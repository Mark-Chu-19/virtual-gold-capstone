"""Score rules, Presidio and their union on Karina's baseline v1.1 (development split by default).

Runs the service's own segmentation and detectors on each `request`, writes predictions in the
service's span format, scores them with data/baseline/score.py, and adds a type check score.py
lacks: for each must-redact span that was found, did an overlapping detection carry the right
type, and did every overlapping detection sit in a less strict tier (it could then be kept).

The 40 test emails are scored once, after the pipeline is frozen (TODO B47); `--part test` and
`--part all` therefore need `--final`.

Usage, from the repo root with the service virtualenv:
    service/.venv/bin/python service/scripts/eval/eval_detectors.py [--part dev] [--out DIR]
"""
import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FILES = {"dev": "baseline_v1.1_dev.jsonl", "test": "baseline_v1.1_test.jsonl", "all": "baseline_v1.1.jsonl"}
ap = argparse.ArgumentParser()
ap.add_argument("--part", choices=FILES, default="dev")
ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "out")
ap.add_argument("--final", action="store_true", help="allow the reserved test emails")
ARGS = ap.parse_args()
if ARGS.part != "dev" and not ARGS.final:
    sys.exit("The test emails are run once, after the pipeline is frozen. Add --final to do so.")
PART, OUT, DATA = ARGS.part, ARGS.out.resolve(), REPO / "data/baseline" / FILES[ARGS.part]
sys.path.insert(0, str(REPO / "service"))

from vg_redactor.contracts.policy import Policy  # noqa: E402
from vg_redactor.contracts.types import RedactionRequestV3  # noqa: E402
from vg_redactor.privacy import FileContextStore, detect_rules, make_detect_presidio  # noqa: E402
from vg_redactor.privacy.merge import make_merge  # noqa: E402
from vg_redactor.stubs.components import segment  # noqa: E402

RANK = {"public": 0, "low": 1, "medium": 2, "high": 3}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    policy = Policy.load(REPO / "service/config/policy.yaml")
    ctx = FileContextStore.load(REPO / "service/config/context_store.yaml", policy.high_types())
    presidio, merge = make_detect_presidio(), make_merge(policy)
    emails = [json.loads(line) for line in open(DATA, encoding="utf-8")]
    preds = {d: [] for d in ("rules", "presidio", "union")}
    for e in emails:
        req = RedactionRequestV3.model_validate(e["request"])
        segs = segment(req.purpose, req.email)
        r, p = detect_rules(segs, ctx), presidio(segs)
        for det, cands in (("rules", r), ("presidio", p), ("union", merge(r, p))):
            preds[det].append({"id": e["id"], "spans": [
                {"field": c.field, "start": c.start, "end": c.end, "type": c.type,
                 "tier": policy.tier_of(c.type)} for c in cands]})

    print(f"{PART}: {len(emails)} emails, tier table {policy.version}\n")
    summary = {}
    for det, rows in preds.items():
        path = OUT / f"pred_{det}_{PART}.jsonl"
        path.write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
        rep = OUT / f"score_{det}_{PART}.json"
        subprocess.run([sys.executable, str(REPO / "data/baseline/score.py"), str(DATA), str(path),
                        "--out", str(rep)], check=True, capture_output=True)
        summary[det] = json.loads(rep.read_text())
    types = type_check(emails, preds["union"])

    cols = (("rules", 9), ("presidio", 10), ("union", 9))
    print(f"{'':16}{'rules':>9}{'presidio':>10}{'union':>9}")
    for k in ("recall", "recall_partial", "fact_recall", "leak_rate", "extra_masks"):
        print(f"{k:16}" + "".join(f"{_fmt(summary[d][k]):>{w}}" for d, w in cols))
    for t in ("high", "medium", "low"):
        print(f"{'leak ' + t:16}" + "".join(f"{_fmt(summary[d]['leak_rate_by_tier'][t]):>{w}}"
                                          for d, w in cols))

    print("\nUNION by type (must-redact spans): n | fully masked | found any | right type | tier too low")
    rec = summary["union"]["recall_by_type"]
    for t, (n, found, right, low) in sorted(types.items(), key=lambda kv: -kv[1][0]):
        print(f"  {t:22}{n:4} | {_fmt(rec.get(t)):>5} | {found / n:4.0%} | "
              f"{(right / found if found else 0):4.0%} | {low}")
    if PART == "dev":  # never print test-set text
        misses = collections.defaultdict(list)
        for m in summary["union"]["misses"]:
            if len(misses[m["type"]]) < 4:
                misses[m["type"]].append(m["text"][:40])
        print("\nUNION misses (examples)")
        for t, v in sorted(misses.items()):
            print(f"  {t}: {v}")


def type_check(emails, union_rows):
    """Per label type: [spans, found (any overlap), found with the right type, found but every
    overlapping detection sits in a less strict tier]."""
    out = collections.defaultdict(lambda: [0, 0, 0, 0])
    by_id = {x["id"]: x["spans"] for x in union_rows}
    for e in emails:
        dets = by_id[e["id"]]
        for s in e["spans"]:
            if s["ground_truth"] != "redact" or s["type"] == "FACT":
                continue
            hit = [d for d in dets if d["field"] == s["field"]
                   and d["start"] < s["field_end"] and s["field_start"] < d["end"]]
            row = out[s["service_type"]]
            row[0] += 1
            if hit:
                row[1] += 1
                row[2] += any(d["type"] == s["service_type"] for d in hit)
                row[3] += all(RANK[d["tier"]] < RANK[s["tier"]] for d in hit)
    return out


def _fmt(v):
    return "-" if v is None else (str(v) if isinstance(v, int) else f"{v:.0%}")


if __name__ == "__main__":
    main()
