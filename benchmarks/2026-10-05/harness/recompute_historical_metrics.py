"""
Recomputes corrected metrics for historical runs from saved raw responses.
Uses the corrected per-document span matching and per-document Brier score calculations.
Preserves original summary_metrics.json and saves corrected_summary_metrics.json.
"""

import json
import sys
from pathlib import Path
import numpy as np

BENCHMARK_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BENCHMARK_DIR / "harness"))

from detectors import run_baseline_detection, merge_and_deduplicate_spans
from pipeline import parse_json_safely, align_model_candidates, apply_redaction, get_tier_for_category, TIER_THRESHOLDS
from metrics import compute_character_masks
from test_metrics_regression import compute_span_metrics_per_document, compute_brier_score_per_document

def load_data():
    with open(BENCHMARK_DIR / "data" / "synthetic_documents_dev.json") as f:
        dev_docs = {d["id"]: d for d in json.load(f)}
    with open(BENCHMARK_DIR / "data" / "synthetic_documents_test.json") as f:
        test_docs = {d["id"]: d for d in json.load(f)}
    with open(BENCHMARK_DIR / "data" / "gold_annotations_dev.json") as f:
        dev_gold = {d["id"]: d for d in json.load(f)}
    with open(BENCHMARK_DIR / "data" / "gold_annotations_test.json") as f:
        test_gold = {d["id"]: d for d in json.load(f)}
    return dev_docs, test_docs, dev_gold, test_gold

def replay_case(doc, raw_file, stage):
    text = doc["text"]
    baseline_spans = run_baseline_detection(text)

    if stage == "A":
        redacted_text, p_map = apply_redaction(text, baseline_spans)
        return {
            "redacted_spans": baseline_spans,
            "assessed_candidates": [],
            "degraded": False
        }

    with open(raw_file) as f:
        raw_data = json.load(f)

    # Stage 1 replay
    stage1_content = raw_data.get("stage1_raw")
    parsed_s1 = parse_json_safely(stage1_content)
    if not parsed_s1 or "candidates" not in parsed_s1:
        # Fallback to baseline
        redacted_text, p_map = apply_redaction(text, baseline_spans)
        return {
            "redacted_spans": baseline_spans,
            "assessed_candidates": [],
            "degraded": True
        }

    model_spans, _, _ = align_model_candidates(parsed_s1.get("candidates", []), text)
    union_spans = merge_and_deduplicate_spans(baseline_spans + model_spans, text)

    if stage == "B":
        redacted_text, p_map = apply_redaction(text, union_spans)
        return {
            "redacted_spans": union_spans,
            "assessed_candidates": [],
            "degraded": False
        }

    # Stage C replay
    if not union_spans:
        return {"redacted_spans": [], "assessed_candidates": [], "degraded": False}

    stage2_content = raw_data.get("stage2_raw")
    parsed_s2 = parse_json_safely(stage2_content)
    if not parsed_s2 or "assessments" not in parsed_s2:
        redacted_text, p_map = apply_redaction(text, union_spans)
        return {
            "redacted_spans": union_spans,
            "assessed_candidates": [],
            "degraded": True
        }

    assessments_by_id = {a["candidate_id"]: a for a in parsed_s2.get("assessments", []) if a.get("candidate_id") is not None}
    
    spans_to_redact = []
    assessed_records = []
    for i, s in enumerate(union_spans):
        a = assessments_by_id.get(i)
        cat = s.get("category", "MEDIUM")
        tier = get_tier_for_category(cat)
        threshold = TIER_THRESHOLDS.get(tier, 0.50)

        if a:
            verdict = a.get("verdict", "PRIVATE").upper()
            conf = float(a.get("confidence", 0.50))
            p_priv = conf if verdict == "PRIVATE" else (1.0 - conf)
            reason = a.get("reasoning", "")
        else:
            verdict = "PRIVATE"
            p_priv = 1.0
            reason = "Omitted candidate; fallback"

        should_redact = (p_priv >= threshold)
        if should_redact:
            spans_to_redact.append(s)

        assessed_records.append({
            "candidate_id": i,
            "start": s["start"],
            "end": s["end"],
            "text": s["text"],
            "category": cat,
            "tier": tier,
            "threshold": threshold,
            "verdict": verdict,
            "raw_score": p_priv,
            "should_redact": should_redact,
            "reasoning": reason
        })

    return {
        "redacted_spans": spans_to_redact,
        "assessed_candidates": assessed_records,
        "degraded": False
    }

