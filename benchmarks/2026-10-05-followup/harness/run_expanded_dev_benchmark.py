#!/usr/bin/env python3
"""
Expanded Local Development Benchmark on Apple Silicon M4 (16 GB Unified Memory):
- Evaluates 15 representative executive emails from baseline_dev.jsonl
- Tests both Llama 3.1 8B (llama3.1:8b) and Qwen 3.5 9B (qwen3.5:9b)
- Uses hardened v2 prompts, exhaustive tier rules, connected multi-detector fallback,
  and detector provenance preservation in merge_and_deduplicate_spans
- Records:
  1. Character-level private leakage (including FACT clauses)
  2. Character-level public text masking
  3. Scorer metrics (score.py: entity recall, fact recall, entity leak rate, extra masks)
  4. Latency breakdown (Stage 1 detection, Stage 2 assessment, total)
  5. Live memory telemetry via ollama ps and ps rss
  6. Candidate-level audit records for empirical calibration refitting
- Saves intermediate checkpoints after each document to ensure robustness
"""

import sys
import os
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple, Optional

harness_dir = Path(__file__).resolve().parent
repo_root = harness_dir.parent.parent.parent
sys.path.append(str(harness_dir))
sys.path.append(str(repo_root / "data"))

from model_client import UnifiedModelClient
from pipeline import run_experiment_pipeline
from score import score as evaluate_score
from calibration import EmpiricalCalibrator

DEV_DATA_PATH = repo_root / "data" / "baseline_dev.jsonl"
RESULTS_DIR = harness_dir.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR = harness_dir.parent / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

CHECKPOINT_FILE = RESULTS_DIR / "dev15_checkpoint.json"
FINAL_RESULTS_FILE = RESULTS_DIR / "local_m4_dev15_benchmark.json"
AUDIT_RECORDS_FILE = CONFIG_DIR / "calibration_fit_records_dev15.jsonl"
CALIBRATION_PROFILE_FILE = CONFIG_DIR / "calibration_profile_dev15.json"

DEFAULT_15_IDS = [
    "E001", "E002", "E003", "E005", "E008",
    "E009", "E011", "E013", "E015", "E016",
    "E018", "E019", "E020", "E023", "E024"
]

def get_ollama_memory_telemetry() -> Dict[str, Any]:
    """Capture live memory from ollama ps and ps -eo rss,comm."""
    telemetry = {
        "ollama_ps_size": None,
        "ollama_ps_processor": None,
        "runner_rss_mb": 0.0,
        "raw_ps_output": None
    }
    try:
        out = subprocess.check_output(["ollama", "ps"], stderr=subprocess.DEVNULL).decode("utf-8")
        lines = out.strip().splitlines()
        if len(lines) > 1:
            parts = lines[1].split()
            # NAME ID SIZE PROCESSOR CONTEXT UNTIL
            if len(parts) >= 4:
                telemetry["ollama_ps_size"] = parts[2] + " " + parts[3] if parts[3] in ["GB", "MB"] else parts[2]
                telemetry["ollama_ps_processor"] = parts[4] if parts[3] in ["GB", "MB"] else parts[3]
    except Exception:
        pass

    try:
        ps_out = subprocess.check_output(["ps", "-eo", "rss,comm"]).decode("utf-8")
        total_rss_kb = 0
        for line in ps_out.splitlines():
            line_l = line.lower()
            if "llama-server" in line_l or "ollama" in line_l:
                parts = line.strip().split()
                if parts and parts[0].isdigit():
                    total_rss_kb += int(parts[0])
        telemetry["runner_rss_mb"] = round(total_rss_kb / 1024.0, 1)
    except Exception:
        pass

    return telemetry

