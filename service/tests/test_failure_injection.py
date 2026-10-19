"""Failure-injection table (development-schedule W10). Every failure must fail safe."""
import asyncio
import copy

import pytest

from conftest import EMAIL_REQ, post_json

R = "/v1/redactions"


def assert_degraded(j, reason, stage):
    assert j["degraded"] is True and j["degraded_reason"] == reason and j["degraded_stage"] == stage
    assert j["spans"], "rule candidates must still be found"
    assert all(s["action"] == "redact" and s["confidence"] is None and s["reason"] == "degraded_redact_all"
               for s in j["spans"])
    assert all(set(s["detectors"]) <= {"rules", "presidio"} for s in j["spans"])
    assert "202-555-0102" not in j["redacted_email"]["body"]


@pytest.mark.parametrize("mode,reason", [("down", "model_unavailable"), ("timeout", "model_timeout"),
                                         ("garbage", "model_output_unparseable")])
@pytest.mark.parametrize("prompt,stage", [("detection", "detection"), ("assessment", "assessment")])
async def test_model_failures_degrade(client, model, mode, reason, prompt, stage):
    model.mode[prompt] = mode
    r = await post_json(client, R, EMAIL_REQ)
    assert r.status_code == 200 and r.headers["X-Degraded"] == "true"
    assert_degraded(r.json(), reason, stage)


async def test_hanging_model_degrades_within_timeout(client, model, settings):
    model.mode["detection"] = "hang"
    loop = asyncio.get_running_loop(); t = loop.time()
    r = await post_json(client, R, EMAIL_REQ)
    assert r.status_code == 200 and loop.time() - t < settings.timeout_ms / 1000
    assert_degraded(r.json(), "model_timeout", "detection")


async def test_degraded_still_restores(client, model):
    model.mode["assessment"] = "down"
    rid = (await post_json(client, R, EMAIL_REQ)).json()["request_id"]
    r = await post_json(client, f"{R}/{rid}/restore", {"reply_text": "[PHONE_1]"})
    assert r.json()["restore_decision"] == "RESTORED"


async def test_presidio_failure_is_degraded_200(client, components):
    def boom(segs): raise RuntimeError("presidio exploded")
    components.detect_presidio = boom
    r = await post_json(client, R, EMAIL_REQ)
    assert r.status_code == 200
    assert_degraded(r.json(), "recognizer_failure", "detection")


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
        await c.delete(f"{R}/{rid_first}")  # frees the slot
        assert (await post_json(c, R, EMAIL_REQ)).status_code == 200


async def test_end_to_end_timeout_504(client, components, settings):
    import time
    settings.timeout_ms = 200
    def slow(segs, ctx): time.sleep(1); return []
    components.detect_rules = slow
    r = await post_json(client, R, EMAIL_REQ)
    assert r.status_code == 504 and r.json()["type"] == "urn:vg:problem:deadline-exceeded"


async def test_record_expiry_gives_410(client, app):
    body = copy.deepcopy(EMAIL_REQ); body["mapping"]["ttl_seconds"] = 1
    rid = (await post_json(client, R, body)).json()["request_id"]
    await asyncio.sleep(1.2)
    assert (await post_json(client, f"{R}/{rid}/restore", {"reply_text": "x"})).status_code == 410


async def test_readyz_reports_degraded_when_model_down(client, model, app):
    model.up = False
    await app.state.refresh_readiness()
    j = (await client.get("/readyz")).json()
    assert j["mode"] == "degraded" and j["components"]["model_detection"] == "down"