def main():
    dev_docs, test_docs, dev_gold, test_gold = load_data()
    raw_dir = BENCHMARK_DIR / "results" / "raw_responses"

    with open(BENCHMARK_DIR / "results" / "summary_metrics.json") as f:
        old_summaries = json.load(f)

    corrected_summaries = []

    for old_s in old_summaries:
        model = old_s["model"]
        stage = old_s["stage"]
        split = old_s["split"]

        docs_map = dev_docs if split == "dev" else test_docs
        gold_map = dev_gold if split == "dev" else test_gold

        doc_eval_spans = []
        doc_eval_brier = []

        total_priv_chars = 0
        total_leaked_chars = 0
        total_pub_chars = 0
        total_over_redacted_chars = 0
        requests_with_leak = 0
        tier_totals = {"HIGH": {"total": 0, "leaked": 0},
                       "MEDIUM": {"total": 0, "leaked": 0},
                       "LOW": {"total": 0, "leaked": 0}}

        for doc_id, doc in docs_map.items():
            gold = gold_map[doc_id]
            gold_priv = gold["private_spans"]
            gold_pub = gold["public_spans"]

            raw_file = raw_dir / f"{doc_id}_{model.replace('/', '_')}_stage{stage}.json"
            res = replay_case(doc, raw_file, stage)

            # Character masks
            char_res = compute_character_masks(len(doc["text"]), gold_priv, gold_pub, res["redacted_spans"])
            total_priv_chars += char_res["total_private_chars"]
            total_leaked_chars += char_res["leaked_private_chars"]
            total_pub_chars += char_res["total_public_chars"]
            total_over_redacted_chars += char_res["masked_public_chars"]
            if char_res["has_leak"]:
                requests_with_leak += 1

            for t in ["HIGH", "MEDIUM", "LOW"]:
                tier_totals[t]["total"] += char_res["tier_breakdown"][t]["total"]
                tier_totals[t]["leaked"] += char_res["tier_breakdown"][t]["leaked"]

            # Per-doc spans
            doc_eval_spans.append({
                "doc_id": doc_id,
                "gold_private_spans": gold_priv,
                "predicted_spans": res["redacted_spans"]
            })

            # Per-doc Brier
            if stage == "C":
                doc_eval_brier.append({
                    "doc_id": doc_id,
                    "gold_private_spans": gold_priv,
                    "gold_public_spans": gold_pub,
                    "assessed_candidates": res["assessed_candidates"]
                })

        corrected_spans = compute_span_metrics_per_document(doc_eval_spans)
        corrected_brier = compute_brier_score_per_document(doc_eval_brier) if stage == "C" else None

        new_s = dict(old_s)
        new_s["char_leak_rate"] = total_leaked_chars / total_priv_chars if total_priv_chars > 0 else 0.0
        new_s["request_leak_rate"] = requests_with_leak / len(docs_map)
        new_s["char_over_redaction_rate"] = total_over_redacted_chars / total_pub_chars if total_pub_chars > 0 else 0.0
        new_s["span_metrics_corrected"] = corrected_spans
        new_s["brier_corrected"] = corrected_brier
        corrected_summaries.append(new_s)

    with open(BENCHMARK_DIR / "results" / "corrected_summary_metrics.json", "w") as f:
        json.dump(corrected_summaries, f, indent=2)

    print("=== RECOMPUTED HISTORICAL METRICS SUMMARY ===")
    header = "%-25s | %-3s | %-5s | %-7s | %-7s | %-9s | %-9s | %-8s | %-8s | %-12s" % (
        "Model", "Stg", "Split", "PrivLk%", "OvRed%", "OldSpRec", "NewSpRec", "OldSpPrec", "NewSpPrec", "NewBrier(eval/tot)"
    )
    print(header)
    print("-" * len(header))
    for s in corrected_summaries:
        m = s["model"].split("/")[-1]
        stg = s["stage"]
        spl = s["split"]
        priv_lk = "%.1f%%" % (s["char_leak_rate"] * 100)
        ov_red = "%.1f%%" % (s["char_over_redaction_rate"] * 100)
        old_rec = "%.2f" % s["span_metrics"]["exact_recall"]
        new_rec = "%.2f" % s["span_metrics_corrected"]["exact_recall"]
        old_prec = "%.2f" % s["span_metrics"]["exact_precision"]
        new_prec = "%.2f" % s["span_metrics_corrected"]["exact_precision"]
        bc = s.get("brier_corrected")
        if bc and bc["brier_score"] is not None:
            brier_str = "%.3f (%d/%d)" % (bc["brier_score"], bc["evaluated_candidates"], bc["total_assessed_candidates"])
        else:
            brier_str = "N/A"
        print("%-25s | %-3s | %-5s | %-7s | %-7s | %-9s | %-9s | %-8s | %-8s | %-12s" % (
            m, stg, spl, priv_lk, ov_red, old_rec, new_rec, old_prec, new_prec, brier_str
        ))

if __name__ == "__main__":
    main()
