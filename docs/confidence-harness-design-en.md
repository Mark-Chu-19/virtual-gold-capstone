# Confidence Scoring & Evaluation Harness — Design

**Capstone · Virtual Gold Inc · Week 3 · Confidence-scoring work package**

Extends [architecture-v0.3-en.md](architecture-v0.3-en.md) §5 (Confidence scoring) and §7 (Evaluation design and datasets) with an 8B-scale literature review and a concrete harness design. This document is the basis for the `feat/harness-*` and `eval/*` branches described in §6 below.

| Version | Date | Status | Author |
|---|---|---|---|
| v0.1 | 2026-09-14 | Draft, for team review | Zhexuan Ye |
| v0.2 | 2026-09-15 | Revised per Mark's review: inference-stack prerequisite for the SEP variant, six-metrics framing aligned with architecture §7, A/B/C renamed signal variants, midpoint pilot split out, TruthfulQA scope narrowed | Zhexuan Ye |

---

## 1. Why this document exists

Architecture v0.3 §5 lists five candidate confidence strategies (token probability, self-consistency, verifier model, retrieval grounding, task heuristics) and recommends starting the MVP with token probability plus task heuristics, without citing scale-specific evidence. This document narrows that recommendation using literature tested at or near our target scale (Llama 3.1 8B / Qwen3 8B), and turns architecture v0.3 §7's three-configuration evaluation design into a runnable harness.

Three questions this document answers:

1. Which confidence signals have real (not extrapolated) evidence at 8B scale?
2. How many extra inferences does each cost, so the harness reports both the accuracy gain and the compute price?
3. How do we get architecture v0.3 §7's three system configurations, plus per-variant confidence metrics, out of a single sampling pass instead of separate evaluation runs?

## 2. Signal landscape at 8B scale

| Signal | Extra local generations / query | Extra auxiliary-model calls | One-time cost | 8B-scale evidence |
|---|---|---|---|---|
| Token probability / softmax | 0 | 0 | none | Direct: small-model AUROC 0.71–0.87 |
| Verbalized confidence (in-line) | 0 | 0 | none | Direct: **broken** at 8B — saturates to near-constant "very confident" |
| Verbalized confidence (follow-up prompt) | 1 | 0 | none | No 8B test; inferred from capability trend |
| Semantic Entropy Probe (SEP) | 0 at inference\* | 0 | one probe-training pass | Smallest tested: 7B (Llama-2-7B, Mistral-7B); no 8B-specific ablation |
| P(True) / P(IK) | ≥1 | 0 | none | No 8B test (800M/3B/12B/52B only); scale trend suggests worse OOD generalization |
| Self-consistency | k−1 (saturates ~5–10 samples) | 0 | none | No 8B test (20B–540B only); smaller-model gains reduced |
| Full semantic entropy | M−1 (M=10 in the source paper) | O(M²) entailment checks | none | Direct: LLaMA-2-Chat 7B/13B, AUROC 0.79 |
| SelfCheckGPT (n-gram / BERTScore) | N−1 | 0 (n-gram) / light (BERTScore) | none | Direct: Llama-2-7B/13B tested |
| SelfCheckGPT (NLI / prompt-based) | N−1 | N calls | none | Direct: 7B/13B tested, best result needs a GPT-3.5 judge |

Full source review, per-paper caveats, and citations: `reference/team/confidence_scoring_harness_report_concise_en.md` (Zhexuan Ye, 2026-09-13).

