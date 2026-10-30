"""
Metrics module for Virtual Gold Privacy Redaction Benchmark (V2).
Implements strictly per-document span matching and Brier score evaluation to prevent
cross-document offset contamination.
"""

from typing import List, Dict, Any, Optional
import numpy as np

def compute_character_masks(
    text_length: int,
    private_spans: List[Dict[str, Any]],
    public_spans: List[Dict[str, Any]],
    redaction_spans: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Computes boolean character masks for a single document:
    - is_private[i]: True if index i is in a gold private span
    - is_public[i]: True if index i is in a gold public span
    - is_masked[i]: True if index i is covered by a redaction span
    """
    is_private = [False] * text_length
    is_public = [False] * text_length
    is_masked = [False] * text_length
    
    tier_map = ["NONE"] * text_length
    category_map = ["NONE"] * text_length

    for s in private_spans:
        start, end = s["start"], s["end"]
        tier = s.get("tier", "MEDIUM")
        cat = s.get("category", "UNKNOWN")
        for i in range(max(0, start), min(text_length, end)):
            is_private[i] = True
            tier_map[i] = tier
            category_map[i] = cat

    for s in public_spans:
        start, end = s["start"], s["end"]
        for i in range(max(0, start), min(text_length, end)):
            is_public[i] = True

    for s in redaction_spans:
        start, end = s["start"], s["end"]
        for i in range(max(0, start), min(text_length, end)):
            is_masked[i] = True

    total_private_chars = sum(is_private)
    total_public_chars = sum(is_public)
    
    leaked_private_chars = sum(1 for i in range(text_length) if is_private[i] and not is_masked[i])
    masked_public_chars = sum(1 for i in range(text_length) if is_public[i] and is_masked[i])
    
    tier_counts = {"HIGH": {"total": 0, "leaked": 0},
                   "MEDIUM": {"total": 0, "leaked": 0},
                   "LOW": {"total": 0, "leaked": 0}}
    
    for i in range(text_length):
        if is_private[i]:
            t = tier_map[i]
            if t in tier_counts:
                tier_counts[t]["total"] += 1
                if not is_masked[i]:
                    tier_counts[t]["leaked"] += 1

    return {
        "text_length": text_length,
        "total_private_chars": total_private_chars,
        "leaked_private_chars": leaked_private_chars,
        "leak_rate_chars": (leaked_private_chars / total_private_chars) if total_private_chars > 0 else 0.0,
        "has_leak": leaked_private_chars > 0,
        "total_public_chars": total_public_chars,
        "masked_public_chars": masked_public_chars,
        "over_redaction_rate_chars": (masked_public_chars / total_public_chars) if total_public_chars > 0 else 0.0,
        "tier_breakdown": tier_counts
    }

def compute_span_metrics_per_document(
    doc_evaluations: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Computes exact-match and overlap-match precision and recall strictly per document,
    then aggregates counts across all documents.
    """
    total_exact_tp = 0
    total_overlap_gold_hits = 0
    total_overlap_pred_hits = 0
    total_gold_spans = 0
    total_pred_spans = 0

    for doc in doc_evaluations:
        gold = doc.get("gold_private_spans", [])
        pred = doc.get("predicted_spans", [])
        total_gold_spans += len(gold)
        total_pred_spans += len(pred)

        matched_preds = set()
        for g in gold:
            for i, p in enumerate(pred):
                if i not in matched_preds and p["start"] == g["start"] and p["end"] == g["end"]:
                    total_exact_tp += 1
                    matched_preds.add(i)
                    break

        for g in gold:
            for p in pred:
                if max(g["start"], p["start"]) < min(g["end"], p["end"]):
                    total_overlap_gold_hits += 1
                    break

        for p in pred:
            for g in gold:
                if max(g["start"], p["start"]) < min(g["end"], p["end"]):
                    total_overlap_pred_hits += 1
                    break

    exact_prec = (total_exact_tp / total_pred_spans) if total_pred_spans > 0 else 0.0
    exact_rec = (total_exact_tp / total_gold_spans) if total_gold_spans > 0 else 0.0
    overlap_rec = (total_overlap_gold_hits / total_gold_spans) if total_gold_spans > 0 else 0.0
    overlap_prec = (total_overlap_pred_hits / total_pred_spans) if total_pred_spans > 0 else 0.0

    return {
        "gold_spans_count": total_gold_spans,
        "pred_spans_count": total_pred_spans,
        "exact_tp": total_exact_tp,
        "exact_precision": exact_prec,
        "exact_recall": exact_rec,
        "overlap_precision": overlap_prec,
        "overlap_recall": overlap_rec
    }

def compute_brier_score_per_document(
    doc_evaluations: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Evaluates candidate scores strictly against THAT document's gold spans.
    Candidate-only evaluation: reports candidate coverage (evaluated vs excluded).
    """
    scores = []
    labels = []
    total_assessed = 0

    for doc in doc_evaluations:
        gold_priv = doc.get("gold_private_spans", [])
        gold_pub = doc.get("gold_public_spans", [])
        candidates = doc.get("assessed_candidates", [])
        
        for cand in candidates:
            raw_score = cand.get("raw_score")
            if raw_score is None:
                continue
            total_assessed += 1
            c_s, c_e = cand["start"], cand["end"]

            is_priv = any(max(c_s, g["start"]) < min(c_e, g["end"]) for g in gold_priv)
            is_pub = any(max(c_s, g["start"]) < min(c_e, g["end"]) for g in gold_pub)

            if is_priv and not is_pub:
                scores.append(float(raw_score))
                labels.append(1.0)
            elif is_pub and not is_priv:
                scores.append(float(raw_score))
                labels.append(0.0)

    evaluated_cnt = len(scores)
    excluded_cnt = total_assessed - evaluated_cnt
    brier = float(np.mean([(s - y) ** 2 for s, y in zip(scores, labels)])) if evaluated_cnt > 0 else None

    return {
        "brier_score": brier,
        "total_assessed_candidates": total_assessed,
        "evaluated_candidates": evaluated_cnt,
        "excluded_candidates": excluded_cnt
    }
