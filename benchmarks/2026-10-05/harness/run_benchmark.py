"""
Main Benchmark Runner for Virtual Gold Local Privacy Redaction.
Executes:
- Experiment A: Rules + Presidio baseline
- Experiment B: Baseline + Model Candidate Detection
- Experiment C: Two-call Candidate Union + Contextual Assessment
Across 3 models:
1. meta-llama/llama-3.1-8b-instruct
2. qwen/qwen-2.5-7b-instruct
3. x-ai/grok-4.20
On:
- Development set (10 docs)
- Held-out Test set (20 docs)
Plus 5-case Repeatability check on Test set.
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, List
import numpy as np

# Ensure local imports work
BENCHMARK_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BENCHMARK_DIR / "harness"))

from model_client import ModelClient
from pipeline import run_experiment_pipeline
from metrics import compute_character_masks, compute_span_metrics, compute_brier_score

MODELS = [
    "meta-llama/llama-3.1-8b-instruct",
    "qwen/qwen-2.5-7b-instruct",
    "x-ai/grok-4.20"
]

def load_data():
    data_dir = BENCHMARK_DIR / "data"
    with open(data_dir / "synthetic_documents_dev.json") as f:
        dev_docs = json.load(f)
    with open(data_dir / "synthetic_documents_test.json") as f:
        test_docs = json.load(f)
    with open(data_dir / "gold_annotations_dev.json") as f:
        dev_gold = {d["id"]: d for d in json.load(f)}
    with open(data_dir / "gold_annotations_test.json") as f:
        test_gold = {d["id"]: d for d in json.load(f)}
    return dev_docs, test_docs, dev_gold, test_gold

def evaluate_run(
    docs: List[Dict[str, Any]],
    golds: Dict[str, Any],
    client: ModelClient,
    model: str,
    stage: str,
    split_name: str
) -> Dict[str, Any]:
    print(f"\n>>> Running Evaluation: Model={model} | Stage={stage} | Split={split_name} ({len(docs)} docs) <<<")
    case_results = []
    
    total_priv_chars = 0
    total_leaked_chars = 0
    total_pub_chars = 0
    total_over_redacted_chars = 0
    requests_with_leak = 0
    
    all_gold_priv_spans = []
    all_redacted_spans = []
    all_assessed_candidates = []
    
    tier_totals = {"HIGH": {"total": 0, "leaked": 0},
                   "MEDIUM": {"total": 0, "leaked": 0},
                   "LOW": {"total": 0, "leaked": 0}}

    stage1_latencies = []
    stage2_latencies = []
    total_latencies = []
    prompt_tokens = 0
    completion_tokens = 0
    cost_usd = 0.0
    degraded_count = 0
    invalid_spans_count = 0

    for i, doc in enumerate(docs):
        doc_id = doc["id"]
        gold = golds[doc_id]
        gold_priv = gold["private_spans"]
        gold_pub = gold["public_spans"]
        
        trace = run_experiment_pipeline(doc, client, model, stage=stage)
        
        # Save raw responses to disk
        raw_dir = BENCHMARK_DIR / "results" / "raw_responses"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_record = {
            "doc_id": doc_id,
            "split": split_name,
            "model": model,
            "stage": stage,
            "stage1_raw": trace.get("raw_stage1_response"),
            "stage2_raw": trace.get("raw_stage2_response")
        }
        raw_file = raw_dir / f"{doc_id}_{model.replace('/', '_')}_stage{stage}.json"
        with open(raw_file, "w") as rf:
            json.dump(raw_record, rf, indent=2)

        # Compute character metrics
        char_res = compute_character_masks(
            len(doc["text"]),
            gold_priv,
            gold_pub,
            trace["redacted_spans"]
        )

        # Accumulate
        total_priv_chars += char_res["total_private_chars"]
        total_leaked_chars += char_res["leaked_private_chars"]
        total_pub_chars += char_res["total_public_chars"]
        total_over_redacted_chars += char_res["masked_public_chars"]
        if char_res["has_leak"]:
            requests_with_leak += 1

        for t in ["HIGH", "MEDIUM", "LOW"]:
            tier_totals[t]["total"] += char_res["tier_breakdown"][t]["total"]
            tier_totals[t]["leaked"] += char_res["tier_breakdown"][t]["leaked"]

        all_gold_priv_spans.extend(gold_priv)
        all_redacted_spans.extend(trace["redacted_spans"])
        all_assessed_candidates.extend(trace.get("assessed_candidates", []))

        if trace["degraded"]:
            degraded_count += 1
        invalid_spans_count += trace.get("invalid_spans_discarded", 0)

        stage1_latencies.append(trace["stage1_latency_s"])
        stage2_latencies.append(trace["stage2_latency_s"])
        total_latencies.append(trace["total_latency_s"])
        prompt_tokens += trace["prompt_tokens"]
        completion_tokens += trace["completion_tokens"]
        cost_usd += trace["cost_usd"]

        case_results.append({
            "doc_id": doc_id,
            "split": split_name,
            "model": model,
            "stage": stage,
            "degraded": trace["degraded"],
            "degraded_reason": trace["degraded_reason"],
            "total_private_chars": char_res["total_private_chars"],
            "leaked_private_chars": char_res["leaked_private_chars"],
            "leak_rate_chars": char_res["leak_rate_chars"],
            "has_leak": char_res["has_leak"],
            "total_public_chars": char_res["total_public_chars"],
            "masked_public_chars": char_res["masked_public_chars"],
            "over_redaction_rate_chars": char_res["over_redaction_rate_chars"],
            "tier_breakdown": char_res["tier_breakdown"],
            "redacted_spans_count": len(trace["redacted_spans"]),
            "placeholder_count": len(trace["placeholder_map"]),
            "latency_s": trace["total_latency_s"],
            "cost_usd": trace["cost_usd"]
        })
        print(f"  [{i+1}/{len(docs)}] {doc_id} -> leaked={char_res['leaked_private_chars']}/{char_res['total_private_chars']} chars | over-mask={char_res['masked_public_chars']}/{char_res['total_public_chars']} | time={trace['total_latency_s']:.2f}s")

    # Aggregate span metrics
    span_res = compute_span_metrics(all_gold_priv_spans, all_redacted_spans)
    
    # Brier score (for Stage C)
    gold_pub_all = []
    for g in golds.values():
        gold_pub_all.extend(g["public_spans"])
    brier = compute_brier_score(all_assessed_candidates, all_gold_priv_spans, gold_pub_all) if stage == "C" else None

    summary = {
        "model": model,
        "stage": stage,
        "split": split_name,
        "document_count": len(docs),
        "total_private_chars": total_priv_chars,
        "leaked_private_chars": total_leaked_chars,
        "char_leak_rate": (total_leaked_chars / total_priv_chars) if total_priv_chars > 0 else 0.0,
        "requests_with_leak": requests_with_leak,
        "request_leak_rate": (requests_with_leak / len(docs)) if docs else 0.0,
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
        "span_metrics": span_res,
        "brier_score": brier,
        "latency": {
            "median_s": float(np.median(total_latencies)) if total_latencies else 0.0,
            "p95_s": float(np.percentile(total_latencies, 95)) if total_latencies else 0.0,
            "stage1_median_s": float(np.median(stage1_latencies)) if stage1_latencies else 0.0,
            "stage2_median_s": float(np.median(stage2_latencies)) if stage2_latencies else 0.0,
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

    return summary, case_results

def main():
    dev_docs, test_docs, dev_gold, test_gold = load_data()
    client = ModelClient(budget_ceiling_usd=5.0)

    all_summaries = []
    all_case_results = []

    # 1. Baseline (Experiment A) on Dev and Test
    base_summary_dev, base_cases_dev = evaluate_run(
        dev_docs, dev_gold, client, "baseline_rules_presidio", "A", "dev"
    )
    base_summary_test, base_cases_test = evaluate_run(
        test_docs, test_gold, client, "baseline_rules_presidio", "A", "test"
    )
    all_summaries.extend([base_summary_dev, base_summary_test])
    all_case_results.extend(base_cases_dev + base_cases_test)

    # 2. Model Experiments (B and C) on Dev and Test for all 3 models
    for m in MODELS:
        # Experiment B (Baseline + Model Detection) on Test
        s_b_test, cases_b_test = evaluate_run(
            test_docs, test_gold, client, m, "B", "test"
        )
        all_summaries.append(s_b_test)
        all_case_results.extend(cases_b_test)

        # Experiment C (Two-Call Pipeline with Assessment) on Dev and Test
        s_c_dev, cases_c_dev = evaluate_run(
            dev_docs, dev_gold, client, m, "C", "dev"
        )
        s_c_test, cases_c_test = evaluate_run(
            test_docs, test_gold, client, m, "C", "test"
        )
        all_summaries.extend([s_c_dev, s_c_test])
        all_case_results.extend(cases_c_dev + cases_c_test)

    # 3. Repeatability Check: 5 held-out cases repeated 3 times at temp=0.0
    print("\n>>> Running Repeatability Check: 5 held-out cases x 3 repetitions across models <<<")
    repeat_docs = test_docs[:5]
    repeatability_results = []
    for m in MODELS:
        print(f"Testing repeatability for model: {m}")
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
        
        # Check stability across runs
        identical_spans = True
        for d_idx in range(len(repeat_docs)):
            spans0 = runs[0][d_idx]["redacted_spans"]
            for r_idx in range(1, 3):
                spans_r = runs[r_idx][d_idx]["redacted_spans"]
                if len(spans0) != len(spans_r):
                    identical_spans = False
                else:
                    for s0, sr in zip(spans0, spans_r):
                        if (s0["start"], s0["end"]) != (sr["start"], sr["end"]):
                            identical_spans = False

        repeatability_results.append({
            "model": m,
            "doc_ids": [d["id"] for d in repeat_docs],
            "repetitions": 3,
            "identical_outputs_across_runs": identical_spans,
            "rep_runs": runs
        })

    # Save results
    results_dir = BENCHMARK_DIR / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    with open(results_dir / "summary_metrics.json", "w") as f:
        json.dump(all_summaries, f, indent=2)

    with open(results_dir / "per_case_results.json", "w") as f:
        json.dump(all_case_results, f, indent=2)

    with open(results_dir / "variability_results.json", "w") as f:
        json.dump(repeatability_results, f, indent=2)

    print("\n==========================================")
    print(f"BENCHMARK COMPLETE!")
    print(f"Total API Cost Incurred: ${client.total_cost_usd:.4f}")
    print(f"Total Prompt Tokens: {client.total_prompt_tokens}")
    print(f"Total Completion Tokens: {client.total_completion_tokens}")
    print("==========================================")

if __name__ == "__main__":
    main()
