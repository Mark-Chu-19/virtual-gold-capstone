"""
Main Benchmark Runner for Virtual Gold Privacy Redaction Follow-Up.
Evaluates:
1. local_qwen3.5_9b (Local Ollama on Apple M4, Q4_K_M)
2. google/gemma-3-12b-it (OpenRouter)
3. qwen/qwen3.5-9b (OpenRouter)

Across:
- Experiment B: Baseline + Model Candidate Detection (Union mask) on Test (20 docs)
- Experiment C: Two-Call Candidate Union + Contextual Assessment on Dev (10 docs) and Test (20 docs)
Plus 5-case Repeatability Check (3 repetitions) on Test set.

Uses strictly per-document metric computation from metrics.py.
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, List
import numpy as np

FOLLOWUP_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(FOLLOWUP_DIR / "harness"))

from model_client import UnifiedModelClient
from pipeline import run_experiment_pipeline
from metrics import (
    compute_character_masks,
    compute_span_metrics_per_document,
    compute_brier_score_per_document
)

MODELS = [
    "local_qwen3.5_9b",
    "google/gemma-3-12b-it",
    "qwen/qwen3.5-9b"
]

DATA_DIR = FOLLOWUP_DIR.parent / "2026-10-05" / "data"

def load_data():
    with open(DATA_DIR / "synthetic_documents_dev.json") as f:
        dev_docs = json.load(f)
    with open(DATA_DIR / "synthetic_documents_test.json") as f:
        test_docs = json.load(f)
    with open(DATA_DIR / "gold_annotations_dev.json") as f:
        dev_gold = {d["id"]: d for d in json.load(f)}
    with open(DATA_DIR / "gold_annotations_test.json") as f:
        test_gold = {d["id"]: d for d in json.load(f)}
    return dev_docs, test_docs, dev_gold, test_gold

def evaluate_run(
    docs: List[Dict[str, Any]],
    golds: Dict[str, Any],
    client: UnifiedModelClient,
    model: str,
    stage: str,
    split_name: str
) -> Dict[str, Any]:
    print(f"\n>>> Running Evaluation: Model={model} | Stage={stage} | Split={split_name} ({len(docs)} docs) <<<")
    case_results = []
    doc_evaluations = []
    
    total_priv_chars = 0
    total_leaked_chars = 0
    total_pub_chars = 0
    total_over_redacted_chars = 0
    requests_with_leak = 0
    
    tier_totals = {
        "HIGH": {"total": 0, "leaked": 0},
        "MEDIUM": {"total": 0, "leaked": 0},
        "LOW": {"total": 0, "leaked": 0}
    }

    stage1_latencies = []
    stage2_latencies = []
    total_latencies = []
    load_durations = []
    eval_durations = []
    prompt_tokens = 0
    completion_tokens = 0
    cost_usd = 0.0
    degraded_count = 0
    invalid_spans_count = 0

    raw_dir = FOLLOWUP_DIR / "results" / "raw_responses"
    raw_dir.mkdir(parents=True, exist_ok=True)

    for i, doc in enumerate(docs):
        doc_id = doc["id"]
        gold = golds[doc_id]
        gold_priv = gold["private_spans"]
        gold_pub = gold["public_spans"]
        
        trace = run_experiment_pipeline(doc, client, model, stage=stage)
        
        clean_model_name = model.replace("/", "_").replace(":", "_")
        raw_record = {
            "doc_id": doc_id,
            "split": split_name,
            "model": model,
            "stage": stage,
            "trace": trace
        }
        with open(raw_dir / f"{clean_model_name}_{stage}_{split_name}_{doc_id}.json", "w") as f:
            json.dump(raw_record, f, indent=2)

        char_res = compute_character_masks(
            text_length=len(doc["text"]),
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

        stage1_latencies.append(trace["stage1_latency_s"])
        stage2_latencies.append(trace["stage2_latency_s"])
        total_latencies.append(trace["total_latency_s"])
        load_durations.append(trace.get("load_duration_s", 0.0))
        eval_durations.append(trace.get("eval_duration_s", 0.0))
        prompt_tokens += trace["prompt_tokens"]
        completion_tokens += trace["completion_tokens"]
        cost_usd += trace["cost_usd"]
        if trace["degraded"]:
            degraded_count += 1
        invalid_spans_count += trace["invalid_spans_discarded"]

        doc_eval_entry = {
            "doc_id": doc_id,
            "gold_private_spans": gold_priv,
            "gold_public_spans": gold_pub,
            "predicted_spans": trace["redacted_spans"],
            "assessed_candidates": trace["assessed_candidates"]
        }
        doc_evaluations.append(doc_eval_entry)

        case_results.append({
            "doc_id": doc_id,
            "model": model,
            "stage": stage,
            "split": split_name,
            "degraded": trace["degraded"],
            "degraded_reason": trace["degraded_reason"],
            "char_metrics": char_res,
            "redacted_spans_count": len(trace["redacted_spans"]),
            "union_spans_count": len(trace["union_spans"]),
            "total_latency_s": trace["total_latency_s"],
            "cost_usd": trace["cost_usd"]
        })

    span_metrics = compute_span_metrics_per_document(doc_evaluations)
    brier_res = compute_brier_score_per_document(doc_evaluations) if stage == "C" else None

    summary = {
        "model": model,
        "stage": stage,
        "split": split_name,
        "document_count": len(docs),
        "total_private_chars": total_priv_chars,
        "leaked_private_chars": total_leaked_chars,
        "char_leak_rate": (total_leaked_chars / total_priv_chars) if total_priv_chars > 0 else 0.0,
        "requests_with_leak": requests_with_leak,
        "request_leak_rate": requests_with_leak / len(docs) if docs else 0.0,
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
            "stage1_median_s": float(np.median(stage1_latencies)) if stage1_latencies else 0.0,
            "stage2_median_s": float(np.median(stage2_latencies)) if stage2_latencies else 0.0,
            "load_duration_sum_s": float(np.sum(load_durations)),
            "eval_duration_median_s": float(np.median(eval_durations)) if eval_durations else 0.0,
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

    print(f"Summary for {model} [{stage}|{split_name}]:")
    print(f"  Leak Rate: {summary['char_leak_rate']*100:.2f}% | Req Leaks: {summary['requests_with_leak']}/{len(docs)} ({summary['request_leak_rate']*100:.1f}%)")
    print(f"  Over-redaction: {summary['char_over_redaction_rate']*100:.2f}% | High-tier Leak: {summary['tier_summary']['HIGH']['leak_rate']*100:.2f}%")
    print(f"  Span Exact P/R: {span_metrics['exact_precision']:.3f} / {span_metrics['exact_recall']:.3f} | Overlap P/R: {span_metrics['overlap_precision']:.3f} / {span_metrics['overlap_recall']:.3f}")
    if brier_res and brier_res["brier_score"] is not None:
        print(f"  Brier Score: {brier_res['brier_score']:.4f} (Evaluated: {brier_res['evaluated_candidates']}/{brier_res['total_assessed_candidates']})")
    print(f"  Median Latency: {summary['latency']['median_s']:.2f}s | Cost: ${summary['cost_usd']:.5f}")

    return summary, case_results

def run_repeatability_check(
    repeat_docs: List[Dict[str, Any]],
    client: UnifiedModelClient,
    models: List[str]
) -> List[Dict[str, Any]]:
    print("\n>>> Running Repeatability Check: 5 comparison cases x 3 repetitions across models <<<")
    repeatability_results = []

    for m in models:
        print(f"\nTesting repeatability for model: {m} (3 repetitions)")
        runs = []
        for rep in range(3):
            rep_run = []
            for doc in repeat_docs:
                trace = run_experiment_pipeline(doc, client, m, stage="C")
                rep_run.append({
                    "doc_id": doc["id"],
                    "redacted_spans": trace["redacted_spans"],
                    "placeholder_map": trace["placeholder_map"],
                    "total_latency_s": trace["total_latency_s"]
                })
            runs.append(rep_run)

        identical_spans = True
        doc_agreement = []
        for d_idx in range(len(repeat_docs)):
            doc_id = repeat_docs[d_idx]["id"]
            spans0 = runs[0][d_idx]["redacted_spans"]
            doc_match = True
            for r_idx in range(1, 3):
                spans_r = runs[r_idx][d_idx]["redacted_spans"]
                if len(spans0) != len(spans_r):
                    doc_match = False
                    identical_spans = False
                else:
                    for s0, sr in zip(spans0, spans_r):
                        if (s0["start"], s0["end"]) != (sr["start"], sr["end"]):
                            doc_match = False
                            identical_spans = False
            doc_agreement.append({
                "doc_id": doc_id,
                "identical_across_reps": doc_match,
                "rep0_spans": len(runs[0][d_idx]["redacted_spans"]),
                "rep1_spans": len(runs[1][d_idx]["redacted_spans"]),
                "rep2_spans": len(runs[2][d_idx]["redacted_spans"])
            })

        print(f"Model {m} repeatability: Identical={identical_spans}")
        repeatability_results.append({
            "model": m,
            "doc_ids": [d["id"] for d in repeat_docs],
            "repetitions": 3,
            "identical_outputs_across_runs": identical_spans,
            "doc_agreement": doc_agreement,
            "rep_runs": runs
        })

    return repeatability_results

def main():
    dev_docs, test_docs, dev_gold, test_gold = load_data()
    client = UnifiedModelClient(budget_ceiling_usd=3.0)

    all_summaries = []
    all_case_results = []

    for m in MODELS:
        print(f"\n=======================================================")
        print(f"STARTING EVALUATION FOR MODEL: {m}")
        print(f"=======================================================")
        
        s_b_test, cases_b_test = evaluate_run(
            test_docs, test_gold, client, m, "B", "test"
        )
        all_summaries.append(s_b_test)
        all_case_results.extend(cases_b_test)

        s_c_dev, cases_c_dev = evaluate_run(
            dev_docs, dev_gold, client, m, "C", "dev"
        )
        all_summaries.append(s_c_dev)
        all_case_results.extend(cases_c_dev)

        s_c_test, cases_c_test = evaluate_run(
            test_docs, test_gold, client, m, "C", "test"
        )
        all_summaries.append(s_c_test)
        all_case_results.extend(cases_c_test)

    repeat_docs = test_docs[:5]
    repeatability_results = run_repeatability_check(repeat_docs, client, MODELS)

    results_dir = FOLLOWUP_DIR / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    with open(results_dir / "summary_metrics.json", "w") as f:
        json.dump(all_summaries, f, indent=2)

    with open(results_dir / "per_case_results.json", "w") as f:
        json.dump(all_case_results, f, indent=2)

    with open(results_dir / "variability_results.json", "w") as f:
        json.dump(repeatability_results, f, indent=2)

    print("\n==========================================")
    print("FOLLOW-UP BENCHMARK COMPLETE!")
    print(f"Total API Cost Incurred: ${client.total_cost_usd:.4f}")
    print(f"Total Prompt Tokens: {client.total_prompt_tokens}")
    print(f"Total Completion Tokens: {client.total_completion_tokens}")
    print("==========================================")

if __name__ == "__main__":
    main()

