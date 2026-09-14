# Confidence Scoring & Evaluation Harness — Design

**Capstone · Virtual Gold Inc · Week 3 · Confidence-scoring work package**

Extends [architecture-v0.2-en.md](architecture-v0.2-en.md) §5 (Confidence scoring) and §7 (Evaluation design and datasets) with an 8B-scale literature review and a concrete harness design. This document is the basis for the `feat/harness-*` and `eval/*` branches described in §5 below.

| Version | Date | Status | Author |
|---|---|---|---|
| v0.1 | 2026-09-14 | Draft, for team review | Zhexuan Ye |

---

## 1. Why this document exists

Architecture v0.2 §5 lists five candidate confidence strategies (token probability, self-consistency, verifier model, retrieval grounding, task heuristics) and recommends starting the MVP with token probability plus task heuristics, without citing scale-specific evidence. This document narrows that recommendation using literature tested at or near our target scale (Llama 3.1 8B / Qwen3 8B), and turns architecture v0.2 §7's three-configuration evaluation design into a runnable harness.

Three questions this document answers:

1. Which confidence signals have real (not extrapolated) evidence at 8B scale?
2. How many extra inferences does each cost, so the harness reports both the accuracy gain and the compute price?
3. How do we run three configurations and six metrics in a single pass instead of three separate evaluation runs?

## 2. Signal landscape at 8B scale

| Signal | Extra local generations / query | Extra auxiliary-model calls | One-time cost | 8B-scale evidence |
|---|---|---|---|---|
| Token probability / softmax | 0 | 0 | none | Direct: small-model AUROC 0.71–0.87 |
| Verbalized confidence (in-line) | 0 | 0 | none | Direct: **broken** at 8B — saturates to near-constant "very confident" |
| Verbalized confidence (follow-up prompt) | 1 | 0 | none | No 8B test; inferred from capability trend |
| Semantic Entropy Probe (SEP) | 0 at inference | 0 | one probe-training pass | Smallest tested: 7B (Llama-2-7B, Mistral-7B); no 8B-specific ablation |
| P(True) / P(IK) | ≥1 | 0 | none | No 8B test (800M/3B/12B/52B only); scale trend suggests worse OOD generalization |
| Self-consistency | k−1 (saturates ~5–10 samples) | 0 | none | No 8B test (20B–540B only); smaller-model gains reduced |
| Full semantic entropy | M−1 (M=10 in the source paper) | O(M²) entailment checks | none | Direct: LLaMA-2-Chat 7B/13B, AUROC 0.79 |
| SelfCheckGPT (n-gram / BERTScore) | N−1 | 0 (n-gram) / light (BERTScore) | none | Direct: Llama-2-7B/13B tested |
| SelfCheckGPT (NLI / prompt-based) | N−1 | N calls | none | Direct: 7B/13B tested, best result needs a GPT-3.5 judge |

Full source review, per-paper caveats, and citations: `reference/team/confidence_scoring_harness_report_concise_en.md` (Zhexuan Ye, 2026-09-13).

**Design constraint carried over from the review:** a 2026 pre-registered screen of seven 3B–9B open-weight instruct models (including Llama-3-8B-Instruct and Llama-3.1-8B-Instruct) found verbalized confidence saturates — 91.7% of responses self-reported ≥95% confidence regardless of correctness, and two models never gave a low-confidence rating in 500+ trials. This supersedes architecture v0.2 §5's implicit assumption that a model can simply "state" its confidence. **We do not route on verbalized confidence.** Architecture v0.2 §5's strategy table should be read with token probability, self-consistency, and retrieval grounding as the viable candidates; verifier-model and task-heuristic strategies are unaffected by this finding.

## 3. What the harness implements first

Ranked by evidence strength at 8B scale and marginal cost, closest match to architecture v0.2's MVP commitment (§9: "self-consistency or token logprob as the baseline signal"):

1. **Token-probability confidence** — zero marginal cost, direct 8B-adjacent evidence. Implement first.
2. **Semantic Entropy Probe** — zero marginal cost at inference once trained; best cost/accuracy combination in the review, but needs a one-time labeled calibration pass (run full semantic entropy once offline to generate probe training targets). Implement second.
3. **Self-consistency / full semantic entropy ensemble** — the expensive, best-validated upper bound. Implement third, as the reference point for "is k× compute worth it," not as a shipped default.

Retrieval grounding and verifier-model strategies from architecture v0.2 §5 are out of scope for this document; they depend on the RAG decision still open in architecture v0.2 §11 item 2.

## 4. Harness design: three configurations, one sampling pass

### 4.1 Share the sampling budget

Generate the local model's *k* samples once per query, then derive all three configurations from that shared batch, so the harness pays for k generations once, not 3k:

- **Config A — Zero-Overhead.** Sample #1 only; confidence = token logprob. No extra cost.
- **Config B — Cheap Probe.** Sample #1's hidden states through the offline-trained SEP. Same inference cost as A; the only added cost is one-time probe training.
- **Config C — Sampling Ensemble.** All k samples; self-consistency agreement and/or entailment-clustered semantic entropy. The expensive, best-validated configuration and the upper-bound reference.

This three-way split sits inside architecture v0.2 §7's three-configuration evaluation (local-only / hybrid / cloud-only): A, B, and C are three candidate implementations of the "hybrid" configuration's confidence signal, each run against the same local-only and cloud-only baselines.

### 4.2 Six metrics per configuration (3×6 result table)

