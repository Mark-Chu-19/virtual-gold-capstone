#!/usr/bin/env python3
"""
Comparative local evaluation of Qwen 3.5 9B vs Llama 3.1 8B on Apple Silicon M4 (16 GB Unified Memory).
Evaluates latency, token throughput, schema compliance, and redaction precision/recall on
representative executive emails from baseline_dev.jsonl.
"""

import sys
import json
import time
import subprocess
from pathlib import Path

harness_dir = Path(__file__).resolve().parent
sys.path.append(str(harness_dir))
sys.path.append(str(harness_dir.parent.parent.parent / "data"))

from model_client import UnifiedModelClient
from pipeline import run_experiment_pipeline
from score import score as evaluate_score, load as load_gold

def get_process_memory(model_name: str) -> float:
    """Return memory in MB for ollama runner process if available."""
    try:
        out = subprocess.check_output(["ps", "-eo", "rss,comm"]).decode("utf-8")
        for line in out.splitlines():
            if "ollama" in line.lower():
                parts = line.strip().split()
                rss_kb = int(parts[0])
                return round(rss_kb / 1024.0, 1)
    except Exception:
        pass
    return 0.0

def run_comparison():
    data_path = harness_dir.parent.parent.parent / "data" / "baseline_dev.jsonl"
    eval_ids = ["E001", "E002", "E003", "E008", "E010"]
    
    docs_to_eval = []
    gold_subset = {}
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["id"] in eval_ids:
                docs_to_eval.append(rec)
                gold_subset[rec["id"]] = rec

    models = ["qwen3.5:9b", "llama3.1:8b"]
    client = UnifiedModelClient(timeout_s=120.0)
    
    results = {}

    for model in models:
        print(f"\n==========================================")
        print(f"Running Local Evaluation: {model} on Apple M4")
        print(f"==========================================")
        
        preds = []
        traces = []
        latencies_s1 = []
        latencies_s2 = []
        total_latencies = []
        schema_failures = 0
        
        for doc in docs_to_eval:
            print(f"Processing {doc['id']} ({doc['domain']} - {doc['exec']})...", end="", flush=True)
            t0 = time.time()
            tr = run_experiment_pipeline(doc, client, model, stage="C", prompt_version="v2")
            elapsed = time.time() - t0
            print(f" done in {round(elapsed, 2)}s (S1: {round(tr['stage1_latency_s'], 1)}s, S2: {round(tr['stage2_latency_s'], 1)}s)")
            
            traces.append(tr)
            latencies_s1.append(tr["stage1_latency_s"])
            latencies_s2.append(tr["stage2_latency_s"])
            total_latencies.append(tr["total_latency_s"])
            
            if tr.get("degraded") or len(tr.get("failures", [])) > 0:
                schema_failures += 1
                
            pred_spans = [
                {"start": s["start"], "end": s["end"], "type": s.get("category", "SENSITIVE"), "score": s.get("raw_score", 1.0)}
                for s in tr.get("redacted_spans", [])
            ]
            preds.append({"id": doc["id"], "spans": pred_spans})

        pred_dict = {p["id"]: p for p in preds}
        scored = evaluate_score(gold_subset, pred_dict)
        
        results[model] = {
            "model": model,
            "emails_evaluated": len(docs_to_eval),
            "median_latency_s": round(float(sorted(total_latencies)[len(total_latencies)//2]), 2),
            "mean_latency_s": round(float(sum(total_latencies) / len(total_latencies)), 2),
            "median_stage1_s": round(float(sorted(latencies_s1)[len(latencies_s1)//2]), 2),
            "median_stage2_s": round(float(sorted(latencies_s2)[len(latencies_s2)//2]), 2),
            "schema_failures": schema_failures,
            "recall": scored["recall"],
            "recall_partial": scored["recall_partial"],
            "fact_recall": scored["fact_recall"],
            "leak_rate": scored["leak_rate"],
            "extra_masks": scored["extra_masks"],
            "recall_by_type": scored["recall_by_type"],
            "traces": traces
        }

    out_file = harness_dir.parent / "results" / "local_m4_model_comparison.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        # Save summary without large raw text in traces for readability
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    print("\n\n==========================================")
    print("COMPARATIVE LOCAL BENCHMARK SUMMARY (Apple Silicon M4, 16 GB)")
    print("==========================================")
    print(f"{'Metric':<25} | {'Qwen 3.5 9B':<18} | {'Llama 3.1 8B':<18}")
    print("-" * 67)
    print(f"{'Median Latency (Total)':<25} | {results['qwen3.5:9b']['median_latency_s']:>15} s | {results['llama3.1:8b']['median_latency_s']:>15} s")
    print(f"{'Median Stage 1 (Det)':<25} | {results['qwen3.5:9b']['median_stage1_s']:>15} s | {results['llama3.1:8b']['median_stage1_s']:>15} s")
    print(f"{'Median Stage 2 (Ctx)':<25} | {results['qwen3.5:9b']['median_stage2_s']:>15} s | {results['llama3.1:8b']['median_stage2_s']:>15} s")
    print(f"{'Entity Recall':<25} | {results['qwen3.5:9b']['recall']:>18} | {results['llama3.1:8b']['recall']:>18}")
    print(f"{'Fact Recall':<25} | {results['qwen3.5:9b']['fact_recall']:>18} | {results['llama3.1:8b']['fact_recall']:>18}")
    print(f"{'Email Leak Rate':<25} | {results['qwen3.5:9b']['leak_rate']:>18} | {results['llama3.1:8b']['leak_rate']:>18}")
    print(f"{'Extra Masks (Over-mask)':<25} | {results['qwen3.5:9b']['extra_masks']:>18} | {results['llama3.1:8b']['extra_masks']:>18}")
    print(f"{'Schema Failures':<25} | {results['qwen3.5:9b']['schema_failures']:>18} | {results['llama3.1:8b']['schema_failures']:>18}")
    print("==========================================")

if __name__ == "__main__":
    run_comparison()

