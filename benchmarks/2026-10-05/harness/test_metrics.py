import unittest
from metrics import compute_character_masks, compute_span_metrics, compute_brier_score

class TestMetricsValidation(unittest.TestCase):
    def test_complete_mask(self):
        """Case 1: Gold private span is completely masked."""
        text_len = 50
        priv = [{"start": 10, "end": 20, "tier": "MEDIUM", "category": "PHONE"}]
        pub = []
        redact = [{"start": 10, "end": 20}]
        
        res = compute_character_masks(text_len, priv, pub, redact)
        self.assertEqual(res["total_private_chars"], 10)
        self.assertEqual(res["leaked_private_chars"], 0)
        self.assertEqual(res["leak_rate_chars"], 0.0)
        self.assertFalse(res["has_leak"])
        self.assertEqual(res["tier_breakdown"]["MEDIUM"]["leaked"], 0)

    def test_missed_span(self):
        """Case 2: Gold private span is completely unmasked."""
        text_len = 50
        priv = [{"start": 10, "end": 20, "tier": "HIGH", "category": "SECRET"}]
        pub = []
        redact = []
        
        res = compute_character_masks(text_len, priv, pub, redact)
        self.assertEqual(res["total_private_chars"], 10)
        self.assertEqual(res["leaked_private_chars"], 10)
        self.assertEqual(res["leak_rate_chars"], 1.0)
        self.assertTrue(res["has_leak"])
        self.assertEqual(res["tier_breakdown"]["HIGH"]["leaked"], 10)

    def test_partial_mask(self):
        """Case 3: Gold private span is partially masked (residual leakage)."""
        text_len = 50
        priv = [{"start": 10, "end": 20, "tier": "MEDIUM", "category": "PHONE"}]
        pub = []
        redact = [{"start": 10, "end": 15}] # only 5 of 10 chars masked
        
        res = compute_character_masks(text_len, priv, pub, redact)
        self.assertEqual(res["total_private_chars"], 10)
        self.assertEqual(res["leaked_private_chars"], 5)
        self.assertEqual(res["leak_rate_chars"], 0.5)
        self.assertTrue(res["has_leak"])
        self.assertEqual(res["tier_breakdown"]["MEDIUM"]["leaked"], 5)

    def test_over_redaction(self):
        """Case 4: Public span is unnecessarily masked."""
        text_len = 100
        priv = []
        pub = [{"start": 30, "end": 45, "category": "PHONE"}] # 15 chars
        redact = [{"start": 30, "end": 45}]
        
        res = compute_character_masks(text_len, priv, pub, redact)
        self.assertEqual(res["total_public_chars"], 15)
        self.assertEqual(res["masked_public_chars"], 15)
        self.assertEqual(res["over_redaction_rate_chars"], 1.0)
        self.assertEqual(res["leaked_private_chars"], 0)

    def test_span_metrics(self):
        """Span level precision, recall, exact match, overlap match."""
        gold = [{"start": 10, "end": 20}, {"start": 30, "end": 40}]
        # Pred 1 matches gold 1 exactly; Pred 2 overlaps gold 2 partially [32, 42]; Pred 3 is false positive [60, 70]
        preds = [{"start": 10, "end": 20}, {"start": 32, "end": 42}, {"start": 60, "end": 70}]
        
        m = compute_span_metrics(gold, preds)
        self.assertEqual(m["gold_spans_count"], 2)
        self.assertEqual(m["pred_spans_count"], 3)
        self.assertEqual(m["exact_tp"], 1)
        self.assertAlmostEqual(m["exact_precision"], 1 / 3)
        self.assertAlmostEqual(m["exact_recall"], 1 / 2)
        self.assertEqual(m["overlap_recall"], 1.0) # both gold spans overlapped
        self.assertAlmostEqual(m["overlap_precision"], 2 / 3)

    def test_brier_score(self):
        """Brier score MSE calculation."""
        gold_priv = [{"start": 10, "end": 20}]
        gold_pub = [{"start": 50, "end": 60}]
        
        assessments = [
            {"start": 10, "end": 20, "raw_score": 0.8}, # priv (y=1), err = 0.2, err^2 = 0.04
            {"start": 50, "end": 60, "raw_score": 0.2}  # pub (y=0), err = 0.2, err^2 = 0.04
        ]
        brier = compute_brier_score(assessments, gold_priv, gold_pub)
        self.assertAlmostEqual(brier, 0.04)

if __name__ == "__main__":
    unittest.main()