def compute_character_metrics(
    doc: Dict[str, Any],
    redacted_spans: List[Dict[str, Any]]
) -> Dict[str, Any]:
    text = doc["text"]
    text_len = len(text)

    # 1. Gold private character indices
    gold_priv_indices: Set[int] = set()
    gold_fact_indices: Set[int] = set()
    for s in doc.get("spans", []):
        if s.get("must_mask", True):
            for i in range(max(0, s["start"]), min(text_len, s["end"])):
                gold_priv_indices.add(i)
                if s.get("type") == "FACT":
                    gold_fact_indices.add(i)

    # 2. Gold public character indices
    gold_pub_indices: Set[int] = set(range(text_len)) - gold_priv_indices

    # 3. Masked character indices
    masked_indices: Set[int] = set()
    for p in redacted_spans:
        for i in range(max(0, p["start"]), min(text_len, p["end"])):
            masked_indices.add(i)

    # 4. Leakage & Over-redaction
    leaked_priv = gold_priv_indices - masked_indices
    leaked_fact = gold_fact_indices - masked_indices
    masked_pub = gold_pub_indices.intersection(masked_indices)

    tot_priv = len(gold_priv_indices)
    tot_fact = len(gold_fact_indices)
    tot_pub = len(gold_pub_indices)

    return {
        "text_length": text_len,
        "total_private_chars": tot_priv,
        "leaked_private_chars": len(leaked_priv),
        "private_leak_rate": round(len(leaked_priv) / tot_priv, 4) if tot_priv > 0 else 0.0,
        "total_fact_chars": tot_fact,
        "leaked_fact_chars": len(leaked_fact),
        "fact_leak_rate": round(len(leaked_fact) / tot_fact, 4) if tot_fact > 0 else 0.0,
        "total_public_chars": tot_pub,
        "masked_public_chars": len(masked_pub),
        "public_mask_rate": round(len(masked_pub) / tot_pub, 4) if tot_pub > 0 else 0.0
    }

