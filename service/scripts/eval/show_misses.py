"""List each must-redact span a prediction file misses or tags with a less strict tier, with the
text around it. Development emails only.

Usage, from the repo root:
    python service/scripts/eval/show_misses.py service/scripts/eval/out/pred_union_dev.jsonl \\
        CODENAME,ACCOUNT_NUMBER,ID_NUMBER
"""
import json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
gold = {e["id"]: e for e in map(json.loads, open(REPO / "data/baseline/baseline_v1.1_dev.jsonl"))}
pred = {x["id"]: x["spans"] for x in map(json.loads, open(sys.argv[1]))}
want = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
RANK = {"public": 0, "low": 1, "medium": 2, "high": 3}
for i, e in gold.items():
    if i not in pred:
        sys.exit(f"{sys.argv[1]} has no prediction for {i}: is it a development run?")
    for s in e["spans"]:
        if s["ground_truth"] != "redact" or (want and s["service_type"] not in want):
            continue
        hit = [d for d in pred[i] if d["field"] == s["field"]
               and d["start"] < s["field_end"] and s["field_start"] < d["end"]]
        if any(d["start"] <= s["field_start"] and d["end"] >= s["field_end"]
               and RANK[d["tier"]] >= RANK[s["tier"]] for d in hit):
            continue
        body = e["request"]["email"]["body"] if s["field"] == "email.body" else None
        where = (body[max(0, s["field_start"] - 45):s["field_end"] + 30].replace("\n", " ")
                 if body else s["field"])
        print(f"{i} {s['service_type']:15} [{s['text']}] | {[(d['type'], d['tier']) for d in hit]} | ...{where}...")
