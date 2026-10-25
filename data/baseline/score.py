#!/usr/bin/env python3
"""Score a redaction model against the baseline dataset (v1 or v1.1).

Usage:
    python score.py baseline_v1.1.jsonl predictions.jsonl [--truth ground_truth|must_mask] [--out report.json]

predictions.jsonl: one line per email. Either offset style works:
    {"id": "E001", "spans": [{"start": 10, "end": 22, "type": "PERSON", "score": 0.93}]}          offsets into "text"
    {"id": "E001", "spans": [{"field": "email.body", "start": 3, "end": 9, "tier": "medium"}]}     service output (contract 0.4.2)
Service-style spans with "action": "retain" are ignored (they were found but not masked).

--truth ground_truth (default for v1.1): a span must be masked when ground_truth == "redact".
--truth must_mask: the original v1 labels, so old numbers can be reproduced.

Metrics
    recall            share of must-mask entity spans (everything except FACT) that were fully masked
                      (at least 95% of their letters and digits covered by predicted spans)
    recall_partial    same, but any overlap counts
    fact_recall       share of FACT spans with at least 50% of letters and digits covered
    leak_rate         share of emails where at least one must-mask entity span was not fully masked
    leak_rate_by_tier share of emails leaking at least one span of that tier (deck slide 19: primary metric)
    extra_masks       predicted spans that overlap no labeled span (over-masking)
    optional_masked   share of not-required spans that were masked (informational)
"""
import json, sys, argparse, collections

def alnum_positions(text, s, e):
    return [i for i in range(s, e) if text[i].isalnum()]

def load(path):
    return {json.loads(l)["id"]: json.loads(l) for l in open(path, encoding="utf-8") if l.strip()}

def to_text_spans(g, pspans):
    out = []
    for p in pspans:
        if p.get("action") == "retain":
            continue
        if "field" in p:
            base = g.get("field_offsets", {}).get(p["field"])
            if base is None:
                continue  # e.g. "purpose": not part of the email text
            out.append({"start": base + p["start"], "end": base + p["end"]})
        else:
            out.append(p)
    return out

def score(gold, pred, truth):
    required = (lambda s: s["ground_truth"] == "redact") if truth == "ground_truth" else (lambda s: s["must_mask"])
    tot = collections.Counter(); hit = collections.Counter(); part = collections.Counter()
    by_type = collections.defaultdict(lambda: [0, 0]); by_dom = collections.defaultdict(lambda: [0, 0])
    tier_leaks = collections.Counter()
    leaked_emails, misses, extra, opt_tot, opt_hit = [], [], 0, 0, 0
    fact_tot = fact_hit = 0
    for eid, g in gold.items():
        text = g["text"]
        cov = [False] * len(text)
        pspans = to_text_spans(g, pred.get(eid, {}).get("spans", []))
        for p in pspans:
            for i in range(max(0, p["start"]), min(len(text), p["end"])):
                cov[i] = True
        leaked, tiers_leaked = False, set()
        for s in g["spans"]:
            if truth == "must_mask" and s.get("must_mask") is None:
                continue  # added in review, not part of v1
            pos = alnum_positions(text, s["start"], s["end"]) or list(range(s["start"], s["end"]))
            frac = sum(cov[i] for i in pos) / len(pos)
            if not required(s):
                opt_tot += 1; opt_hit += frac > 0
                continue
            if s["type"] == "FACT":
                fact_tot += 1; fact_hit += frac >= 0.5
                continue
            full = frac >= 0.95
            key = s.get("service_type", s["type"]) if truth == "ground_truth" else s["type"]
            tot["all"] += 1; hit["all"] += full; part["all"] += frac > 0
            by_type[key][0] += 1; by_type[key][1] += full
            by_dom[g["domain"]][0] += 1; by_dom[g["domain"]][1] += full
            if not full:
                leaked = True
                if "tier" in s: tiers_leaked.add(s["tier"])
                misses.append({"id": eid, "type": key, "text": s["text"], "covered": round(frac, 2)})
        if leaked:
            leaked_emails.append(eid)
        for t in tiers_leaked:
            tier_leaks[t] += 1
        for p in pspans:
            if not any(p["start"] < s["end"] and s["start"] < p["end"] for s in g["spans"]):
                extra += 1
    r = lambda a, b: round(a / b, 4) if b else None
    return {
        "truth": truth,
        "emails": len(gold),
        "recall": r(hit["all"], tot["all"]),
        "recall_partial": r(part["all"], tot["all"]),
        "fact_recall": r(fact_hit, fact_tot),
        "leak_rate": r(len(leaked_emails), len(gold)),
        "leak_rate_by_tier": {t: r(tier_leaks[t], len(gold)) for t in ("high", "medium", "low", "public")},
        "extra_masks": extra,
        "optional_masked": r(opt_hit, opt_tot),
        "recall_by_type": {k: r(v[1], v[0]) for k, v in sorted(by_type.items())},
        "recall_by_domain": {k: r(v[1], v[0]) for k, v in sorted(by_dom.items())},
        "leaked_emails": leaked_emails,
        "misses": misses,
    }

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("gold"); ap.add_argument("pred"); ap.add_argument("--out")
    ap.add_argument("--truth", choices=["ground_truth", "must_mask"])
    a = ap.parse_args()
    gold = load(a.gold)
    truth = a.truth or ("ground_truth" if "ground_truth" in next(iter(gold.values()))["spans"][0] else "must_mask")
    res = score(gold, load(a.pred), truth)
    for k in ["truth", "emails", "recall", "recall_partial", "fact_recall", "leak_rate", "extra_masks", "optional_masked"]:
        print(f"{k:16} {res[k]}")
    if truth == "ground_truth":
        print("\nleak rate by tier:")
        for k, v in res["leak_rate_by_tier"].items():
            print(f"  {k:12} {v}")
    print("\nrecall by type:")
    for k, v in res["recall_by_type"].items():
        print(f"  {k:22} {v}")
    print("\nrecall by domain:")
    for k, v in res["recall_by_domain"].items():
        print(f"  {k:32} {v}")
    if a.out:
        json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