\* **The SEP row's "0 at inference" assumes the inference stack exposes hidden states.** Ollama and the llama.cpp server don't expose them at all; vLLM exposes logprobs but not hidden states without a custom hook. The Semantic Entropy Probe reads hidden states directly (it's also what the OATML SEP reference implementation requires), so variant B is only buildable if the harness runs the model through HF transformers directly. Architecture v0.3 §9/TODO A1 has since settled on HF transformers with bitsandbytes 4-bit as the local inference stack precisely for this reason — see §3 below for what that means for sequencing.

**Design constraint carried over from the review:** a 2026 pre-registered screen of seven 3B–9B open-weight instruct models (including Llama-3-8B-Instruct and Llama-3.1-8B-Instruct) found verbalized confidence saturates — 91.7% of responses self-reported ≥95% confidence regardless of correctness, and two models never gave a low-confidence rating in 500+ trials. None of architecture v0.3 §5's five strategies is a verbalized-confidence prompt, so this finding adds a constraint for future strategy choices rather than superseding anything already in that table. **We do not route on verbalized confidence.** All five of §5's strategies remain candidates in principle; §3 below explains which three this document actually scopes in for the MVP and why the other two (verifier model, retrieval grounding) wait.

## 3. What the harness implements first

Ranked by evidence strength at 8B scale and marginal cost, closest match to architecture v0.3's MVP commitment (§9: "self-consistency or token logprob as the baseline signal"):

1. **Token-probability confidence (variant A)** — zero marginal cost, direct 8B-adjacent evidence, and no dependency on hidden-state access. Implement first; this is the only signal in the W4–W7 midpoint scope (TODO A7).
2. **Semantic Entropy Probe (variant B)** — zero marginal cost at inference once trained; best cost/accuracy combination in the review. Needs two things the midpoint doesn't have time for: a one-time labeled calibration pass (run full semantic entropy once offline to generate probe training targets) and the HF-transformers inference stack described in §2's footnote. Implement second, in the W9–W11 extend phase, now that TODO A1 has settled the stack it needs.
3. **Self-consistency / full semantic entropy ensemble (variant C)** — the expensive, best-validated upper bound. Implement third, also W9–W11, as the reference point for "is k× compute worth it," not as a shipped default.

Retrieval grounding and verifier-model strategies from architecture v0.3 §5 are out of scope for this document; they depend on the RAG decision, now settled as a stretch goal (architecture v0.3 §11 item 2 / decision log 2026-09-15). Task heuristics ("multi-step reasoning escalates by default") are router policy, not a confidence signal — out of scope here for that reason, not because of any finding in this document. They stack on top of any variant above and belong in a future `feat/router-*` branch, keeping §5's MVP recommendation of "token probability plus task heuristics" intact.

## 4. Harness design: three signal variants, one sampling pass

A note on naming, since this section and §7 both use the word "configuration" for different things: architecture v0.3 §7 defines three **system configurations** — local-only, hybrid, cloud-only. Variants A, B, and C below are three candidate confidence **signals** that only exist inside the hybrid configuration; they never run standalone. From here on this document calls A/B/C "signal variants" and reserves "configuration" for §7's three.

### 4.1 Share the sampling budget

Generate the local model's *k* samples once per query, then derive all three signal variants from that shared batch, so the harness pays for k generations once, not 3k:

- **Variant A — Zero-Overhead.** Sample #1 only; confidence = token logprob. No extra cost. W4–W7 midpoint scope.
- **Variant B — Cheap Probe.** Sample #1's hidden states through the offline-trained SEP. Same inference cost as A; the added costs are one-time probe training and requiring an inference stack that exposes hidden states (§2 footnote). W9–W11 extend-phase scope.
- **Variant C — Sampling Ensemble.** All k samples; self-consistency agreement and/or entailment-clustered semantic entropy. The expensive, best-validated variant and the upper-bound reference. W9–W11 extend-phase scope.

Each variant is a candidate implementation of the hybrid configuration's confidence signal, run against the same local-only and cloud-only baselines (§4.3 explains how those two baselines fall out of the same pass).

### 4.2 Six confidence metrics per signal variant

These are **not** architecture v0.3 §7's six system metrics (accuracy, latency, cost per query, escalation rate, PII-leak rate, prompt-injection resistance), computed once per system configuration. They are the confidence-specific detail behind §7's one sentence for the hybrid row: "we also plot the escalation-rate vs accuracy curve, AUROC, and calibration error." The harness still records §7's six system metrics for all three system configurations (local-only, hybrid, cloud-only) — that table is the headline result; what follows expands the hybrid row's confidence signal into per-variant detail:

1. **System accuracy** — end-to-end correctness after routing, for this variant's escalation decisions.
2. **Local-only accuracy** — correctness ignoring escalation, isolating routing's contribution.
3. **ECE** — calibration of the confidence score vs. local-answer correctness.
4. **AUROC** — ranking power of the confidence score.
5. **AURC** (or accuracy at fixed coverage, e.g. 80%) — selective-prediction performance.
6. **Escalation rate & inference-cost multiplier** — % routed to cloud, paired with the realized compute multiplier (1×, 1×+probe, or k×). This is a different number from §7's cost per query: the multiplier is relative local compute, cost per query is realized dollars including the cloud call. Both are reported.

The sampling loop itself logs wall-clock latency and cloud tokens (converted to dollars) per query, so §7's latency and cost-per-query metrics come out of this same run rather than a separate pass. PII-leak rate and prompt-injection resistance are computed by the security workstream from the same per-query logs, in W9–W11.

The result is a two-level table: architecture v0.3 §7's 3 configurations × 6 system metrics as the headline, with the hybrid row's confidence signal expanded into 3 signal variants × 6 confidence metrics above.

Metric 6 is the number most routing literature omits (see reference report §2): published work reports savings from routing but rarely the added cost of computing the confidence signal itself. This harness reports both sides.

### 4.3 One-pass execution flow

The cloud model is called once per query, unconditionally, and the answer is cached — not called only when some variant escalates. This costs nothing extra: the cloud-only configuration already needs every query answered by the cloud, so paying for that call once and reusing it is strictly cheaper than the naive "call cloud-only separately" approach, and it makes all three of architecture v0.3 §7's system configurations fall out of the same pass:

```
for each query in eval_set:
    samples[1..k] = local_model.generate(query, n=k, temperature=T)   # the one shared local cost
    cloud_answer = cloud_model.generate(query)                        # the one shared cloud cost, always called, cached

    conf_A = token_logprob_score(samples[1])
    escalate_A = conf_A < threshold_A

    conf_B = semantic_entropy_probe(hidden_states(samples[1]))        # trained offline once; W9-W11
    escalate_B = conf_B < threshold_B

    conf_C = self_consistency_agreement(samples[1..k])                # and/or semantic_entropy(samples); W9-W11
    escalate_C = conf_C < threshold_C

    record("local-only", correctness(samples[1], gold))
    record("cloud-only", correctness(cloud_answer, gold))

    for variant in [A, B, C]:
        final_answer[variant] = cloud_answer if escalate[variant] else samples[1]  # or majority vote for C
        record("hybrid", variant, correctness(final_answer[variant], gold),
               correctness(samples[1] or majority, gold), conf[variant], escalate[variant])

# after the loop:
#   per system configuration (local-only / hybrid / cloud-only): accuracy, latency, cost per query,
#     escalation rate (architecture v0.3 §7's six, minus PII-leak rate and prompt-injection resistance,
#     which the security workstream adds from the same logs in W9-W11)
#   per hybrid signal variant (A / B / C): accuracy, local-only accuracy, ECE, AUROC,
#     AURC@80%coverage, escalation rate & cost multiplier (§4.2)
```

Cost is computed from the log — escalation flags times cloud tokens for each variant — not from separate cloud calls per variant, since only one cloud call happens per query regardless of how many variants would have escalated.

`threshold_A/B/C` are calibrated independently on a held-out dev split, separate from the benchmark test sets in §5, and re-validated whenever the base 8B model changes. The midpoint (§3, §6) only calibrates `threshold_A`; `threshold_B` and `threshold_C` follow once variants B and C exist in W9–W11.

## 5. Datasets for `correctness(...)`

Architecture v0.3 §7 already names MMLU, GSM8K, and TruthfulQA/HaluEval for this purpose. Scoring detail per dataset:

| Benchmark | Format | Scoring | Caveat |
|---|---|---|---|
| MMLU | 4-way MC, 57 subjects | Accuracy, 5-shot | ~6.5% documented label-error rate (up to 57% in Virology) — sets a floor on achievable ECE/AURC; a nonzero ECE should not be read as a model shortcoming without checking against this floor. |
| GSM8K | Free-text math word problems | Exact-match on final numeric answer after `####` | — |
| TruthfulQA | MC only for the MVP (MC1/MC2 by logprob, same mechanism as variant A) | Logprob-based, no external judge | The free-generation split needs fine-tuned GPT-judge/GPT-info classifiers — OpenAI fine-tunes on a base model no longer served. Cloud provider (TODO A6) is still open; if it lands on Anthropic the harness shouldn't carry an OpenAI dependency for scoring. Defer free-generation scoring until A6 is decided, using an open-weight HF judge if it's still wanted. |
| HaluEval | QA/dialogue/summarization + general-query | Binary Yes/No hallucination judgment vs. label | Maps most directly onto the binary correct/incorrect label ECE/AUROC/AURC need; arguably the most harness-friendly of the four. |

## 6. Implementation roadmap

Proposed branch sequence (see repository root `README.md` for branch-naming rules), split by the midpoint/extend boundary the review pointed out:

| Branch | Scope | Depends on | Phase |
|---|---|---|---|
| `docs/confidence-harness-design` | This document | — | — |
| `feat/harness-sampling-core` | Shared k-sample loop on HF transformers (TODO A1), unconditional cached cloud call, query/result data structures, escalation trigger | this doc | W4–W7 |
| `eval/benchmark-loaders` | MMLU / GSM8K / TruthfulQA(MC) / HaluEval loaders and `correctness(...)` scoring | this doc | W4–W7 |
| `eval/calibration-metrics` | ECE, AUROC, AURC, escalation-rate & cost-multiplier, unit-tested against synthetic data | this doc | W4–W7 |
| `feat/signal-token-logprob` | Variant A | `feat/harness-sampling-core` | W4–W7 |
| `feat/harness-threshold-calibration` | Calibrate whichever variant thresholds exist so far on a held-out dev split; produce the escalation-vs-accuracy curve. Needs at least one signal variant, not all three — the midpoint pass only calibrates `threshold_A` | at least one signal variant branch | W4–W7 (variant A), extended W9–W11 (B, C) |
| `eval/midpoint-pilot` | First real run: variant A only, architecture v0.3 §7's three system configurations on MMLU subset + GSM8K, accuracy/escalation-rate/cost-per-query/latency (TODO A7) | sampling-core, benchmark-loaders, calibration-metrics, signal-token-logprob, threshold-calibration(A) | W4–W7 |
| `feat/signal-sep-probe` | Variant B: offline probe training + inference-time scoring on hidden states (needs the transformers stack from `feat/harness-sampling-core`, §2 footnote) | `feat/harness-sampling-core` | W9–W11 |
| `feat/signal-sampling-ensemble` | Variant C: self-consistency (+ optional semantic-entropy clustering) | `feat/harness-sampling-core` | W9–W11 |
| `eval/full-run` | Full 3-configuration × 6-metric result table with all three signal variants; PII-leak rate and prompt-injection resistance added by the security workstream | signal-sep-probe, signal-sampling-ensemble, threshold-calibration(B, C) | W9–W11 |

## 7. Open risks

- **MMLU label noise** caps achievable ECE/AURC regardless of model quality (§5).
- **Threshold calibration is model-specific**, not a fixed property of "8B parameters" — must be redone if the base model changes.
- **Cost-accounting gap in the literature**: most routing papers report savings, not the confidence estimator's own cost. Metric 6 (§4.2) is designed to close this gap for our results specifically.
- **No direct 8B evidence** for self-consistency, P(True)/P(IK), or full semantic entropy at exactly 8B (closest tested points: 7B/13B for semantic entropy, 3B/12B for P(True)/P(IK), 20B+ for self-consistency). Treat variant C's numbers as informative, not as a scale-matched ground truth.

The inference-stack risk this document originally carried for variant B (SEP needs hidden states; Ollama/llama.cpp/vLLM don't expose them) is resolved, not open: TODO A1 and the 2026-09-15 decision log entry settled on HF transformers with bitsandbytes 4-bit specifically because the harness needs it.

## 8. Relationship to open decisions

This document's variant-B/inference-stack finding is what drove TODO A1's decision to require an inference stack that exposes logprobs and hidden states, and the resulting choice of HF transformers over Ollama (decision log, 2026-09-15) — see `todo/TODO.md`. It also adds one earlier clarification worth its own decision-log entry: verbalized confidence is excluded from the MVP's confidence-scoring candidates on evidence grounds, not by omission (decision log, 2026-09-14).

---

*Confidence Scoring & Evaluation Harness — Design v0.2 · Capstone for Virtual Gold Inc · 2026-09-15*
