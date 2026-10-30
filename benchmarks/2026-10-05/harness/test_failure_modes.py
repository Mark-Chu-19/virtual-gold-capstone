import unittest
from pipeline import run_experiment_pipeline, restore_text, parse_json_safely, align_model_candidates
from detectors import run_baseline_detection

class MockFailingClient:
    def __init__(self, failure_type="unavailable"):
        self.failure_type = failure_type

    def chat_completion(self, model, messages, **kwargs):
        if self.failure_type == "unavailable":
            return {
                "model_requested": model,
                "model_returned": None,
                "provider": None,
                "latency_s": 0.05,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost_usd": 0.0,
                "attempts": 3,
                "success": False,
                "error": "HTTP 503: Service Unavailable",
                "content": None
            }
        elif self.failure_type == "malformed":
            return {
                "model_requested": model,
                "model_returned": model,
                "provider": "MockProvider",
                "latency_s": 0.05,
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "cost_usd": 0.0001,
                "attempts": 1,
                "success": True,
                "error": None,
                "content": "This is definitely not JSON { broken ..."
            }

class TestFailureModes(unittest.TestCase):
    def setUp(self):
        self.sample_doc = {
            "id": "DOC-TEST-FAIL",
            "task": "Test failure fallback",
            "text": "Call me at 415-555-0182 or email contact@example.com."
        }

    def test_unavailable_inference_fallback(self):
        """When remote inference is unavailable, fallback masks baseline candidates and marks degraded."""
        client = MockFailingClient(failure_type="unavailable")
        trace = run_experiment_pipeline(self.sample_doc, client, "mock-model", stage="C")
        
        self.assertTrue(trace["degraded"])
        self.assertIn("Stage 1 Call Failed", trace["degraded_reason"])
        self.assertGreater(len(trace["redacted_spans"]), 0) # Fallback masked baseline candidates
        # Redacted text contains placeholders
        self.assertIn("[PHONE_", trace["redacted_text"])
        self.assertIn("[EMAIL_", trace["redacted_text"])

    def test_malformed_output_fallback(self):
        """When model outputs malformed JSON, fallback triggers and marks degraded."""
        client = MockFailingClient(failure_type="malformed")
        trace = run_experiment_pipeline(self.sample_doc, client, "mock-model", stage="C")
        
        self.assertTrue(trace["degraded"])
        self.assertEqual(trace["degraded_reason"], "Stage 1 Unparseable JSON output")
        self.assertGreater(len(trace["redacted_spans"]), 0)

    def test_restoration_and_unknown_token_flagging(self):
        """Restoration restores issued tokens and flags unissued / unknown tokens."""
        text = "Hello [PERSON_1], call [PHONE_1] or [PHONE_99] (fake)."
        placeholder_map = {
            "[PERSON_1]": "Alice",
            "[PHONE_1]": "415-555-0199"
        }
        restored, unissued = restore_text(text, placeholder_map)
        
        self.assertEqual(restored, "Hello Alice, call 415-555-0199 or [PHONE_99] (fake).")
        self.assertIn("[PHONE_99]", unissued)
        self.assertEqual(len(unissued), 1)

    def test_discard_invalid_substring(self):
        """Model hallucinating substrings not present in document text are safely discarded."""
        raw_candidates = [
            {"text": "415-555-0182", "category": "PHONE"}, # exists
            {"text": "John Doe", "category": "PERSON"}       # does not exist
        ]
        spans, valid_cnt, discarded_cnt = align_model_candidates(raw_candidates, self.sample_doc["text"])
        self.assertEqual(valid_cnt, 1)
        self.assertEqual(discarded_cnt, 1)
        self.assertEqual(spans[0]["text"], "415-555-0182")

if __name__ == "__main__":
    unittest.main()
