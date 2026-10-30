# Combined client brief: metric verification

Both October 5 rounds use the same 20 comparison documents: 2,270 labeled private and 966 labeled public characters. Preliminary character metrics, degraded counts, and latency are recomputed from recorded per_case_results.json; follow-up character metrics are recomputed from saved trace spans against original input lengths (see CLIENT_METRICS_VERIFICATION.md). No paid reruns or benchmark-code changes were made.

Baseline outputs differ across rounds: preliminary leaked 1,139 private / masked 839 public characters; follow-up leaked 1,156 / masked 652. The brief discloses this limitation and identifies each round, rather than presenting a controlled cross-round ranking.

Follow-up historical replay summaries update rates without updating original count fields. The combined table uses recorded preliminary character counts instead of mixing historical counts with replayed percentages. Cross-document span/confidence audit findings are summarized qualitatively; Brier scores are not treated as calibrated probabilities.

The table includes fallback cases. Hosted Qwen follow-up is excluded because 19/20 Stage B requests degraded. Final PDF is one page; Word document is editable. No production readiness, compliance, downstream task-quality, or network-egress guarantee is made.

## Final content audit

Revalidated all gold span offsets and text slices. Rechecked follow-up character metrics, degraded counts, and latency against saved traces. Reaggregated preliminary table counts and latency from per-document records. Verified repeatability evidence: each preliminary hosted model had non-identical outputs over three repetitions on five documents. Clarified residual leakage versus measured external disclosure, inclusion of all fallback requests, and Grok reference-only status. Stage comparisons describe observed runs rather than a controlled causal result. No production privacy guarantee is asserted.
