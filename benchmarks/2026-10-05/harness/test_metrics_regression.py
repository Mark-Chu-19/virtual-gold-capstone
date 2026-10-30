import unittest
import numpy as np

# Import old pooled implementations
from metrics import compute_span_metrics as old_compute_span_metrics
from metrics import compute_brier_score as old_compute_brier_score

def compute_span_metrics_per_document(doc_evaluations):
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

def compute_brier_score_per_document(doc_evaluations):
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

            # Match only within THIS document!
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

class TestMetricsRegression(unittest.TestCase):
    def test_cross_document_span_leak(self):
        """
        Doc 1: Private span at [10, 20]. Preds: [] (missed).
        Doc 2: No private span. Pred at [10, 20].
        Pooled calculation erroneously matches Doc 2's pred to Doc 1's gold.
        Per-document calculation correctly yields 0 matches.
        """
        doc1 = {"doc_id": "D1", "gold_private_spans": [{"start": 10, "end": 20}], "predicted_spans": []}
        doc2 = {"doc_id": "D2", "gold_private_spans": [], "predicted_spans": [{"start": 10, "end": 20}]}

        # Old pooled behavior
        pooled_gold = doc1["gold_private_spans"] + doc2["gold_private_spans"]
        pooled_pred = doc1["predicted_spans"] + doc2["predicted_spans"]
        old_res = old_compute_span_metrics(pooled_gold, pooled_pred)
        self.assertEqual(old_res["exact_tp"], 1, "Old pooled method falsely matched across docs")

        # New per-document behavior
        new_res = compute_span_metrics_per_document([doc1, doc2])
        self.assertEqual(new_res["exact_tp"], 0, "New per-doc method correctly prevents cross-doc matching")
        self.assertEqual(new_res["exact_recall"], 0.0)
        self.assertEqual(new_res["exact_precision"], 0.0)

    def test_cross_document_brier_leak(self):
        """
        Doc 1: Gold private span at [10, 20].
        Doc 2: Gold public span at [10, 20]. Candidate at [10, 20] with score 0.1 (public).
        Pooled calculation sees candidate overlapping both Doc 1 private and Doc 2 public,
        so it falsely drops the candidate as ambiguous (returning None).
        Per-document calculation checks within Doc 2 only, correctly identifies it as public (label=0.0).
        """
        doc1 = {
            "doc_id": "D1",
            "gold_private_spans": [{"start": 10, "end": 20}],
            "gold_public_spans": [],
            "assessed_candidates": []
        }
        doc2 = {
            "doc_id": "D2",
            "gold_private_spans": [],
            "gold_public_spans": [{"start": 10, "end": 20}],
            "assessed_candidates": [{"start": 10, "end": 20, "raw_score": 0.10}]
        }

        # Old pooled behavior: cand matched both doc1 priv and doc2 pub -> dropped (None)
        old_brier = old_compute_brier_score(
            doc2["assessed_candidates"],
            doc1["gold_private_spans"],
            doc2["gold_public_spans"]
        )
        self.assertIsNone(old_brier, "Old pooled calculation corrupted evaluation and dropped candidate")

        # New per-doc behavior: cand matches gold_pub in doc2 -> label=0.0 -> error = (0.1 - 0.0)^2 = 0.01
        new_res = compute_brier_score_per_document([doc1, doc2])
        self.assertAlmostEqual(new_res["brier_score"], 0.01, places=2)
        self.assertEqual(new_res["evaluated_candidates"], 1)
        self.assertEqual(new_res["excluded_candidates"], 0)

if __name__ == "__main__":
    unittest.main()
