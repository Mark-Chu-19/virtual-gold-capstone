"""V3 contracts, backend migration, ownership and record lifecycle regression tests."""
import asyncio
import base64
import copy
import json
import logging

import httpx
import pytest

from conftest import EMAIL_REQ, KEY, post_json
from vg_redactor.api.app import create_app
from vg_redactor.settings import hash_key
from vg_redactor.sessions.service import SessionContext

REDACT = "/v3/redaction"
RESTORE = "/v3/restore"
UNKNOWN = "sid_00000000000000000000000000"


def body():
    req = copy.deepcopy(EMAIL_REQ)
    req.pop("mapping")
    return req


def restore_body(result, text=None):
    return {"session_id": result["session_id"],
            "text": result["redacted_email"]["body"] if text is None else text}


def delete_session(client, session_id, **kwargs):
    return client.request("DELETE", REDACT, json={"session_id": session_id}, **kwargs)


async def test_minimal_contract_roundtrip_and_independent_requests(client, app):
    first = await post_json(client, REDACT, body())
    assert first.status_code == 200, first.text
    result = first.json()
    assert set(result) == {"session_id", "redacted_email", "redacted_purpose", "expires_at", "degraded"}
    assert result["session_id"].startswith("sid_")
    assert result["degraded"] is False
    assert "X-Request-ID" in first.headers and "X-Degraded" not in first.headers
    assert first.headers["X-Request-ID"] != result["session_id"]
    second = (await post_json(client, REDACT, body())).json()
    assert second["session_id"] != result["session_id"]
    assert app.state.records.stats()["active"] == 0
    for _ in range(2):
        response = await post_json(client, RESTORE, restore_body(result))
        assert response.status_code == 200, response.text
        assert response.json() == {"restored_text": body()["email"]["body"]}
        assert response.headers["X-Request-ID"] != first.headers["X-Request-ID"]
    # The unprotected legacy lookup must never reach the V3 store.
    legacy = await post_json(client, f'/v1/redactions/{result["session_id"]}/restore',
                             {"reply_text": "[PHONE_1]"})
    assert legacy.status_code == 404


@pytest.mark.parametrize("extra", [
    {"session_id": "client-session"}, {"request_id": "client-request"},
    {"mapping": {"retain": False}}, {"tokenization": {"mode": "aes_siv"}},
    {"source_context": {}},
])
async def test_no_client_ids_retention_backend_or_context(client, extra):
    response = await post_json(client, REDACT, {**body(), **extra})
    assert response.status_code == 422
    assert "request_id" not in response.json()
    assert "X-Request-ID" in response.headers


async def test_errors_and_no_partial_restore(client):
    result = (await post_json(client, REDACT, body())).json()
    response = await post_json(client, RESTORE, restore_body(result, "[PHONE_1] [PHONE_999]"))
    assert response.status_code == 422
    assert response.json()["type"] == "urn:vg:problem:unknown-placeholder"
    assert set(response.json()) == {"type", "title", "status"}
    assert "202-555-0102" not in response.text
    assert (await post_json(client, RESTORE, {"session_id": UNKNOWN, "text": "x"})).status_code == 404
    assert (await post_json(client, RESTORE, {"session_id": "bad", "text": "x"})).status_code == 422
    assert (await post_json(client, RESTORE, {"text": "x"})).status_code == 422
    unauthorized = await post_json(client, RESTORE, restore_body(result),
                                  headers={"Authorization": "Bearer invalid"})
    assert unauthorized.status_code == 401 and "request_id" not in unauthorized.json()
    assert (await delete_session(client, "bad")).status_code == 422


async def test_tenant_isolation_including_tombstones(client, app, settings):
    other_key = "another-key"
    settings.api_key_hashes.add(hash_key(other_key))
    headers = {"Authorization": "Bearer " + other_key}
    result = (await post_json(client, REDACT, body())).json()
    for deleted in (False, True):
        if deleted:
            assert (await delete_session(client, result["session_id"])).status_code == 204
        denied = await post_json(client, RESTORE, restore_body(result), headers=headers)
        assert denied.status_code == 404
        assert (await delete_session(client, result["session_id"], headers=headers)).status_code == 404
    assert (await post_json(client, RESTORE, restore_body(result))).status_code == 410
    assert (await delete_session(client, result["session_id"])).status_code == 204
    assert (await delete_session(client, UNKNOWN)).status_code == 204


@pytest.mark.parametrize("payload", [{}, {"session_id": 123}, {"session_id": UNKNOWN, "text": "extra"}])
async def test_delete_validates_json_body(client, payload):
    response = await client.request("DELETE", REDACT, json=payload)
    assert response.status_code == 422
    assert response.json()["type"] == "urn:vg:problem:validation-failed"
    assert "request_id" not in response.json()


async def test_expiry_and_tombstone_cleanup(client, app):
    clock = [0.0]
    store = app.state.sessions.records
    store._clock = lambda: clock[0]
    result = (await post_json(client, REDACT, body())).json()
    record = store.get(result["session_id"])
    clock[0] = record.expires_at
    assert (await post_json(client, RESTORE, restore_body(result))).status_code == 410
    assert record.mapping is None
    clock[0] += store.max_ttl + 1
    assert (await post_json(client, RESTORE, restore_body(result))).status_code == 404


async def test_empty_mapping_and_degraded_mapping(client, model):
    req = {"purpose": "Summarize", "email": {"body": "Nothing private here."}}
    result = (await post_json(client, REDACT, req)).json()
    restored = await post_json(client, RESTORE, restore_body(result))
    assert restored.json() == {"restored_text": req["email"]["body"]}
    model.mode["assessment"] = "garbage"
    result = (await post_json(client, REDACT, body())).json()
    assert result["degraded"] is True
    assert (await post_json(client, RESTORE, restore_body(result))).json() == {
        "restored_text": body()["email"]["body"]}


