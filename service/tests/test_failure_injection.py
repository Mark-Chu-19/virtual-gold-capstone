"""Failure-injection table (development-schedule W10). Every failure must fail safe."""
import asyncio
import json

import pytest

from conftest import EMAIL_REQ, post_json

R = "/v3/redaction"


def assert_degraded(j, reason, stage, settings):
    assert j["degraded"] is True
    assert "degraded_reason" not in j and "spans" not in j
    assert "202-555-0102" not in j["redacted_email"]["body"]
    # Detailed decisions belong to audit, not the client response.
    audit = json.loads(open(settings.audit_log_path, encoding="utf8").read().splitlines()[-1])
    assert audit["degraded_reason"] == reason and audit["degraded_stage"] == stage
    assert audit["spans"], "rule candidates must still be found"
    assert all(s["action"] == "redact" and s["confidence"] is None
               and s["reason"] == "degraded_redact_all" for s in audit["spans"])


@pytest.mark.parametrize("mode,reason", [("down", "model_unavailable"), ("timeout", "model_timeout"),
                                         ("garbage", "model_output_unparseable")])
@pytest.mark.parametrize("prompt,stage", [("detection", "detection"), ("assessment", "assessment")])
async def test_model_failures_degrade(client, model, mode, reason, prompt, stage, settings):
    model.mode[prompt] = mode
    r = await post_json(client, R, EMAIL_REQ)
    assert r.status_code == 200 and "X-Degraded" not in r.headers
    assert_degraded(r.json(), reason, stage, settings)


async def test_hanging_model_degrades_within_timeout(client, model, settings):
    model.mode["detection"] = "hang"
    loop = asyncio.get_running_loop(); t = loop.time()
    r = await post_json(client, R, EMAIL_REQ)
    assert r.status_code == 200 and loop.time() - t < settings.timeout_ms / 1000
    assert_degraded(r.json(), "model_timeout", "detection", settings)


async def test_degraded_still_restores(client, model):
    model.mode["assessment"] = "down"
    sid = (await post_json(client, R, EMAIL_REQ)).json()["session_id"]
    r = await post_json(client, "/v3/restore", {"session_id": sid, "text": "[PHONE_1]"})
    assert r.json() == {"restored_text": "202-555-0102"}


async def test_presidio_failure_is_degraded_200(client, components, settings):
    def boom(segs): raise RuntimeError("presidio exploded")
    components.detect_presidio = boom
    r = await post_json(client, R, EMAIL_REQ)
    assert r.status_code == 200
    assert_degraded(r.json(), "recognizer_failure", "detection", settings)


async def test_rule_engine_failure_is_500_and_releases_slot(client, components, app):
    def boom(segs, ctx): raise RuntimeError("rules exploded")
    components.detect_rules = boom
    r = await post_json(client, R, EMAIL_REQ)
    assert r.status_code == 500 and r.headers["content-type"].startswith("application/problem+json")
    assert app.state.records.stats()["reserved"] == 0


async def test_capacity_exhausted_503(settings, components, model):
    import httpx
    from vg_redactor.api.app import create_app
    from vg_redactor.obs.metrics import Metrics
    from conftest import HEADERS
    settings.max_records = 1
    app = create_app(settings, components, model, Metrics())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                 headers=HEADERS) as c:
        assert (await post_json(c, R, EMAIL_REQ)).status_code == 200
        r = await post_json(c, R, EMAIL_REQ)
        assert r.status_code == 503 and r.headers["Retry-After"]
        rid_first = list(app.state.records._records)[0]
        await c.request("DELETE", R, json={"session_id": rid_first})  # frees the slot
        assert (await post_json(c, R, EMAIL_REQ)).status_code == 200


async def test_end_to_end_timeout_504(client, components, settings):
    import time
    settings.timeout_ms = 200
    def slow(segs, ctx): time.sleep(1); return []
    components.detect_rules = slow
    r = await post_json(client, R, EMAIL_REQ)
    assert r.status_code == 504 and r.json()["type"] == "urn:vg:problem:deadline-exceeded"


async def test_readyz_reports_degraded_when_model_down(client, model, app):
    model.up = False
    await app.state.refresh_readiness()
    j = (await client.get("/readyz")).json()
    assert j["mode"] == "degraded" and j["components"]["model_detection"] == "down"
