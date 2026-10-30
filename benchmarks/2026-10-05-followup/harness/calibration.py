"""
Calibration and Score Meaning module for Virtual Gold Capstone:
- Implements Empirical Binned Calibration (binned_empirical_v1)
- Reconciles tier thresholds with Midterm Deck Slide 11
- Calculates Expected Calibration Error (ECE) and Brier Score
- Implements Multi-Detector Agreement fallback (multi_detector_agreement_v1)
- Preserves Deterministic Policy Override (deterministic_policy_override)
"""

import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

class EmpiricalCalibrator:
    def __init__(self, bin_edges: Optional[List[float]] = None):
        if bin_edges is None:
            # 5 bins: [0.0, 0.2), [0.2, 0.4), [0.4, 0.6), [0.6, 0.8), [0.8, 1.0]
            self.bin_edges = [0.0, 0.2, 0.4, 0.6, 0.8, 1.01]
        else:
            self.bin_edges = bin_edges
        self.num_bins = len(self.bin_edges) - 1
        # Default prior is bin midpoints
        self.bin_calibrated_values = [
            (self.bin_edges[i] + self.bin_edges[i+1]) / 2.0
            for i in range(self.num_bins)
        ]
        self.bin_counts = [0] * self.num_bins
        self.is_fitted = False

    def _get_bin_index(self, score: float) -> int:
        score = max(0.0, min(1.0, float(score)))
        for i in range(self.num_bins):
            if self.bin_edges[i] <= score < self.bin_edges[i+1]:
                return i
        return self.num_bins - 1

    EXCLUDED_SCORE_METHODS = {
        "deterministic_policy_override",
        "omitted_fail_closed_override",
        "ambiguous_fail_closed_override",
    }

    def fit(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Fit empirical probability of true private within each bin.
        records: list of dicts with 'raw_score' (float) and 'is_private' (bool).
        Strictly excludes deterministic, omitted, and ambiguous policy overrides (Section 2.3).
        """
        bin_pos = [0] * self.num_bins
        bin_tot = [0] * self.num_bins

        filtered_records = [
            r for r in records
            if r.get("score_method") not in self.EXCLUDED_SCORE_METHODS
            and r.get("raw_score") is not None
        ]

        for r in filtered_records:
            score = float(r["raw_score"])
            is_priv = 1 if r.get("is_private", r.get("is_gold_private", False)) else 0
            b_idx = self._get_bin_index(score)
            bin_tot[b_idx] += 1
            bin_pos[b_idx] += is_priv

        for i in range(self.num_bins):
            midpoint = (self.bin_edges[i] + min(1.0, self.bin_edges[i+1])) / 2.0
            if bin_tot[i] >= 5:
                # Empirical rate with weak Laplace prior toward bin midpoint to prevent small-sample inversions
                emp = (bin_pos[i] + 2.0 * midpoint) / (bin_tot[i] + 2.0)
                self.bin_calibrated_values[i] = round(emp, 4)
            else:
                self.bin_calibrated_values[i] = round(midpoint, 4)

        # Enforce non-decreasing monotonicity across bins so [0.0, 0.2) never deadlocks unmasking
        for i in range(1, self.num_bins):
            if self.bin_calibrated_values[i] < self.bin_calibrated_values[i - 1]:
                self.bin_calibrated_values[i] = self.bin_calibrated_values[i - 1]

        self.bin_counts = bin_tot
        self.is_fitted = True

        return {
            "num_samples": len(filtered_records),
            "bin_edges": self.bin_edges,
            "bin_counts": self.bin_counts,
            "bin_calibrated_values": self.bin_calibrated_values
        }

    def predict(self, raw_score: float) -> Tuple[float, str]:
        """
        Maps raw_score to calibrated probability of privacy.
        """
        if not self.is_fitted:
            return round(raw_score, 4), "raw_uncalibrated"
        b_idx = self._get_bin_index(raw_score)
        return self.bin_calibrated_values[b_idx], "binned_empirical_v1"

    def evaluate_metrics(self, records: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Calculates ECE and Brier Score before and after calibration.
        """
        if not records:
            return {"ece_raw": 0.0, "ece_cal": 0.0, "brier_raw": 0.0, "brier_cal": 0.0}

        y_true = np.array([1.0 if r["is_private"] else 0.0 for r in records])
        y_raw = np.array([float(r["raw_score"]) for r in records])
        y_cal = np.array([self.predict(r["raw_score"])[0] for r in records])

        brier_raw = float(np.mean((y_raw - y_true) ** 2))
        brier_cal = float(np.mean((y_cal - y_true) ** 2))

        def calc_ece(probs, labels):
            ece = 0.0
            n = len(probs)
            for i in range(self.num_bins):
                in_bin = (probs >= self.bin_edges[i]) & (probs < self.bin_edges[i+1])
                bin_size = np.sum(in_bin)
                if bin_size > 0:
                    bin_acc = np.mean(labels[in_bin])
                    bin_conf = np.mean(probs[in_bin])
                    ece += (bin_size / n) * abs(bin_acc - bin_conf)
            return float(ece)

        return {
            "ece_raw": round(calc_ece(y_raw, y_true), 4),
            "ece_cal": round(calc_ece(y_cal, y_true), 4),
            "brier_raw": round(brier_raw, 4),
            "brier_cal": round(brier_cal, 4)
        }

    def save(self, filepath: Path):
        data = {
            "bin_edges": self.bin_edges,
            "bin_calibrated_values": self.bin_calibrated_values,
            "bin_counts": self.bin_counts,
            "is_fitted": self.is_fitted
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, filepath: Path):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.bin_edges = data["bin_edges"]
        self.bin_calibrated_values = data.get("bin_calibrated_values") or data.get("bin_empirical_p_private")
        self.bin_counts = data["bin_counts"]
        self.is_fitted = data["is_fitted"]
        self.num_bins = len(self.bin_edges) - 1

def compute_multi_detector_score(
    is_rule_hit: bool,
    is_model_det_hit: bool,
    ctx_verdict: str,
    ctx_conf: float
) -> Tuple[float, str]:
    """
    Fallback score calculation when single-model confidence does not discriminate.
    Weights evidence from regex/Presidio, model detection candidate, and contextual verdict.
    """
    w_rules = 0.40
    w_det = 0.30
    w_ctx = 0.30

    v = ctx_verdict.upper()
    ctx_prob = ctx_conf if v == "PRIVATE" else (1.0 - ctx_conf)

    score = (
        (1.0 if is_rule_hit else 0.0) * w_rules +
        (1.0 if is_model_det_hit else 0.0) * w_det +
        ctx_prob * w_ctx
    )
    return round(score, 4), "multi_detector_agreement_v1"

