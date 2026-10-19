"""Contract tests: status codes, fields and rules from contract 0.4.2."""
import copy
import json

import httpx
import pytest

from conftest import EMAIL_REQ, HEADERS, post_json

R = "/v1/redactions"


async def test_redact_ok_shape(client):
    r = await post_json(client, R, EMAIL_REQ)
    assert r.status_code == 200
    b = r.json()
    assert b["request_id"].startswith("req_") and r.headers["X-Request-ID"] == b["request_id"]
    assert b["degraded"] is False and "degraded_reason" not in b and r.headers["X-Degraded"] == "false"
    assert b["record"]["mapping_retained"] is True
    assert set(b["prompt_versions"]) == {"detection", "assessment"}
    body = b["redacted_email"]["body"]
    assert "202-555-0102" not in body and "[PHONE_1]" in body and "123-45-6789" not in body
    # spans never carry the original value, offsets index the original text
    assert all(set(s) == {"field", "start", "end", "type", "tier", "action", "confidence",
                          "detectors", "reason"} for s in b["spans"])
    phone = next(s for s in b["spans"] if s["type"] == "PHONE_PERSONAL")
    assert EMAIL_REQ["email"]["body"][phone["start"]:phone["end"]] == "202-555-0102"
    re_ = b["redacted_email"]  # same shape as the input; the stub rules redact header addresses too
    assert set(EMAIL_REQ["email"]) <= set(re_) and re_["from"]["address"].startswith("[EMAIL_")
    assert re_["to"][0]["name"] == "Support Team" and len(re_["thread"]) == 1


async def test_auth_required_but_health_is_public(client):
    r = await client.post(R, content="{}", headers={"Authorization": "Bearer nope",
                                                    "Content-Type": "application/json"})
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json")
    anon = httpx.AsyncClient(transport=client._transport, base_url="http://t")  # no default key
    assert (await anon.get("/healthz")).status_code == 200
    assert (await anon.get("/readyz")).status_code == 200
    assert (await anon.get("/v1/info")).status_code == 401


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
    (lambda b: b.update(session_id="abc"), "session_id", "session_requires_retain"),
    (lambda b: b["mapping"].update(retain=True, ttl_seconds=10**9), "mapping.ttl_seconds", "ttl_too_large"),
    (lambda b: b.update(policy={"overrides": {"thresholds": {"high": 0.9}}}),
     "policy.overrides.thresholds.high", "high_tier_fixed"),
    (lambda b: b.update(policy={"overrides": {"entity_types": {"exclude": ["HEALTH"]}}}),
     "policy.overrides.entity_types.exclude", "high_tier_fixed"),
])
async def test_validation_422(client, mutate, field, code):
    body = copy.deepcopy(EMAIL_REQ)
    if code == "session_requires_retain":
        body["mapping"] = {"retain": False}
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


async def test_restore_roundtrip_and_retry(client):
    rid = (await post_json(client, R, EMAIL_REQ)).json()["request_id"]
    reply = "Call [PHONE_1] about [GOV_1]"
    for _ in range(2):  # restore does not consume the record, so retry works
        r = await post_json(client, f"{R}/{rid}/restore", {"reply_text": reply})
        assert r.status_code == 200 and r.json()["restore_decision"] == "RESTORED"
    assert "202-555-0102" in r.json()["restored_text"] and "123-45-6789" in r.json()["restored_text"]


async def test_restore_blocked_cases(client):
    rid = (await post_json(client, R, EMAIL_REQ)).json()["request_id"]
    r = await post_json(client, f"{R}/{rid}/restore", {"reply_text": "x [PHONE_9] [phone_1]"})
    j = r.json()
    assert j["restore_decision"] == "BLOCKED" and j["reason"] == "unknown_placeholder"
    assert set(j["unmatched_placeholders"]) == {"[PHONE_9]", "[phone_1]"} and "restored_text" not in j
    no_map = copy.deepcopy(EMAIL_REQ); no_map["mapping"] = {"retain": False}
    rid2 = (await post_json(client, R, no_map)).json()["request_id"]
    j = (await post_json(client, f"{R}/{rid2}/restore", {"reply_text": "[PHONE_1]"})).json()
    assert j["restore_decision"] == "BLOCKED" and j["reason"] == "mapping_not_retained"


async def test_restore_404_410_and_delete_idempotent(client):
    assert (await post_json(client, f"{R}/req_unknown/restore", {"reply_text": "x"})).status_code == 404
    rid = (await post_json(client, R, EMAIL_REQ)).json()["request_id"]
    assert (await client.delete(f"{R}/{rid}")).status_code == 204
    assert (await client.delete(f"{R}/{rid}")).status_code == 204
    assert (await client.delete(f"{R}/req_never")).status_code == 204
    assert (await post_json(client, f"{R}/{rid}/restore", {"reply_text": "x"})).status_code == 410


async def test_session_labels_are_consistent_across_requests(client):
    body = copy.deepcopy(EMAIL_REQ); body["session_id"] = "s1"
    a = (await post_json(client, R, body)).json()["redacted_email"]["body"]
    body2 = copy.deepcopy(body); body2["email"]["body"] = "Again 202-555-0102 and 303-555-0103"
    b = (await post_json(client, R, body2)).json()["redacted_email"]["body"]
    # request 1 used PHONE_1 (body) and PHONE_2 (the thread's support line); the same number keeps
    # its label in request 2 and the new number continues the numbering
    assert "[PHONE_1]" in a and "[PHONE_1]" in b and "[PHONE_3]" in b


async def test_info_health_ready(client):
    info = (await client.get("/v1/info")).json()
    assert info["failure_behavior"] == "redact_all_candidates" and info["contract_version"] == "0.4.2"
    assert info["tiers"]["high"]["threshold"] == 0.2 and info["limits"]["max_records"] == 1000
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    ready = (await client.get("/readyz")).json()
    assert ready["mode"] == "ready" and ready["components"]["model_detection"] == "up"


async def test_policy_override_medium_threshold(client):
    body = copy.deepcopy(EMAIL_REQ)
    body["policy"] = {"overrides": {"thresholds": {"medium": 0.9}}}  # stub calibrates 0.9 -> 0.675
    spans = (await post_json(client, R, body)).json()["spans"]
    phone = next(s for s in spans if s["type"] == "PHONE_PERSONAL")
    assert phone["action"] == "retain" and phone["reason"] == "below_threshold"
    ssn = next(s for s in spans if s["type"] == "GOV_ID")
    assert ssn["action"] == "redact"  # High tier unaffected
