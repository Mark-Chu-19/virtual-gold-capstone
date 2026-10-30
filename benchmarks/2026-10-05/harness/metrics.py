"""
Metrics calculation module for privacy redaction evaluation.
Covers character-level leakage, request-level leakage, over-redaction,
span-level precision/recall, tier breakdowns, and Brier score.
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np

def compute_character_masks(
    text_length: int,
    private_spans: List[Dict[str, Any]],
    public_spans: List[Dict[str, Any]],
    redaction_spans: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Computes boolean masks of length text_length for exact character tracking:
    - is_private[i]: True if index i is in a gold private span
    - is_public[i]: True if index i is in a gold public span
    - is_masked[i]: True if index i is covered by a redaction span
    """
    is_private = [False] * text_length
    is_public = [False] * text_length
    is_masked = [False] * text_length
    
    # Track which tier each private char belongs to
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
    
    # Tier breakdowns
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

def compute_span_metrics(
    gold_private_spans: List[Dict[str, Any]],
    predicted_spans: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Computes exact-match and overlap-match precision and recall at the span level.
    """
    n_gold = len(gold_private_spans)
    n_pred = len(predicted_spans)
    
    if n_gold == 0 and n_pred == 0:
        return {
            "gold_spans_count": 0,
            "pred_spans_count": 0,
            "exact_tp": 0,
            "overlap_tp": 0,
            "exact_precision": 1.0,
            "exact_recall": 1.0,
            "overlap_precision": 1.0,
            "overlap_recall": 1.0
        }
    if n_gold == 0:
        return {
            "gold_spans_count": 0,
            "pred_spans_count": n_pred,
            "exact_tp": 0,
            "overlap_tp": 0,
            "exact_precision": 0.0,
            "exact_recall": 1.0,
            "overlap_precision": 0.0,
            "overlap_recall": 1.0
        }
    if n_pred == 0:
        return {
            "gold_spans_count": n_gold,
            "pred_spans_count": 0,
            "exact_tp": 0,
            "overlap_tp": 0,
            "exact_precision": 0.0,
            "exact_recall": 0.0,
            "overlap_precision": 0.0,
            "overlap_recall": 0.0
        }

    # Exact matches
    exact_tp = 0
    matched_preds = set()
    for g in gold_private_spans:
        for i, p in enumerate(predicted_spans):
            if i not in matched_preds and p["start"] == g["start"] and p["end"] == g["end"]:
                exact_tp += 1
                matched_preds.add(i)
                break

    # Overlap matches (intersection > 0)
    overlap_gold_hits = 0
    for g in gold_private_spans:
        for p in predicted_spans:
            if max(g["start"], p["start"]) < min(g["end"], p["end"]):
                overlap_gold_hits += 1
                break

    overlap_pred_hits = 0
    for p in predicted_spans:
        for g in gold_private_spans:
            if max(g["start"], p["start"]) < min(g["end"], p["end"]):
                overlap_pred_hits += 1
                break

    return {
        "gold_spans_count": n_gold,
        "pred_spans_count": n_pred,
        "exact_tp": exact_tp,
        "exact_precision": exact_tp / n_pred,
        "exact_recall": exact_tp / n_gold,
        "overlap_recall": overlap_gold_hits / n_gold,
        "overlap_precision": overlap_pred_hits / n_pred
    }

def compute_brier_score(
    candidate_assessments: List[Dict[str, Any]],
    gold_private_spans: List[Dict[str, Any]],
    gold_public_spans: List[Dict[str, Any]]
) -> Optional[float]:
    """
    Computes Brier score (MSE between raw probability and binary truth)
    for assessed candidate spans that overlap known gold private (1.0) or public (0.0) spans.
    """
    scores = []
    labels = []
    
    for cand in candidate_assessments:
        raw_score = cand.get("raw_score")
        if raw_score is None:
            continue
        c_s, c_e = cand["start"], cand["end"]
        # Check if overlaps gold private
        is_priv = any(max(c_s, g["start"]) < min(c_e, g["end"]) for g in gold_private_spans)
        # Check if overlaps gold public
        is_pub = any(max(c_s, g["start"]) < min(c_e, g["end"]) for g in gold_public_spans)
        
        if is_priv and not is_pub:
            scores.append(float(raw_score))
            labels.append(1.0)
        elif is_pub and not is_priv:
            scores.append(float(raw_score))
            labels.append(0.0)

    if not scores:
        return None
    
    mse = float(np.mean([(s - y) ** 2 for s, y in zip(scores, labels)]))
    return mse
