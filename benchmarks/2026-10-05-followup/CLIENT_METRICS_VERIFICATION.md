# Client brief metric verification — October 5, 2026

The reviewed brief recalculates character-level metrics from preserved follow-up response traces and original test text / gold annotations. No model reruns or benchmark-code changes were made.

The follow-up compilation script uses redacted output length when gold annotations lack a `text` field. Redaction spans still use original-input offsets. That combination truncates evaluation masks and changes denominators across configurations. The corrected comparison uses all 2,270 labeled private characters and 966 labeled public characters for every configuration. All 20 document IDs and span boundaries were checked; rule-only spans were identical across configurations.

Verified counts (private leaked; public masked; documents with any leak): rules + Presidio 1,156; 652; 15/20. Local Qwen B 803; 662; 14/20. Local Qwen C 1,430; 0; 15/20. Hosted Gemma B 657; 841; 11/20. Hosted Gemma C 1,129; 60; 15/20. Hosted Qwen B 1,109; 652; 15/20, but 19/20 requests degraded; excluded from the client comparison. Latency medians come from recorded total latencies. Gemma C includes its one degraded request.

Historical tables also contain rates that disagree with their displayed counts. The reviewed brief therefore uses the same follow-up traces for its baseline and model comparisons, rather than combining inconsistent historical fields. Local residency, network egress, compliance, production hardware throughput, and downstream utility were not independently validated by this metric audit; the brief avoids those guarantees.

Machine-readable calculations: `client_verified_metrics.json`.
