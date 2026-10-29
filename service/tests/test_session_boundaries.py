"""Regression tests for literal labels, output expansion, deadlines and failure cleanup."""
import asyncio
import base64
import io
import json
import logging
import threading
import time

import httpx
import pytest

from conftest import HEADERS, EMAIL_REQ, post_json
from vg_redactor.api import app as api
from vg_redactor.obs.logging import AllowlistJsonFormatter, get_logger, log_event
from vg_redactor.privacy import pseudonymize as privacy_pseudonymize


@pytest.fixture(params=["mapping", "aes_siv"])
def backend_app(request, settings, components, model):
    settings.v3.backend = request.param
    if request.param == "aes_siv":
        settings.v3.keys = {"k1": base64.b64encode(bytes(range(64))).decode()}
    return api.create_app(settings, components, model)


@pytest.fixture
async def backend_client(backend_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=backend_app, raise_app_exceptions=False),
                                base_url="http://test", headers=HEADERS) as client:
        yield client


@pytest.mark.parametrize("real_renderer", [False, True])
async def test_original_labels_roundtrip_without_collisions(
        backend_client, backend_app, components, real_renderer):
    if real_renderer:
        components.pseudonymize = privacy_pseudonymize
    original = "Keep [PHONE_1] and [phone_2]; call 202-555-0102."
    req = {"purpose": "Keep [EMAIL_1]", "email": {
        "subject": "Keep [PHONE_9]", "body": original,
        "thread": [{"text": "Original [PHONE_4]"}]}}
    response = await post_json(backend_client, "/v3/redaction", req)
    assert response.status_code == 200, response.text
    result = response.json()
    assert "[PHONE_3]" in result["redacted_email"]["body"]
    assert "[PHONE_1]" in result["redacted_email"]["body"]
    assert "[phone_2]" in result["redacted_email"]["body"]
    for text in (original, "Keep [EMAIL_1]", "Keep [PHONE_9]", "Original [PHONE_4]"):
        redacted = result["redacted_email"]["body"] if text == original else text
        restored = await post_json(backend_client, "/v3/restore", {
            "session_id": result["session_id"], "text": redacted})
        assert restored.json() == {"restored_text": text}
    # Only literals present in the original request are identity-mapped.
    unknown = await post_json(backend_client, "/v3/restore", {
        "session_id": result["session_id"], "text": "[PHONE_8]"})
    assert unknown.status_code == 422


async def test_restore_expansion_rejected_before_replacement(
        backend_client, backend_app, components, monkeypatch):
    value = "synthetic confidential value " * 400
    result = (await post_json(backend_client, "/v3/redaction", {
        "purpose": "Reply", "email": {"body": value},
        "policy": {"overrides": {"deny_list": [value]}}})).json()
    called = []
    original = components.restore

    def track(*args):
        called.append(True)
        return original(*args)

    monkeypatch.setattr(components, "restore", track)
    payload = {"session_id": result["session_id"], "text": result["redacted_email"]["body"] * 1000}
    assert len(json.dumps(payload)) < 20000
    response = await post_json(backend_client, "/v3/restore", payload)
    assert response.status_code == 413
    assert response.json()["type"] == "urn:vg:problem:restored-text-too-large"
    assert "restored_text" not in response.json()
    assert not called  # No large replacement string was allocated by the restore component.
    assert backend_app.state.records.stats()["active"] == 1
    payload["text"] = result["redacted_email"]["body"]
    assert (await post_json(backend_client, "/v3/restore", payload)).json() == {"restored_text": value}


async def test_output_limit_counts_utf8_and_accepts_exact_boundary(backend_client, backend_app):
    value = "秘密😀"
    req = {"purpose": "Reply", "email": {"body": value},
           "policy": {"overrides": {"deny_list": [value]}}}
    result = (await post_json(backend_client, "/v3/redaction", req)).json()
    payload = {"session_id": result["session_id"], "text": result["redacted_email"]["body"]}
    backend_app.state.sessions.max_restored_bytes = len(value.encode("utf8"))
    assert (await post_json(backend_client, "/v3/restore", payload)).json() == {"restored_text": value}
    payload["text"] += "!"
    assert (await post_json(backend_client, "/v3/restore", payload)).status_code == 413
    # Token-free text is subject to the same byte limit.
    payload["text"] = value + "!"
    assert (await post_json(backend_client, "/v3/restore", payload)).status_code == 413


