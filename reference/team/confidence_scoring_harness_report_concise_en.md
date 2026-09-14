---
title: Confidence Scoring & Evaluation Harness — Research Report (Concise)
subtitle: Virtual Gold Inc. Capstone (Secure Hybrid AI Assistant) — Confidence Scoring & Model-Routing Work Package
date: September 13, 2026
author: Zhexuan Ye (CMU MISM Capstone Team)
---

# Confidence Scoring and Evaluation Harness

## Which uncertainty signals work on 8B-class local models, what they cost, and how to benchmark them

---

## 0. Scope

The sponsor's brief (Virtual Gold Inc.) describes a hybrid assistant that runs open-source LLMs locally and escalates to cloud models "when additional confidence or reasoning capability is required," without prescribing methods or a harness design. This report answers three questions for the confidence-scoring work package:

1. Which confidence signals actually work on an 8B model?
2. How many extra inferences does each cost?
3. How should the harness run three configurations and report six metrics in one pass?

---

## 1. The Confidence-Signal Landscape

### 1.1 Single-pass, near-zero-cost signals (all scale-dependent — bigger models are more reliable)

**Token-probability / softmax confidence.** The log-probability the model already assigned to its answer tokens — free, since it's a byproduct of the generation call already made. A 2025 medical-QA study found token probability beats verbalized confidence (AUROC 0.71–0.87 vs. 0.51–0.70) and wins on Brier score across all 9 models tested, though not universally on false-positive rate (two Gemma models showed no improvement, one significantly worse). Calibration tracked model scale directly: Phi-3-Mini's ACE exceeded 40%, mid-size models (Phi-3-Medium, Llama 3.1-8B) sat around 20–25%, and GPT-4o-class models stayed under 10% ([PMC12396779](https://pmc.ncbi.nlm.nih.gov/articles/PMC12396779/)). **Constraint: requires logprob access** (works for GPT-family, Llama, Phi, Gemma; not exposed by Claude or Gemini APIs). Reliability degrades as models get smaller.

**Verbalized confidence (single prompt).** The model states a numeric/categorical confidence, free if appended to the same generation. Xiong et al. (2023) found the core problem is reliability, not cost: models are systematically overconfident, and no prompting/aggregation trick consistently fixes it. Their tested models ranged from GPT-3 (175B) and Vicuna (13B) to LLaMA-2 (70B), GPT-3.5, GPT-4; weaker/less-RLHF'd models (e.g., GPT-3) calibrated far worse (ECE up to 52.0, near-random AUROC). No 8B model was tested, so this can't quantify the problem at 8B directly — but the "weaker capability → worse verbalized confidence" trend makes it reasonable to expect the problem persists or worsens at 8B, pending direct evidence ([arXiv:2306.13063](https://arxiv.org/abs/2306.13063)).

**P(True) / P(IK) self-evaluation (Kadavath et al. 2022).** P(True): after generating a candidate answer, ask the model to estimate its correctness probability. P(IK): without a candidate, ask whether the model "knows" the answer at all. Both need ≥1 extra forward pass; showing the model several of its own samples before judging improves performance further but reintroduces multi-sample cost. The paper tested only **800M / 3B / 12B / 52B** models — no 8B — and found AUROC and calibration for P(IK) both improve with scale, implying smaller models generalize worse to new tasks. Since 8B falls between the 3B and 12B test points, this is directional support, not direct evidence, for degraded P(IK) generalization at 8B ([arXiv:2207.05221](https://arxiv.org/abs/2207.05221)).

### 1.2 Learned, single-pass signal (train once, infer free)

**Semantic Entropy Probes (SEPs).** Full semantic entropy needs many sampled generations per query (5–10× cost). SEPs sidestep this: a small linear probe, trained once offline on the model's own hidden states, predicts what the expensive semantic-entropy score would have been — no human-labeled correctness needed, since training targets come from running semantic entropy once on a calibration set. At deployment, a single generation's hidden states suffice. SEPs generalize better OOD than accuracy-trained probes (though accuracy probes win in-distribution), and don't fully match full semantic entropy's absolute performance. Smallest models tested: **Llama-2-7B and Mistral-7B** — the closest match to your 8B target among the signals reviewed, though still an extrapolation rather than a direct 8B measurement ([arXiv:2406.15927](https://arxiv.org/abs/2406.15927); [code](https://github.com/OATML/semantic-entropy-probes)).

### 1.3 Multi-sample, consistency-based signals

**Self-consistency (Wang et al. 2022).** Sample *k* reasoning paths at nonzero temperature; majority-vote agreement doubles as confidence. Original paper used k=40 (ablated 1/5/10/20/40); most tasks saturate by k≈5–10. Tested models: **UL2-20B, LaMDA-137B, GPT-3-175B, PaLM-540B** — no model near 8B. On GSM8K, the smallest model (UL2-20B) gained the least (+3.2 points, 4.1%→7.3%), versus +9–23 points for LaMDA-137B and GPT-3. The paper's own explanation — arithmetic/reasoning capabilities "emerge" only at sufficient scale — is the key warning for 8B: gains may be modest below the emergence threshold. Cost: **k−1 extra local generations**, no auxiliary model ([arXiv:2203.11171](https://arxiv.org/abs/2203.11171)).

**Semantic entropy (Kuhn et al. 2023; Farquhar et al. 2024, *Nature*).** Cluster M sampled generations by meaning (bidirectional entailment) and compute entropy over clusters rather than tokens (M=10 in the main analysis). Directly validated at your target scale: **LLaMA-2-Chat 7B/13B/70B, Falcon-Instruct 7B/40B, Mistral-Instruct 7B**. Across 30 task–model combinations: AUROC 0.790, beating naive entropy (0.691) and P(True) (0.698). Cost: **M−1 generations + O(M²) pairwise entailment checks** (NLI model or cheap LLM call); a discrete variant avoids needing exact logprobs, usable with black-box APIs ([Nature](https://www.nature.com/articles/s41586-024-07421-0)).

**SelfCheckGPT (Manakul et al. 2023).** Black-box: draw N samples, check whether each sentence of the main response is supported by the samples, via one of five backends (BERTScore, MCQ/QA-consistency, n-gram stats, NLI, or LLM prompting). Best result (AUC-PR 93.42) used GPT-3.5 as the prompt-based judge; the public repo also reports the prompt variant on **Llama-2-7B/13B-chat and Mistral-7B-Instruct** (89–92 AUC-PR, below GPT-3.5). Cost scales with N; NLI and prompt variants add N auxiliary-model calls; BERTScore still needs a (lighter) auxiliary model (RoBERTa-Large); only the **n-gram variant is truly free of a second model** — pure statistics over the N samples already generated, making it the cheapest option to pair with a local 8B model ([arXiv:2303.08896](https://arxiv.org/abs/2303.08896); [code](https://github.com/potsawee/selfcheckgpt)).

---

## 2. Calibration and Evaluation Metrics

**ECE** bins predictions by confidence and compares mean stated confidence to actual accuracy per bin: ECE = Σ(|B_m|/n)·|acc(B_m) − conf(B_m)|. Measures calibration magnitude, not ranking ability.

**AUROC** treats correctness as a binary label and confidence as a classifier score — measures discrimination independent of calibration. This is the standard head-to-head metric in the literature (e.g., semantic entropy 0.790 vs. naive entropy 0.691).

**Risk–coverage curves / AURC.** Sort predictions by confidence; at coverage κ=k/n, compute error rate among the top-k retained. AURC integrates this into one number (lower is better), rewarding correct *ranking* even without calibrated absolute values.

**Escalation-rate vs. accuracy curves.** The system-level analogue of risk-coverage: sweep the escalation threshold and plot % of queries sent to the cloud model against end-to-end accuracy or cost. One cascade survey cites a framework reaching "97.25% of GPT-4's quality at 24.18% of the cost" this way ([arXiv:2603.04445](https://arxiv.org/html/2603.04445v1)). That survey mostly reports cost *savings* from routing, with little to no separate accounting of the cost *added* by the confidence estimator itself — the gap RQ2 targets.

---

## 3. RQ1 & RQ2: What Works at 8B, and What It Costs

### 3.1 Verbalized confidence: not just weak at 8B, broken

A 2026 pre-registered psychometric screen tested **3B–9B open-weight instruct models** directly — Meta-Llama-3-8B-Instruct, Meta-Llama-3.1-8B-Instruct, DeepSeek-R1-Distill-Llama-8B, Mistral-7B, Qwen2.5-3B/7B, Gemma-2-9B. Verbalized confidence **saturates**: across seven models, 91.7% of responses averaged self-reported confidence ≥95%, and two models never gave a low-confidence rating in 500+ trials, regardless of correctness. The authors call this "a validity failure rather than a calibration problem": a distribution collapsed to the ceiling carries almost no information. Their conclusion: any hybrid system using verbal confidence from small open-weight models for routing decisions "is building on a degenerate signal" ([arXiv:2604.22215](https://arxiv.org/html/2604.22215)).

### 3.2 What does work at 8B

- **Token-probability confidence** — free; meaningfully separates correct/incorrect even at small scale (AUROC 0.71–0.87), a large improvement over verbalized confidence's near-random behavior.
- **Semantic entropy** — directly validated at 7B/13B (AUROC 0.79), ahead of naive entropy and P(True) at the same scale.
- **Semantic Entropy Probes** — no size-specific ablation found, but inherits semantic entropy's signal while removing nearly all marginal cost; smallest tested models are 7B. Strongest cost/accuracy combination to prototype first.

Self-consistency and P(True) still improve over greedy decoding at small scale, but both papers flag reduced benefit below an "emergence" threshold or on new tasks. SelfCheckGPT's cheaper n-gram/BERTScore variants suit an all-local pipeline better than the prompt-based variant, which leans on a stronger judge model.

### 3.3 Inference-cost table

| Signal | Extra local generations/query | Extra auxiliary-model calls | One-time cost | 8B-scale evidence |
|---|---|---|---|---|
| Token-probability / softmax | **0** | 0 | none | Direct: small-model AUROC 0.71–0.87 |
| Verbalized confidence (in-line) | 0 | 0 | none | Direct: **broken** at 8B (saturation) |
| Verbalized confidence (follow-up) | 1 | 0 | none | No 8B test; inferred from capability trend |
| Semantic Entropy Probe | 0 at inference | 0 | probe training pass | Smallest tested: 7B; no 8B-specific ablation |
| P(True) / P(IK) | ≥1 (more with sample-conditioning) | 0 | none | No 8B test (800M/3B/12B/52B only); scale trend suggests worse OOD generalization |
| Self-consistency | k−1 (k=40 in paper; saturates ~5–10) | 0 | none | No 8B test (20B–540B); smaller-model gains reduced |
| Full semantic entropy | M−1 (M=10 in paper) | O(M²) entailment checks | none | Direct: 7B/13B, AUROC 0.79 |
| SelfCheckGPT (n-gram / BERTScore) | N−1 (~20 in paper) | 0 (n-gram) / light (BERTScore) | none | Direct: tested on Llama-2-7B/13B |
| SelfCheckGPT (NLI / prompt-based) | N−1 | N calls | none | Direct: 7B/13B tested, best result needs GPT-3.5 judge |

**Bottom line:** token-probability confidence and Semantic Entropy Probes are the only two signals here with near-zero marginal cost per query *and* real (not purely extrapolated) evidence near the 8B scale. Multi-sample methods buy measurable AUROC/accuracy gains but cost 5–40× a single pass — budget accordingly given the sponsor's local-compute cost-efficiency goal.

---

## 4. RQ3: A Harness for Three Configurations, Six Metrics, One Pass

### 4.1 Design: share the sampling budget

Generate the local model's *k* samples **once per query**, then derive all three configurations from that shared batch:

- **Config A — Zero-Overhead.** Sample #1 only; confidence = token logprob. No extra cost.
- **Config B — Cheap Probe.** Sample #1's hidden states through an offline-trained SEP-style probe. Same inference cost as A; only added cost is one-time probe training.
- **Config C — Sampling Ensemble.** All k samples; self-consistency and/or entailment-clustered semantic entropy. The expensive, best-validated configuration and the upper-bound reference for "is k× compute worth it."

A and B reuse C's sample #1, so the harness pays for k generations **once**, not 3k. A single cloud call per query (if any configuration escalates) is shared across configs, with per-config bookkeeping to keep metrics independent.

### 4.2 Six metrics per configuration (3×6 = 18-cell results table)

1. **System accuracy** — end-to-end correctness after routing.
2. **Local-only accuracy** — correctness ignoring escalation, isolating routing's contribution.
3. **ECE** — calibration of the confidence score vs. local-answer correctness.
4. **AUROC** — ranking power of the confidence score.
5. **AURC** (or accuracy at fixed coverage, e.g. 80%) — selective-prediction performance.
6. **Escalation rate & inference-cost multiplier** — % routed to cloud, paired with the realized compute multiplier (1×, 1×+probe, or k×) — the number the literature omits.

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

Calibrate `threshold_A/B/C` independently on a held-out dev split; the resulting escalation-vs-accuracy curve is itself useful output, and the reported operating point can match the sponsor's escalation budget (e.g., "≤20% of queries leave the local sandbox").

### 4.4 Benchmarks for `correctness(...)`

| Benchmark | Format | Size | Scoring |
|---|---|---|---|
| **MMLU** | 4-way MC, 57 subjects | 15,908 Q | Accuracy, 5-shot standard. Documented 6.5% label-error rate (up to 57% in Virology) sets a real floor on achievable ECE/AURC. |
| **GSM8K** | Free-text math word problems | 8,792 (7,473/1,319 split) | Exact-match on final numeric answer after `####`. |
| **TruthfulQA** | MC + free-generation, ~38 categories | ~817 | MC1/MC2 by log-prob; free-gen graded by fine-tuned GPT-judge/GPT-info classifiers (~90–95% human agreement). |
| **HaluEval** | QA/dialogue/summarization + general-query splits | 35,000 | Binary Yes/No hallucination judgment vs. label; human agreement κ=0.811. |

HaluEval's Yes/No format maps most directly onto the binary correct/incorrect label ECE/AUROC/AURC need, and measures hallucination directly rather than task accuracy — arguably the most harness-friendly of the four for this purpose.

---

## 5. Recommendations and Open Risks

**Prototype order:** Config A vs. B first (token-logprob vs. SEP) — both near-free per query, B needing only one labeled calibration set. Treat Config C as the expensive upper-bound reference, not the default design, given the sponsor's cost-efficiency goal.

**Don't build on verbalized confidence.** Treat this as a design constraint: multiple 8B-class models collapse to a near-constant "very confident" response, so verbal confidence shouldn't gate escalation without independent validation on your own models/prompts.

**MMLU label-quality caveat.** Its ~6.5% label-error rate caps how low ECE/AURC can go regardless of model quality — worth flagging so a nonzero ECE isn't misread as a model shortcoming.

**Close the literature's cost-accounting gap.** Published routing/cascade work reports savings from routing but rarely the added cost of computing the confidence signal itself. Metric 6 (§4.2) is designed to report both sides of that ledger.

**Threshold calibration needs its own held-out split**, tuned separately from the §4.4 benchmark test sets, and re-validated if the base 8B model changes — calibration behavior is model- and fine-tuning-specific, not a fixed property of "8B parameters."

**Note on scale evidence:** among the signals reviewed, only semantic entropy (Farquhar et al.) and SelfCheckGPT were tested directly on 7B-class models close to your target; the Kadavath (P(True)/P(IK)), Xiong (verbalized confidence), and self-consistency (Wang et al.) papers did not test an 8B-scale model, so their scale-related claims here are extrapolations from adjacent sizes, not direct 8B measurements — flagged explicitly per signal above.

---

## References

1. Wang, X. et al. (2022). *Self-Consistency Improves Chain of Thought Reasoning in Language Models.* [arXiv:2203.11171](https://arxiv.org/abs/2203.11171)
2. Kuhn, L., Gal, Y., Farquhar, S. (2023). *Semantic Uncertainty.* [arXiv:2302.09664](https://arxiv.org/abs/2302.09664)
3. Farquhar, S., Kossen, J., Kuhn, L., Gal, Y. (2024). *Detecting hallucinations in large language models using semantic entropy.* Nature. [link](https://www.nature.com/articles/s41586-024-07421-0)
4. Kossen, J. et al. (2024). *Semantic Entropy Probes.* [arXiv:2406.15927](https://arxiv.org/abs/2406.15927); [code](https://github.com/OATML/semantic-entropy-probes)
5. Kadavath, S. et al. (2022). *Language Models (Mostly) Know What They Know.* [arXiv:2207.05221](https://arxiv.org/abs/2207.05221)
6. Manakul, P., Liusie, A., Gales, M. (2023). *SelfCheckGPT.* [arXiv:2303.08896](https://arxiv.org/abs/2303.08896); [code](https://github.com/potsawee/selfcheckgpt)
7. Xiong, M. et al. (2023). *Can LLMs Express Their Uncertainty?* [arXiv:2306.13063](https://arxiv.org/abs/2306.13063)
8. Anonymous (2026). *Verbal Confidence Saturation in 3–9B Open-Weight Instruction-Tuned LLMs.* [arXiv:2604.22215](https://arxiv.org/html/2604.22215)
9. (2025). *Token Probabilities to Mitigate LLM Overconfidence in Answering Medical Questions.* PMC. [link](https://pmc.ncbi.nlm.nih.gov/articles/PMC12396779/)
10. *Mind the Confidence Gap.* [arXiv:2502.11028](https://arxiv.org/html/2502.11028v2)
11. *Dynamic Model Routing and Cascading for Efficient LLM Inference: A Survey.* [arXiv:2603.04445](https://arxiv.org/html/2603.04445v1)
12. *Leveraging Uncertainty Estimation for Efficient LLM Routing.* [arXiv:2502.11021](https://arxiv.org/html/2502.11021v1)
13. Expected Calibration Error. [Towards Data Science](https://towardsdatascience.com/expected-calibration-error-ece-a-step-by-step-visual-explanation-with-python-code-c3e9aa12937d/)
14. AURC definition. [Torch-Uncertainty docs](https://torch-uncertainty.github.io/generated/torch_uncertainty.metrics.classification.AURC.html); Traub, J. et al. [arXiv:2410.15361](https://arxiv.org/abs/2410.15361)
15. Hendrycks, D. et al. (2020). *MMLU.* [Wikipedia](https://en.wikipedia.org/wiki/MMLU)
16. Cobbe, K. et al. (2021). *GSM8K.* [HuggingFace](https://huggingface.co/datasets/openai/gsm8k)
17. Lin, S., Hilton, J., Evans, O. (2022). *TruthfulQA.* [arXiv:2109.07958](https://arxiv.org/abs/2109.07958)
18. Li, J. et al. (2023). *HaluEval.* [arXiv:2305.11747](https://arxiv.org/html/2305.11747v3)

*Prepared from the Virtual Gold Inc. capstone proposal and confidence-scoring research brief; cross-referenced against sources above via live search and primary-source verification.*
