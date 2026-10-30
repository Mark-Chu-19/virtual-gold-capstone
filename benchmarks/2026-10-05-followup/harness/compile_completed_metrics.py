import json
from pathlib import Path
import numpy as np
import sys

FOLLOWUP_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(FOLLOWUP_DIR / "harness"))

from metrics import compute_character_masks, compute_span_metrics_per_document, compute_brier_score_per_document

DATA_DIR = FOLLOWUP_DIR.parent / "2026-10-05" / "data"
with open(DATA_DIR / "gold_annotations_dev.json") as f:
    dev_gold = {d["id"]: d for d in json.load(f)}
with open(DATA_DIR / "gold_annotations_test.json") as f:
    test_gold = {d["id"]: d for d in json.load(f)}

RAW_DIR = FOLLOWUP_DIR / "results" / "raw_responses"

# Group raw response files by (model, stage, split)
runs = {}
for p in RAW_DIR.glob("*.json"):
    if p.name.startswith("repeat_"):
        continue
    with open(p) as f:
        data = json.load(f)
    model = data["model"]
    stage = data["stage"]
    split = data["split"]
    key = (model, stage, split)
    if key not in runs:
        runs[key] = []
    runs[key].append(data)

summaries = []
for (model, stage, split), records in sorted(runs.items()):
    records.sort(key=lambda r: r["doc_id"])
    golds = dev_gold if split == "dev" else test_gold
    
    total_priv_chars = 0
    total_leaked_chars = 0
    total_pub_chars = 0
    total_over_redacted_chars = 0
    requests_with_leak = 0
    
    tier_totals = {"HIGH": {"total": 0, "leaked": 0}, "MEDIUM": {"total": 0, "leaked": 0}, "LOW": {"total": 0, "leaked": 0}}
    total_latencies = []
    prompt_tokens = 0
    completion_tokens = 0
    cost_usd = 0.0
    degraded_count = 0
    invalid_spans_count = 0
    doc_evaluations = []

    for r in records:
        doc_id = r["doc_id"]
        trace = r["trace"]
        gold = golds[doc_id]
        gold_priv = gold["private_spans"]
        gold_pub = gold["public_spans"]

        char_res = compute_character_masks(
            text_length=len(gold["text"]) if "text" in gold else len(trace["redacted_text"]),
            private_spans=gold_priv,
            public_spans=gold_pub,
            redaction_spans=trace["redacted_spans"]
        )

        total_priv_chars += char_res["total_private_chars"]
        total_leaked_chars += char_res["leaked_private_chars"]
        total_pub_chars += char_res["total_public_chars"]
        total_over_redacted_chars += char_res["masked_public_chars"]
        if char_res["has_leak"]:
            requests_with_leak += 1

        for t in ["HIGH", "MEDIUM", "LOW"]:
            tier_totals[t]["total"] += char_res["tier_breakdown"][t]["total"]
            tier_totals[t]["leaked"] += char_res["tier_breakdown"][t]["leaked"]

        total_latencies.append(trace["total_latency_s"])
        prompt_tokens += trace["prompt_tokens"]
        completion_tokens += trace["completion_tokens"]
        cost_usd += trace["cost_usd"]
        if trace["degraded"]:
            degraded_count += 1
        invalid_spans_count += trace["invalid_spans_discarded"]

        doc_evaluations.append({
            "doc_id": doc_id,
            "gold_private_spans": gold_priv,
            "gold_public_spans": gold_pub,
            "predicted_spans": trace["redacted_spans"],
            "assessed_candidates": trace["assessed_candidates"]
        })

    span_metrics = compute_span_metrics_per_document(doc_evaluations)
    brier_res = compute_brier_score_per_document(doc_evaluations) if stage == "C" else None

    summary = {
        "model": model,
        "stage": stage,
        "split": split,
        "document_count": len(records),
        "total_private_chars": total_priv_chars,
        "leaked_private_chars": total_leaked_chars,
        "char_leak_rate": (total_leaked_chars / total_priv_chars) if total_priv_chars > 0 else 0.0,
        "requests_with_leak": requests_with_leak,
        "request_leak_rate": requests_with_leak / len(records) if records else 0.0,
        "total_public_chars": total_pub_chars,
        "over_redacted_public_chars": total_over_redacted_chars,
        "char_over_redaction_rate": (total_over_redacted_chars / total_pub_chars) if total_pub_chars > 0 else 0.0,
        "tier_summary": {
            t: {
                "total_chars": tier_totals[t]["total"],
                "leaked_chars": tier_totals[t]["leaked"],
                "leak_rate": (tier_totals[t]["leaked"] / tier_totals[t]["total"]) if tier_totals[t]["total"] > 0 else 0.0
            } for t in ["HIGH", "MEDIUM", "LOW"]
        },
        "span_metrics": span_metrics,
        "brier_score": brier_res["brier_score"] if brier_res else None,
        "brier_details": brier_res,
        "latency": {
            "median_s": float(np.median(total_latencies)) if total_latencies else 0.0,
            "p95_s": float(np.percentile(total_latencies, 95)) if total_latencies else 0.0,
            "sample_count": len(total_latencies)
        },
        "tokens": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        },
        "cost_usd": cost_usd,
        "degraded_requests": degraded_count,
        "invalid_spans_discarded": invalid_spans_count
    }
    summaries.append(summary)
    print(f"[{model} | {stage} | {split}] ({len(records)} docs): Leak={summary['char_leak_rate']*100:.2f}% | OverRedact={summary['char_over_redaction_rate']*100:.2f}% | Latency={summary['latency']['median_s']:.2f}s | Cost=${cost_usd:.4f}")

with open(FOLLOWUP_DIR / "results" / "summary_metrics.json", "w") as f:
    json.dump(summaries, f, indent=2)

print("\nSaved summary metrics to", FOLLOWUP_DIR / "results" / "summary_metrics.json")
