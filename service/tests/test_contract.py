"""V3 validation, policy rules and supported API surface."""
import copy

import httpx
import pytest

from conftest import EMAIL_REQ, post_json

R = "/v3/redaction"


async def test_auth_required_but_health_is_public(client):
    r = await client.post(R, content="{}", headers={"Authorization": "Bearer nope",
                                                    "Content-Type": "application/json"})
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json")
    anon = httpx.AsyncClient(transport=client._transport, base_url="http://t")  # no default key
    assert (await anon.get("/healthz")).status_code == 200
    assert (await anon.get("/readyz")).status_code == 200
    assert (await anon.get("/v3/info")).status_code == 401


async def test_content_type_and_json_errors(client):
    r = await client.post(R, content="x", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415
    r = await client.post(R, content="{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["type"] == "urn:vg:problem:malformed-json"


async def test_payload_too_large(client, settings):
    big = copy.deepcopy(EMAIL_REQ); big["email"]["body"] = "x" * (settings.max_request_bytes + 10)
    assert (await post_json(client, R, big)).status_code == 413


@pytest.mark.parametrize("mutate,field,code", [
    (lambda b: b.pop("purpose"), "purpose", "missing"),
    (lambda b: b.update(retain=True), "retain", "extra_forbidden"),
    (lambda b: b.update(session_id="abc"), "session_id", "extra_forbidden"),
    (lambda b: b.update(policy={"overrides": {"thresholds": {"high": 0.9}}}),
     "policy.overrides.thresholds.high", "high_tier_fixed"),
    (lambda b: b.update(policy={"overrides": {"entity_types": {"exclude": ["HEALTH"]}}}),
     "policy.overrides.entity_types.exclude", "high_tier_fixed"),
])
async def test_validation_422(client, mutate, field, code):
    body = copy.deepcopy(EMAIL_REQ)
    mutate(body)
    r = await post_json(client, R, body)
    assert r.status_code == 422
    assert {"field": field, "code": code} in r.json()["violations"]


async def test_422_never_echoes_input(client):
    body = copy.deepcopy(EMAIL_REQ); body["email"]["body"] = 12345
    body["SECRET-CANARY-FIELD"] = "SECRET-CANARY-VALUE"
    r = await post_json(client, R, body)
    assert r.status_code == 422 and "CANARY" not in r.text.replace("SECRET-CANARY-FIELD", "")


async def test_allow_list_on_high_tier_candidate_is_422(client):
    body = copy.deepcopy(EMAIL_REQ)
    body["policy"] = {"overrides": {"allow_list": ["123-45-6789"]}}
    r = await post_json(client, R, body)
    assert r.status_code == 422 and r.json()["violations"][0]["code"] == "high_tier_fixed"


async def test_info_health_ready(client):
    info = (await client.get("/v3/info")).json()
    assert info["failure_behavior"] == "redact_all_candidates" and info["contract_version"] == "v3"
    assert info["tiers"]["high"]["threshold"] == 0.2 and info["limits"]["max_records"] == 1000
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    ready = (await client.get("/readyz")).json()
    assert ready["mode"] == "ready" and ready["components"]["model_detection"] == "up"


async def test_policy_override_medium_threshold(client):
    body = copy.deepcopy(EMAIL_REQ)
    body["policy"] = {"overrides": {"thresholds": {"medium": 0.9}}}  # stub calibrates 0.9 -> 0.675
    text = (await post_json(client, R, body)).json()["redacted_email"]["body"]
    assert "202-555-0102" in text  # Medium falls below the overridden threshold.
    assert "123-45-6789" not in text  # High tier remains protected.


async def test_only_v3_is_registered(app, client):
    paths = {route.path for route in app.routes}
    assert not any(path.startswith(("/v1/", "/v2/")) for path in paths)
    for path in ("/v1/redactions", "/v2/redactions", "/v2/restorations"):
        assert (await post_json(client, path, EMAIL_REQ)).status_code == 404
    info = (await client.get("/v3/info")).json()
    assert info["supported_contracts"] == ["v3"]
    assert info["restoration"]["backend"] == "mapping"
    assert "tokenization" not in info
    ready = (await client.get("/readyz")).json()
    assert ready["components"]["session_store"] == "up"
    assert "conversation_key_store" not in ready["components"]
