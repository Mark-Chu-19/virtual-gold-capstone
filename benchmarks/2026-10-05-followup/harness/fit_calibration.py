#!/usr/bin/env python3
"""
Fit empirical score calibration on candidate traces against gold annotations in baseline_dev.jsonl.
Strictly intersects each candidate span with ground truth gold must_mask spans.
Saves:
- calibration_fit_records.jsonl (complete candidate-level audit records)
- calibration_profile_v1.json (fitted empirical calibration parameters)
"""

import json
from pathlib import Path
from typing import List, Dict, Any

harness_dir = Path(__file__).resolve().parent
config_dir = harness_dir.parent / "config"
config_dir.mkdir(parents=True, exist_ok=True)

gold_path = harness_dir.parent.parent.parent / "data" / "baseline_dev.jsonl"
comp_results_path = harness_dir.parent / "results" / "local_m4_model_comparison.json"

from calibration import EmpiricalCalibrator

def fit_calibration():
    gold = {json.loads(line)["id"]: json.loads(line) for line in open(gold_path, encoding="utf-8") if line.strip()}
    
    if not comp_results_path.exists():
        print(f"Comparison results not found at {comp_results_path}")
        return

    comp_data = json.load(open(comp_results_path, encoding="utf-8"))
    
    fit_records = []
    
    for model_name, m_data in comp_data.items():
        traces = m_data.get("traces", [])
        for tr in traces:
            eid = tr["doc_id"]
            if eid not in gold:
                continue
            g_doc = gold[eid]
            g_spans = g_doc["spans"]
            
            for c in tr.get("assessed_candidates", []):
                cs, ce = c["start"], c["end"]
                # Determine ground truth private status by interval intersection
                overlapping_must_mask = [
                    s for s in g_spans
                    if s.get("must_mask", True) and max(cs, s["start"]) < min(ce, s["end"])
                ]
                is_gold_private = len(overlapping_must_mask) > 0
                
                record = {
                    "doc_id": eid,
                    "model": model_name,
                    "candidate_id": c.get("candidate_id"),
                    "text": c.get("text"),
                    "category": c.get("category"),
                    "tier": c.get("tier"),
                    "raw_score": c.get("raw_score"),
                    "verdict": c.get("verdict"),
                    "is_gold_private": is_gold_private,
                    "overlapping_gold_texts": [s["text"] for s in overlapping_must_mask],
                    "overlapping_gold_types": [s["type"] for s in overlapping_must_mask]
                }
                fit_records.append(record)

    # Save candidate-level audit records
    records_file = config_dir / "calibration_fit_records.jsonl"
    with open(records_file, "w", encoding="utf-8") as f:
        for r in fit_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            
    print(f"Saved {len(fit_records)} audited candidate records to {records_file}")

    # Prepare inputs for EmpiricalCalibrator
    cal_inputs = [
        {"raw_score": r["raw_score"], "is_private": r["is_gold_private"]}
        for r in fit_records
    ]

    calibrator = EmpiricalCalibrator()
    fit_summary = calibrator.fit(cal_inputs)
    
    eval_metrics = calibrator.evaluate_metrics(cal_inputs)
    
    profile_data = {
        "version": "1.1.0",
        "fitted_date": "2026-10-19",
        "dataset_source": "virtual-gold-capstone/data/baseline_dev.jsonl",
        "audit_records_file": str(records_file.name),
        "total_candidate_observations": len(fit_records),
        "bin_edges": calibrator.bin_edges,
        "bin_counts": calibrator.bin_counts,
        "bin_empirical_p_private": calibrator.bin_calibrated_values,
        "evaluation_metrics": eval_metrics,
        "is_fitted": True,
        "validation_status": "Pilot fitted; full development benchmark expansion pending",
        "tier_thresholds": {
            "HIGH": 0.20,
            "MEDIUM": 0.50,
            "LOW": 0.50
        },
        "deterministic_lock_policy": {
            "rule": "High-tier match from regex or presidio sets score_method='deterministic_policy_override', calibrated_score=null",
            "bypasses_contextual_unmasking": True
        },
        "fallback_policy": {
            "method": "multi_detector_agreement_v1",
            "weights": {"rules": 0.40, "model_detection": 0.30, "contextual": 0.30},
            "activation": "Activated on rule/context conflict or score ambiguity (0.35 <= raw_score <= 0.65)",
            "fail_closed_default": "STAGE_B_CANDIDATE_UNION"
        }
    }

    profile_file = config_dir / "calibration_profile_v1.json"
    with open(profile_file, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, indent=2, ensure_ascii=False)

    print(f"Saved updated calibration profile to {profile_file}")
    print("Fit summary:", json.dumps(fit_summary, indent=2))
    print("Metrics:", json.dumps(eval_metrics, indent=2))

if __name__ == "__main__":
    fit_calibration()