class SequenceIds:
    def __init__(self, *ids):
        self.ids = iter(ids)

    def new_id(self):
        return next(self.ids)


async def test_collision_retry_preserves_first_mapping(client, app):
    first = (await post_json(client, REDACT, body())).json()
    sid2 = "sid_00000000000000000000000001"
    app.state.sessions.ids = SequenceIds(first["session_id"], sid2)
    req = {"purpose": "Reply", "email": {"body": "Call 303-555-0103"}}
    second = (await post_json(client, REDACT, req)).json()
    assert second["session_id"] == sid2
    assert (await post_json(client, RESTORE, restore_body(first))).json() == {
        "restored_text": body()["email"]["body"]}
    assert (await post_json(client, RESTORE, restore_body(second))).json() == {
        "restored_text": req["email"]["body"]}


async def test_capacity_and_failure_release(client, app):
    store = app.state.sessions.records
    store.max_records = 1
    result = (await post_json(client, REDACT, body())).json()
    response = await post_json(client, REDACT, body())
    assert response.status_code == 503 and response.headers["Retry-After"] == "5"
    assert (await post_json(client, RESTORE, restore_body(result))).status_code == 200
    await delete_session(client, result["session_id"])
    original = app.state.sessions.backends["mapping"].encode

    def unavailable(*args):
        raise RuntimeError("injected storage failure")

    app.state.sessions.backends["mapping"].encode = unavailable
    response = await post_json(client, REDACT, body())
    assert response.status_code == 500 and "session_id" not in response.json()
    assert store.stats()["active"] == store.stats()["reserved"] == 0
    app.state.sessions.backends["mapping"].encode = original
    assert (await post_json(client, REDACT, body())).status_code == 200


async def test_storage_failure_never_returns_session_id(client, app, monkeypatch):
    store = app.state.sessions.records

    def unavailable(*args, **kwargs):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(store, "commit", unavailable)
    response = await post_json(client, REDACT, body())
    assert response.status_code == 503
    assert response.json()["type"] == "urn:vg:problem:session-store-unavailable"
    assert "session_id" not in response.json()
    assert store.stats()["active"] == store.stats()["reserved"] == 0


async def test_failure_after_commit_removes_mapping(client, app, monkeypatch):
    store = app.state.sessions.records
    captured = []
    original = store.commit

    def capture(*args, **kwargs):
        record = original(*args, **kwargs)
        captured.append(record)
        return record

    def audit_failure(*args):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(store, "commit", capture)
    monkeypatch.setattr(app.state.orchestrator.audit, "write", audit_failure)
    assert (await post_json(client, REDACT, body())).status_code == 500
    assert captured[0].mapping is None
    assert store.stats()["active"] == store.stats()["reserved"] == 0


async def test_timeout_releases_reservation(client, app, settings, monkeypatch):
    settings.timeout_ms = 10

    async def blocked_render(self, decisions):
        await asyncio.sleep(60)

    monkeypatch.setattr(SessionContext, "render", blocked_render)
    response = await post_json(client, REDACT, body())
    assert response.status_code == 504
    assert app.state.sessions.records.stats()["reserved"] == 0


async def test_aes_backend_switch_key_rotation_and_tampering(settings, components, model):
    settings.tokenization.keys = {"k1": base64.b64encode(bytes(range(64))).decode()}
    settings.v3.backend = "aes_siv"
    app = create_app(settings, components, model)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                headers={"Authorization": "Bearer " + KEY}) as client:
        encrypted = (await post_json(client, REDACT, body())).json()
        record = app.state.sessions.records.get(encrypted["session_id"])
        assert record.backend == "aes_siv"
        assert "202-555-0102" not in json.dumps(record.mapping)
        backend = app.state.sessions.backends["aes_siv"]
        backend.keys["k2"] = bytes(reversed(range(64)))
        backend.active_key_id = "k2"
        newer = (await post_json(client, REDACT, body())).json()
        app.state.sessions.backend = "mapping"
        plain = (await post_json(client, REDACT, body())).json()
        assert app.state.sessions.records.get(plain["session_id"]).backend == "mapping"
        for result in (encrypted, newer, plain):
            assert (await post_json(client, RESTORE, restore_body(result))).json() == {
                "restored_text": body()["email"]["body"]}
        # Ciphertext is bound to both tenant and session ID.
        newer_record = app.state.sessions.records.get(newer["session_id"])
        newer_record.mapping = dict(record.mapping)
        assert (await post_json(client, RESTORE, restore_body(newer))).status_code == 503
        del backend.keys["k1"]
        assert (await post_json(client, RESTORE, restore_body(encrypted))).status_code == 503


def test_aes_requires_keys(settings, components, model):
    settings.v3.backend = "aes_siv"
    with pytest.raises(ValueError, match="VG_TOKEN_KEYS"):
        create_app(settings, components, model)


async def test_v3_validation_audit_and_logs_do_not_leak(client, settings, caplog):
    caplog.set_level(logging.DEBUG)
    logging.getLogger("vg_redactor").propagate = True
    result = (await post_json(client, REDACT, body())).json()
    await post_json(client, RESTORE, restore_body(result))
    bad = body()
    bad["email"]["body"] = {"secret": "CANARY-SENSITIVE"}
    response = await post_json(client, REDACT, bad)
    assert response.status_code == 422 and "CANARY-SENSITIVE" not in response.text
    audit = open(settings.audit_log_path, encoding="utf8").read()
    logs = "\n".join(rec.getMessage() + json.dumps(getattr(rec, "fields", {})) for rec in caplog.records)
    for value in ("202-555-0102", "123-45-6789"):
        assert value not in audit and value not in logs
