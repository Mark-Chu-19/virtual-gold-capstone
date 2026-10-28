#!/usr/bin/env python3
"""Run the dataset through the team's own service code, to prove the formats match.

Usage (from the repo root, with the service's dependencies installed):
    python data/baseline/check_with_service.py

1. Validates every `request` with RedactionRequest (service/vg_redactor/contracts/types.py).
2. Segments each request and checks every field lands at `field_offsets`.
3. Runs the real rules detector (service/vg_redactor/privacy/rules.py) and scores it.
4. Feeds the labelled spans to decide() with a confident model score (0.9) and counts the
   spans the tier policy would still keep, so the team can see the Low-tier gap directly.
"""
import json, subprocess, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVICE = HERE.parent.parent / "service"
sys.path.insert(0, str(SERVICE))

from vg_redactor.contracts.types import Candidate, Overrides, RedactionRequest, ScoredCandidate
from vg_redactor.contracts.policy import Policy
from vg_redactor.privacy import FileContextStore, decide, detect_rules
from vg_redactor.stubs.components import segment

policy = Policy.load(SERVICE / "config/policy.yaml")
ctx = FileContextStore.load(SERVICE / "config/context_store.yaml", policy.high_types())
data = [json.loads(l) for l in open(HERE / "baseline_v1.1.jsonl", encoding="utf-8")]

preds, gap = [], Counter()
for e in data:
    req = RedactionRequest.model_validate(e["request"])
    segs = segment(req.purpose, req.email)
    for s in segs:
        if s.field != "purpose":
            b = e["field_offsets"][s.field]
            assert e["text"][b:b + len(s.text)] == s.text, (e["id"], s.field)
    preds.append({"id": e["id"], "spans": [{"field": c.field, "start": c.start, "end": c.end, "type": c.type}
                                            for c in detect_rules(segs, ctx)]})
    scored = [ScoredCandidate(candidate=Candidate(field=s["field"], start=s["field_start"], end=s["field_end"],
                                                  type=s["service_type"], detectors={"model"}),
                              raw_score=0.9, is_private=True, calibrated=0.9) for s in e["spans"]]
    for s, d in zip(e["spans"], decide(scored, policy, Overrides(), ctx)):
        if s["ground_truth"] == "redact" and d.action == "retain":
            gap[s["service_type"]] += 1

print(f"{len(data)} requests validate against types.py; all segment fields match field_offsets")
print(f"must-redact spans the tier policy keeps even at score 0.9: {sum(gap.values())} {dict(gap)}\n")
out = HERE / "pred_rules.jsonl"
out.write_text("\n".join(json.dumps(p) for p in preds) + "\n", encoding="utf-8")
print("rules.py alone, scored against ground_truth:")
subprocess.run([sys.executable, str(HERE / "score.py"), str(HERE / "baseline_v1.1.jsonl"), str(out)])