@pytest.mark.parametrize("data", [
    {"purpose": "Reply", "email": {"body": "\ud800"}},
    {"purpose": "\udfff", "email": {"body": "hello"}},
    {"purpose": "Reply", "email": {"body": "hello"}, "\ud800": "invalid key"},
])
async def test_invalid_unicode_rejected_before_reserving_storage(client, app, data):
    response = await client.post("/v3/redaction", content=json.dumps(data),
                                 headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["violations"] == [{"field": "body", "code": "invalid_unicode"}]
    assert app.state.records.stats()["active"] == app.state.records.stats()["reserved"] == 0


async def test_valid_escaped_surrogate_pair_is_accepted(client):
    content = '{"purpose":"Reply","email":{"body":"\\ud83d\\ude00"}}'
    response = await client.post("/v3/redaction", content=content,
                                 headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    assert response.json()["redacted_email"]["body"] == "😀"


async def test_serialization_failure_cleans_committed_record(client, app, components, monkeypatch):
    original = components.pseudonymize

    def invalid_output(*args):
        out = original(*args)
        out.redacted_email["body"] = "\ud800"
        return out

    monkeypatch.setattr(components, "pseudonymize", invalid_output)
    response = await post_json(client, "/v3/redaction", EMAIL_REQ)
    assert response.status_code == 500
    assert "session_id" not in response.json()
    assert app.state.records.stats()["active"] == app.state.records.stats()["reserved"] == 0


@pytest.mark.parametrize("phase", ["encode", "audit", "serialize"])
async def test_timeout_is_responsive_and_late_worker_cannot_publish(
        client, app, settings, monkeypatch, phase):
    settings.timeout_ms = 100
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    if phase == "encode":
        target, name = app.state.sessions.backends["mapping"], "encode"
    elif phase == "audit":
        target, name = app.state.orchestrator.audit, "write"
    else:
        target, name = api, "_json_response"
    original = getattr(target, name)

    def blocked(*args, **kwargs):
        started.set()
        try:
            release.wait(3)
            return original(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(target, name, blocked)
    task = asyncio.create_task(post_json(client, "/v3/redaction", EMAIL_REQ))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        # A blocked encoder/audit/serializer must not block the service's event loop.
        assert (await asyncio.wait_for(client.get("/healthz"), .5)).status_code == 200
        response = await asyncio.wait_for(task, .5)
        assert response.status_code == 504
        assert app.state.records.stats()["active"] == app.state.records.stats()["reserved"] == 0
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 1)
        await task
    assert app.state.records.stats()["active"] == app.state.records.stats()["reserved"] == 0


async def test_overdue_synchronous_commit_never_returns_success(client, app, settings, monkeypatch):
    settings.timeout_ms = 50
    original = app.state.records.commit

    def slow_commit(*args, **kwargs):
        time.sleep(.1)
        return original(*args, **kwargs)

    monkeypatch.setattr(app.state.records, "commit", slow_commit)
    response = await post_json(client, "/v3/redaction", EMAIL_REQ)
    assert response.status_code == 504
    assert app.state.records.stats()["active"] == app.state.records.stats()["reserved"] == 0


async def test_formatted_log_contains_session_id_but_not_sensitive_fields(client):
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(AllowlistJsonFormatter())
    logger = get_logger()
    logger.addHandler(handler)
    try:
        response = await post_json(client, "/v3/redaction", EMAIL_REQ)
        sid = response.json()["session_id"]
        log_event("canary", session_id=sid, text="SECRET-CANARY-VALUE")
    finally:
        logger.removeHandler(handler)
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    created = next(event for event in events if event["event"] == "session_created")
    assert created["session_id"] == sid
    assert created["request_id"] == response.headers["X-Request-ID"]
    assert "SECRET-CANARY-VALUE" not in output.getvalue()


async def test_restore_snapshot_survives_concurrent_delete(client, app, monkeypatch):
    result = (await post_json(client, "/v3/redaction", EMAIL_REQ)).json()
    captured, release = threading.Event(), threading.Event()
    original = app.state.records.get

    def delayed_get(*args, **kwargs):
        record = original(*args, **kwargs)
        captured.set()
        release.wait(3)
        return record

    monkeypatch.setattr(app.state.records, "get", delayed_get)
    task = asyncio.create_task(post_json(client, "/v3/restore", {
        "session_id": result["session_id"], "text": result["redacted_email"]["body"]}))
    try:
        assert await asyncio.to_thread(captured.wait, 1)
        deleted = await client.request("DELETE", "/v3/redaction", json={"session_id": result["session_id"]})
        assert deleted.status_code == 204
    finally:
        release.set()
    assert (await task).json() == {"restored_text": EMAIL_REQ["email"]["body"]}
    # Requests starting after deletion must not access the retained in-flight snapshot.
    response = await post_json(client, "/v3/restore", {"session_id": result["session_id"], "text": "x"})
    assert response.status_code == 410