def run_benchmark(
    email_ids: List[str] = DEFAULT_15_IDS,
    models: List[str] = ["llama3.1:8b", "qwen3.5:9b"],
    fresh: bool = False,
    out_file: Optional[str] = None,
    stage: str = "C",
    use_gliner: bool = False,
    gliner_model: str = "urchade/gliner_multi_pii-v1",
    gliner_threshold: float = 0.35,
    stage2_model: Optional[str] = None,
    enable_thinking: bool = False,
):
    final_results_file = Path(out_file) if out_file else FINAL_RESULTS_FILE
    checkpoint_file = final_results_file.with_name(final_results_file.stem + "_checkpoint.json")

    print("=" * 70)
    print("STARTING BENCHMARK EVALUATION")
    print(f"Emails ({len(email_ids)}): {', '.join(email_ids)}")
    print(f"Models: {', '.join(models)}")
    print(f"Stage: {stage} | Use GLiNER: {use_gliner} ({gliner_model if use_gliner else 'N/A'}) | Thinking: {enable_thinking}")
    print(f"Fresh Run: {fresh}")
    print(f"Output File: {final_results_file}")
    print("=" * 70)

    # Load dataset (auto-select all dev IDs if "ALL" passed)
    gold_docs: Dict[str, Any] = {}
    all_dev_ids: List[str] = []
    with open(DEV_DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                d = json.loads(line)
                all_dev_ids.append(d["id"])
                if "ALL" in email_ids or d["id"] in email_ids:
                    gold_docs[d["id"]] = d

    if "ALL" in email_ids:
        email_ids = all_dev_ids

    # Preserve order of email_ids
    eval_docs = [gold_docs[eid] for eid in email_ids if eid in gold_docs]

    client = UnifiedModelClient(timeout_s=180.0, enable_thinking=enable_thinking)
    all_results: Dict[str, Any] = {}
    audit_records: List[Dict[str, Any]] = []

    # Check for existing checkpoint
    if not fresh and checkpoint_file.exists():
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                all_results = json.load(f)
            print(f"Loaded existing checkpoint with models: {list(all_results.keys())}")
        except Exception:
            all_results = {}

    for model in models:
        print(f"\n>>> Running Evaluation for Model: {model} <<<")
        model_results = all_results.get(model, {
            "model": model,
            "emails_completed": 0,
            "traces": [],
            "char_metrics_by_doc": {},
            "telemetry": []
        })

        completed_ids = set(tr["doc_id"] for tr in model_results.get("traces", []))
        
        for doc in eval_docs:
            doc_id = doc["id"]
            if doc_id in completed_ids:
                print(f"[{model}] {doc_id} already evaluated in checkpoint, skipping.")
                continue

            print(f"[{model}] Processing {doc_id} ({doc['domain']} | {doc['exec']})...", flush=True)
            t_start = time.time()
            
            # Memory telemetry before/during call
            mem_telemetry = get_ollama_memory_telemetry()
            
            # Execute pipeline with v2 prompts and active fallback
            trace = run_experiment_pipeline(
                doc,
                client,
                model,
                stage=stage,
                prompt_version="v2",
                use_gliner=use_gliner,
                gliner_model=gliner_model,
                gliner_threshold=gliner_threshold,
                stage2_model=stage2_model,
            )
            elapsed = time.time() - t_start
            
            # Compute character-level metrics
            c_metrics = compute_character_metrics(doc, trace["redacted_spans"])
            
            print(f"[{model}] {doc_id} done in {round(elapsed, 1)}s | "
                  f"Priv Leaked: {c_metrics['leaked_private_chars']}/{c_metrics['total_private_chars']} "
                  f"({round(c_metrics['private_leak_rate']*100, 1)}%) | "
                  f"Pub Masked: {c_metrics['masked_public_chars']}/{c_metrics['total_public_chars']} "
                  f"({round(c_metrics['public_mask_rate']*100, 1)}%) | "
                  f"S1: {round(trace['stage1_latency_s'], 1)}s, S2: {round(trace['stage2_latency_s'], 1)}s",
                  flush=True)

            model_results.setdefault("traces", []).append(trace)
            model_results.setdefault("char_metrics_by_doc", {})[doc_id] = c_metrics
            model_results.setdefault("telemetry", []).append({
                "doc_id": doc_id,
                "timestamp": time.time(),
                "memory": mem_telemetry
            })
            model_results["emails_completed"] = len(model_results["traces"])

            # Fix #5: Save intermediate checkpoint to caller-specific checkpoint_file with retry on transient OS swap spikes
            all_results[model] = model_results
            for _w_try in range(3):
                try:
                    tmp_ckpt = checkpoint_file.with_suffix(".tmp")
                    with open(tmp_ckpt, "w", encoding="utf-8") as f:
                        json.dump(all_results, f, indent=2, ensure_ascii=False)
                    os.replace(tmp_ckpt, checkpoint_file)
                    break
                except OSError:
                    time.sleep(2.0)

        # Fix #5: Reconstruct candidate-level audit records across ALL traces (including resumed checkpoints)
        for tr in model_results.get("traces", []):
            doc_id = tr["doc_id"]
            doc_obj = gold_docs.get(doc_id)
            if not doc_obj:
                continue
            g_spans = doc_obj.get("spans", [])
            for c in tr.get("assessed_candidates", []):
                cs, ce = c["start"], c["end"]
                overlapping_must_mask = [
                    s for s in g_spans
                    if s.get("must_mask", True) and max(cs, s["start"]) < min(ce, s["end"])
                ]
                audit_records.append({
                    "doc_id": doc_id,
                    "model": model,
                    "candidate_id": c.get("candidate_id"),
                    "text": c.get("text"),
                    "category": c.get("category"),
                    "tier": c.get("tier"),
                    "raw_score": c.get("raw_score"),
                    "calibrated_score": c.get("calibrated_score"),
                    "score_method": c.get("score_method"),
                    "verdict": c.get("verdict"),
                    "is_gold_private": (len(overlapping_must_mask) > 0),
                    "overlapping_gold_texts": [s["text"] for s in overlapping_must_mask],
                    "overlapping_gold_types": [s["type"] for s in overlapping_must_mask]
                })

        # Scorer evaluation on completed traces
        pred_dict = {}
        for tr in model_results["traces"]:
            pspans = [
                {"start": s["start"], "end": s["end"], "type": s.get("category", "SENSITIVE"), "score": s.get("raw_score", 1.0)}
                for s in tr.get("redacted_spans", [])
            ]
            pred_dict[tr["doc_id"]] = {"id": tr["doc_id"], "spans": pspans}

        scored = evaluate_score(gold_docs, pred_dict)
        model_results["scorer_metrics"] = scored

        # Aggregate character-level metrics (End-to-End across all evaluated emails)
        tot_priv_all = sum(m["total_private_chars"] for m in model_results["char_metrics_by_doc"].values())
        leaked_priv_all = sum(m["leaked_private_chars"] for m in model_results["char_metrics_by_doc"].values())
        tot_fact_all = sum(m["total_fact_chars"] for m in model_results["char_metrics_by_doc"].values())
        leaked_fact_all = sum(m["leaked_fact_chars"] for m in model_results["char_metrics_by_doc"].values())
        tot_pub_all = sum(m["total_public_chars"] for m in model_results["char_metrics_by_doc"].values())
        masked_pub_all = sum(m["masked_public_chars"] for m in model_results["char_metrics_by_doc"].values())

        # Successful-Call-Only metrics (Fix #1, Section 2.1)
        succ_doc_ids = [tr["doc_id"] for tr in model_results["traces"] if not tr.get("degraded")]
        succ_char_metrics = [model_results["char_metrics_by_doc"][did] for did in succ_doc_ids if did in model_results["char_metrics_by_doc"]]
        s_tot_priv = sum(m["total_private_chars"] for m in succ_char_metrics)
        s_leak_priv = sum(m["leaked_private_chars"] for m in succ_char_metrics)
        s_tot_pub = sum(m["total_public_chars"] for m in succ_char_metrics)
        s_mask_pub = sum(m["masked_public_chars"] for m in succ_char_metrics)

        latencies = [tr["total_latency_s"] for tr in model_results["traces"]]
        lat_s1 = [tr["stage1_latency_s"] for tr in model_results["traces"]]
        lat_s2 = [tr["stage2_latency_s"] for tr in model_results["traces"]]

        op_failures = sum(1 for tr in model_results["traces"] if tr.get("operational_failure"))
        infra_failures = sum(1 for tr in model_results["traces"] if tr.get("infrastructure_failure"))

        model_results["aggregate_summary"] = {
            "emails_evaluated": len(model_results["traces"]),
            "successful_emails": len(succ_doc_ids),
            "operational_failures": op_failures,
            "infrastructure_failures": infra_failures,
            "total_private_chars": tot_priv_all,
            "leaked_private_chars": leaked_priv_all,
            "private_character_leak_rate": round(leaked_priv_all / tot_priv_all, 4) if tot_priv_all > 0 else 0.0,
            "total_fact_chars": tot_fact_all,
            "leaked_fact_chars": leaked_fact_all,
            "fact_character_leak_rate": round(leaked_fact_all / tot_fact_all, 4) if tot_fact_all > 0 else 0.0,
            "total_public_chars": tot_pub_all,
            "masked_public_chars": masked_pub_all,
            "public_text_mask_rate": round(masked_pub_all / tot_pub_all, 4) if tot_pub_all > 0 else 0.0,
            "successful_only_private_leak_rate": round(s_leak_priv / s_tot_priv, 4) if s_tot_priv > 0 else 0.0,
            "successful_only_public_mask_rate": round(s_mask_pub / s_tot_pub, 4) if s_tot_pub > 0 else 0.0,
            "median_total_latency_s": round(float(sorted(latencies)[len(latencies)//2]), 2) if latencies else 0.0,
            "mean_total_latency_s": round(float(sum(latencies) / len(latencies)), 2) if latencies else 0.0,
            "median_stage1_s": round(float(sorted(lat_s1)[len(lat_s1)//2]), 2) if lat_s1 else 0.0,
            "median_stage2_s": round(float(sorted(lat_s2)[len(lat_s2)//2]), 2) if lat_s2 else 0.0,
            "schema_failures": sum(1 for tr in model_results["traces"] if tr.get("degraded") or len(tr.get("failures", [])) > 0)
        }

        all_results[model] = model_results
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)

    # Save final results
    with open(final_results_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nFinal benchmark results saved to {final_results_file}")

    # Save candidate audit records
    if audit_records:
        audit_file = final_results_file.with_name("calibration_fit_records_" + final_results_file.stem + ".jsonl")
        cal_prof_file = final_results_file.with_name("calibration_profile_" + final_results_file.stem + ".json")
        with open(audit_file, "w", encoding="utf-8") as f:
            for r in audit_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"Saved {len(audit_records)} candidate audit records to {audit_file}")

        # Fix #3: Fit empirical calibration (strictly excluding deterministic, omitted, and ambiguous overrides)
        excluded_methods = {
            "deterministic_policy_override",
            "omitted_fail_closed_override",
            "ambiguous_fail_closed_override",
        }
        model_evaluated_records = [
            r for r in audit_records
            if r.get("score_method") not in excluded_methods and r.get("raw_score") is not None
        ]
        policy_overrides = [
            r for r in audit_records
            if r.get("score_method") in excluded_methods
        ]
        cal_inputs = [
            {"raw_score": r["raw_score"], "is_private": r["is_gold_private"], "score_method": r.get("score_method")}
            for r in model_evaluated_records
        ]
        calibrator = EmpiricalCalibrator()
        fit_res = calibrator.fit(cal_inputs)
        eval_metrics = calibrator.evaluate_metrics(cal_inputs)

        cal_profile = {
            "version": "1.4.0",
            "fitted_date": time.strftime("%Y-%m-%d"),
            "dataset_source": f"virtual-gold-capstone/data/baseline_dev.jsonl ({len(eval_docs)} emails)",
            "audit_records_file": str(audit_file.name),
            "total_candidate_observations": len(audit_records),
            "policy_overrides_excluded_count": len(policy_overrides),
            "model_evaluated_candidates_count": len(model_evaluated_records),
            "bin_edges": calibrator.bin_edges,
            "bin_counts": calibrator.bin_counts,
            "bin_empirical_p_private": calibrator.bin_calibrated_values,
            "evaluation_metrics": eval_metrics,
            "is_fitted": True,
            "validation_status": "Empirical calibration fitted (deterministic/omitted/ambiguous overrides excluded)"
        }
        with open(cal_prof_file, "w", encoding="utf-8") as f:
            json.dump(cal_profile, f, indent=2, ensure_ascii=False)
        print(f"Saved refitted calibration profile to {cal_prof_file}")

    print("\nBENCHMARK RUN COMPLETE!")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run expanded local/cloud development benchmark")
    parser.add_argument("--models", type=str, default="llama3.1:8b,qwen3.5:9b", help="Comma-separated model names or composite specs")
    parser.add_argument("--ids", type=str, default="", help="Comma-separated email IDs (empty for default 15, or ALL for all dev emails)")
    parser.add_argument("--fresh", action="store_true", help="Start fresh without loading existing checkpoint")
    parser.add_argument("--out", type=str, default="", help="Output results JSON path")
    parser.add_argument("--stage", type=str, default="C", help="Pipeline stage: A, B0, B, C, or 1PASS")
    parser.add_argument("--use-gliner", action="store_true", help="Enable GLiNER Stage 1 encoder augmentation (Config B)")
    parser.add_argument("--gliner-model", type=str, default="urchade/gliner_multi_pii-v1", help="GLiNER HuggingFace model ID")
    parser.add_argument("--gliner-threshold", type=float, default=0.35, help="GLiNER score threshold")
    parser.add_argument("--stage2-model", type=str, default="", help="Optional Stage 2 model override (Config D)")
    parser.add_argument("--thinking", action="store_true", help="Enable hybrid reasoning/thinking mode")
    args = parser.parse_args()

    selected_models = [m.strip() for m in args.models.split(",") if m.strip()]
    selected_ids = [i.strip() for i in args.ids.split(",") if i.strip()] or DEFAULT_15_IDS
    run_benchmark(
        email_ids=selected_ids,
        models=selected_models,
        fresh=args.fresh,
        out_file=args.out if args.out else None,
        stage=args.stage,
        use_gliner=args.use_gliner,
        gliner_model=args.gliner_model,
        gliner_threshold=args.gliner_threshold,
        stage2_model=args.stage2_model if args.stage2_model else None,
        enable_thinking=args.thinking,
    )

