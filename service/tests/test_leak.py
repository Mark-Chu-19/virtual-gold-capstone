"""No input text, detected value or restored text may appear in logs, audit, metrics or errors."""
import copy
import json
import logging

from conftest import EMAIL_REQ, post_json

R = "/v1/redactions"
CANARIES = ["CANARY-412-555-0182", "zxqperson@canary.test", "CANARYSSN 987-65-4321", "Project Falcon"]


def canary_request():
    b = copy.deepcopy(EMAIL_REQ)
    b["email"]["body"] = ("Reach me at 412-555-0182 or zxqperson@canary.test. "
                          "SSN 987-65-4321. About Project Falcon.")
    b["purpose"] = "Summarize CANARY-412-555-0182 thread"
    return b


async def test_no_canaries_anywhere(client, model, app, settings, caplog):
    caplog.set_level(logging.DEBUG)
    logging.getLogger("vg_redactor").propagate = True
    outputs = []
    r = await post_json(client, R, canary_request()); outputs.append(r.text)
    rid = r.json()["request_id"]
    rr = await post_json(client, f"{R}/{rid}/restore", {"reply_text": "[PHONE_1] [EMAIL_1]"})
    assert "412-555-0182" in rr.text  # restore legitimately returns the original to the caller
    model.mode["assessment"] = "garbage"  # degraded path too
    outputs.append((await post_json(client, R, canary_request())).text)
    bad = canary_request(); bad["email"]["body"] = 5
    outputs.append((await post_json(client, R, bad)).text)
    outputs.append((await client.get("/v1/info")).text)
    await client.delete(f"{R}/{rid}")

    log_text = "\n".join(rec.getMessage() + json.dumps(getattr(rec, "fields", {})) for rec in caplog.records)
    audit_text = open(settings.audit_log_path, encoding="utf8").read()
    metrics_text = app.state.metrics.render().decode()
    for canary in ["412-555-0182", "zxqperson@canary.test", "987-65-4321"]:
        for name, text in [("log", log_text), ("audit", audit_text), ("metrics", metrics_text)] + \
                          [(f"response{i}", t) for i, t in enumerate(outputs)]:
            assert canary not in text, f"{canary} leaked into {name}"
    assert "raw_scores" in audit_text  # raw scores are allowed, but only here