Matches architecture v0.2 §7's metric list, with the confidence-specific metrics (ECE, AUROC, calibration error) made explicit per configuration instead of computed once for "hybrid":

1. **System accuracy** — end-to-end correctness after routing.
2. **Local-only accuracy** — correctness ignoring escalation, isolating routing's contribution.
3. **ECE** — calibration of the confidence score vs. local-answer correctness.
4. **AUROC** — ranking power of the confidence score.
5. **AURC** (or accuracy at fixed coverage, e.g. 80%) — selective-prediction performance.
6. **Escalation rate & inference-cost multiplier** — % routed to cloud, paired with the realized compute multiplier (1×, 1×+probe, or k×).

Metric 6 is the number most routing literature omits (see reference report §2): published work reports savings from routing but rarely the added cost of computing the confidence signal itself. This harness reports both sides.

### 4.3 One-pass execution flow

```
for each query in eval_set:
    samples[1..k] = local_model.generate(query, n=k, temperature=T)   # the one shared cost

    conf_A = token_logprob_score(samples[1])
    escalate_A = conf_A < threshold_A

    conf_B = semantic_entropy_probe(hidden_states(samples[1]))        # trained offline once
    escalate_B = conf_B < threshold_B

    conf_C = self_consistency_agreement(samples[1..k])                # and/or semantic_entropy(samples)
    escalate_C = conf_C < threshold_C

    if escalate_A or escalate_B or escalate_C:
        cloud_answer = cloud_model.generate(query)                    # at most once per query

    for cfg in [A, B, C]:
        final_answer[cfg] = cloud_answer if escalate[cfg] else samples[1]  # or majority vote for C
        record(cfg, correctness(final_answer[cfg], gold),
               correctness(samples[1] or majority, gold), conf[cfg], escalate[cfg])

# after the loop, per configuration:
#   accuracy, local-only accuracy, ECE, AUROC, AURC@80%coverage, escalation rate & cost multiplier
```

`threshold_A/B/C` are calibrated independently on a held-out dev split, separate from the benchmark test sets in §5, and re-validated whenever the base 8B model changes.

## 5. Datasets for `correctness(...)`

Architecture v0.2 §7 already names MMLU, GSM8K, and TruthfulQA/HaluEval for this purpose. Scoring detail per dataset:

| Benchmark | Format | Scoring | Caveat |
|---|---|---|---|
| MMLU | 4-way MC, 57 subjects | Accuracy, 5-shot | ~6.5% documented label-error rate (up to 57% in Virology) — sets a floor on achievable ECE/AURC; a nonzero ECE should not be read as a model shortcoming without checking against this floor. |
| GSM8K | Free-text math word problems | Exact-match on final numeric answer after `####` | — |
| TruthfulQA | MC + free-generation | MC1/MC2 by logprob; free-gen graded by fine-tuned GPT-judge/GPT-info classifiers | — |
| HaluEval | QA/dialogue/summarization + general-query | Binary Yes/No hallucination judgment vs. label | Maps most directly onto the binary correct/incorrect label ECE/AUROC/AURC need; arguably the most harness-friendly of the four. |

## 6. Implementation roadmap

Proposed branch sequence (see repository root `README.md` for branch-naming rules):

| Branch | Scope | Depends on |
|---|---|---|
| `docs/confidence-harness-design` | This document | — |
| `feat/harness-sampling-core` | Shared k-sample loop, query/result data structures, escalation trigger, cloud-call stub | this doc |
| `eval/benchmark-loaders` | MMLU / GSM8K / TruthfulQA / HaluEval loaders and `correctness(...)` scoring | this doc |
| `eval/calibration-metrics` | ECE, AUROC, AURC, escalation-rate & cost-multiplier, unit-tested against synthetic data | this doc |
| `feat/signal-token-logprob` | Config A | `feat/harness-sampling-core` |
| `feat/signal-sep-probe` | Config B: offline probe training + inference-time scoring | `feat/harness-sampling-core` |
| `feat/signal-sampling-ensemble` | Config C: self-consistency (+ optional semantic-entropy clustering) | `feat/harness-sampling-core` |
| `feat/harness-threshold-calibration` | Calibrate `threshold_A/B/C` on a held-out dev split; produce the escalation-vs-accuracy curve | signal branches above |
| `eval/*-pilot-run` | First real run producing the 3×6 result table | calibration branch |

## 7. Open risks

- **MMLU label noise** caps achievable ECE/AURC regardless of model quality (§5).
- **Threshold calibration is model-specific**, not a fixed property of "8B parameters" — must be redone if the base model changes (architecture v0.2 §11 item 5 is still open).
- **Cost-accounting gap in the literature**: most routing papers report savings, not the confidence estimator's own cost. Metric 6 (§4.2) is designed to close this gap for our results specifically.
- **No direct 8B evidence** for self-consistency, P(True)/P(IK), or full semantic entropy at exactly 8B (closest tested points: 7B/13B for semantic entropy, 3B/12B for P(True)/P(IK), 20B+ for self-consistency). Treat Config C's numbers as informative, not as a scale-matched ground truth.

## 8. Relationship to open decisions

None of the items in this document require a change to architecture v0.2 §11's open decisions. It does add one clarification worth a decision-log entry: verbalized confidence is excluded from the MVP's confidence-scoring candidates on evidence grounds, not by omission. See `todo/TODO.md` decision log.

---

*Confidence Scoring & Evaluation Harness — Design v0.1 · Capstone for Virtual Gold Inc · 2026-09-14*
