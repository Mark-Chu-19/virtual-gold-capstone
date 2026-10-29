#!/usr/bin/env python3
"""Split baseline v1.1 into 60 development emails and 40 reserved test emails.

Usage:
    python make_split.py            # writes split_v1.1.json, baseline_v1.1_dev.jsonl, baseline_v1.1_test.jsonl
    python make_split.py --check    # recomputes the split and fails if the committed files differ

Rules (decision log 2026-10-19 and TODO B47: tune on the 60, report on the 40 once, after the pipeline is frozen):
1. E001-E024 are always development. Anmol's 15-email development benchmark (DEFAULT_15_IDS) was drawn
   from this range and those emails have been looked at while tuning, so none of them may be test.
2. The 40 test emails come from E025-E100, stratified by business domain (largest-remainder allocation).
3. Among stratified draws (fixed seed), keep the one whose test set best matches the full dataset on label
   mix: redact spans by tier, retain spans, FACT and HEALTH spans, negative controls, adversarial emails,
   exec role and industry. Only the labels are used. No model output is ever used, so the split cannot be
   tuned toward any pipeline.
4. The seed and the number of draws are fixed below. Do not change them, and do not re-split after
   looking at test results.
"""
import json, random, collections, argparse, sys
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "baseline_v1.1.jsonl"
SEED, DRAWS, N_TEST = 20261019, 20000, 40
FORCED_DEV = {f"E{i:03d}" for i in range(1, 25)}

def features(e):
    f = collections.Counter()
    for s in e["spans"]:
        if s["ground_truth"] == "redact":
            f["redact"] += 1; f["tier_" + s.get("tier", "none")] += 1
        else:
            f["retain"] += 1
        if s["type"] in ("FACT", "HEALTH"):
            f["type_" + s["type"]] += 1
    tags = set(e["tags"])
    f["neg_control"] += "negative_control" in tags
    f["adversarial"] += e["domain"] == "Adversarial & Evasion"
    f["confidential_fact_tag"] += "confidential_fact" in tags
    f["exec_" + e["exec"]] += 1
    f["ind_" + e["industry"]] += 1
    return f

def allocate(pool_by_dom, n, rng):
    """Largest-remainder allocation of n test emails across domains; equal remainders are ordered by rng."""
    total = sum(len(v) for v in pool_by_dom.values())
    quota = {d: n * len(v) / total for d, v in pool_by_dom.items()}
    alloc = {d: int(q) for d, q in quota.items()}
    rest = n - sum(alloc.values())
    groups = collections.defaultdict(list)
    for d in sorted(quota):
        groups[round(quota[d] - alloc[d], 9)].append(d)
    ordered = []
    for r in sorted(groups, reverse=True):
        if len(ordered) >= rest:
            break
        g = groups[r]; rng.shuffle(g); ordered += g
    for d in ordered[:rest]:
        alloc[d] += 1
    return alloc

def make():
    emails = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]
    ids = [e["id"] for e in emails]
    assert len(ids) == 100 and len(set(ids)) == 100
    feats = {e["id"]: features(e) for e in emails}
    total = sum(feats.values(), collections.Counter())
    target = {k: v * N_TEST / len(emails) for k, v in total.items()}
    pool = collections.defaultdict(list)
    for e in emails:
        if e["id"] not in FORCED_DEV:
            pool[e["domain"]].append(e["id"])
    rng = random.Random(SEED)
    best = None
    for _ in range(DRAWS):
        alloc = allocate(pool, N_TEST, rng)
        test = sorted(i for d in sorted(pool) for i in rng.sample(sorted(pool[d]), alloc[d]))
        got = sum((feats[i] for i in test), collections.Counter())
        loss = sum((got[k] - t) ** 2 / max(t, 1.0) for k, t in target.items())
        if best is None or loss < best[0]:
            best = (round(loss, 6), test)
    test = set(best[1])
    dev = [i for i in ids if i not in test]
    assert len(dev) == 60 and len(test) == N_TEST and FORCED_DEV <= set(dev)
    return emails, dev, sorted(test), best[0], feats, target

def summary(emails, part):
    sel = [e for e in emails if e["id"] in part]
    c = collections.Counter()
    for e in sel:
        for s in e["spans"]:
            c[s["ground_truth"]] += 1
            if s["ground_truth"] == "redact":
                c["redact_" + s.get("tier", "none")] += 1
                if s["type"] == "FACT": c["redact_FACT"] += 1
    return {"emails": len(sel), "redact_spans": c["redact"], "retain_spans": c["retain"],
            "redact_by_tier": {t: c["redact_" + t] for t in ("high", "medium", "low")},
            "fact_spans": c["redact_FACT"],
            "domains": dict(sorted(collections.Counter(e["domain"] for e in sel).items())),
            "negative_controls": sum("negative_control" in e["tags"] for e in sel)}

def outputs():
    emails, dev, test, loss, *_ = make()
    split = {
        "dataset": SRC.name, "seed": SEED, "draws": DRAWS, "balance_loss": loss,
        "rule": "E001-E024 forced to dev (contains DEFAULT_15_IDS); 40 test drawn from E025-E100, "
                "stratified by domain, balanced on labels only. Test is run once, after the pipeline is frozen.",
        "dev": dev, "test": test,
        "summary": {"dev": summary(emails, set(dev)), "test": summary(emails, set(test))},
    }
    by_id = {e["id"]: e for e in emails}
    line = lambda e: json.dumps(e, ensure_ascii=False) + "\n"
    return {
        "split_v1.1.json": json.dumps(split, ensure_ascii=False, indent=2) + "\n",
        "baseline_v1.1_dev.jsonl": "".join(line(by_id[i]) for i in dev),
        "baseline_v1.1_test.jsonl": "".join(line(by_id[i]) for i in test),
    }

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    out = outputs()
    if a.check:
        bad = [n for n, t in out.items() if not (HERE / n).exists() or (HERE / n).read_text(encoding="utf-8") != t]
        print("split OK" if not bad else f"split differs: {bad}"); sys.exit(1 if bad else 0)
    for n, t in out.items():
        (HERE / n).write_text(t, encoding="utf-8")
    s = json.loads(out["split_v1.1.json"])
    print(json.dumps(s["summary"], indent=2)); print("test:", " ".join(s["test"]))
