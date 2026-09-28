# Hybrid AI Models and Inference

## Final research brief for the Virtual Gold capstone

**Prepared:** 2026-09-20  
**Scope:** model selection, local inference, confidence estimation, routing, privacy, and client discussion  
**Source basis:** [Gemini research source](<Hybrid AI Models And Inference.md>), the [latest client meeting notes](virtual-gold-capstone/meetings/client/2026-09-15/notes-gemini-en.pdf), the [team implementation plan](virtual-gold-capstone/todo/TODO.md), and current primary documentation linked throughout

## Executive recommendation

Virtual Gold should implement a local-first hybrid system for financial-services SMB document workflows:

1. Run the primary model locally on the client GPU sandbox.
2. Compute a confidence signal locally.
3. Answer locally when the request is sufficiently reliable.
4. Escalate only approved, redacted requests to a cloud model or hosted decision service.
5. Keep the original request, PII mapping table, raw logits, hidden states, and audit record inside the local trust boundary.

The MVP decision is:

| Area | MVP choice | Reason |
|---|---|---|
| Primary generative model | Llama 3.1 8B Instruct | Stable text-only baseline, GQA, 128K model context, and a well-documented official release ([Meta model card](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/MODEL_CARD.md)) |
| Secondary comparison model | Qwen3 8B | Similar size, Apache-2.0 model card, strong current open-weight option, and a useful independent comparison ([Qwen3 model card](https://huggingface.co/Qwen/Qwen3-8B)) |
| Runtime | Hugging Face Transformers in-process | Exposes token-level scores, raw logits, and hidden states needed by the confidence experiments ([generation documentation](https://huggingface.co/docs/transformers/main_classes/text_generation)) |
| Quantization | bitsandbytes 4-bit NF4 | Keeps the 8B models feasible on a 16 GB T4 while retaining one comparable implementation path ([bitsandbytes documentation](https://huggingface.co/docs/transformers/main/en/quantization/bitsandbytes)) |
| T4 compute dtype | FP16 | The NVIDIA T4 is compute capability 7.5; BF16 must not be assumed on this GPU ([T4 datasheet](https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/tesla-t4/t4-tensor-core-datasheet-951643.pdf), [CUDA compute capabilities](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/compute-capabilities.html)) |
| Confidence baseline | Selected-token log probability | Smallest interpretable baseline that can be computed from local raw logits |
| Confidence extension | Semantic Entropy Probes and multi-sample semantic agreement | Tests uncertainty beyond a single token score without making it a prerequisite for the MVP ([SEP paper](https://arxiv.org/html/2406.15927)) |
| Router | Small project-owned policy/router | The client requires explicit control over privacy, escalation, cost, and audit behavior |
| Hosted decision comparison | Jev, only for approved non-confidential or redacted data | Jev returns typed decisions rather than generated text and does not replace the local model ([Jev documentation](https://docs.typesafe.ai/introduction)) |

This is a current, project-scoped recommendation as of 2026-09-20. It is not a claim that the selected models are the newest models available. Newer models should enter the project through the same reproducible benchmark and hardware gate.

## 1. Client problem and system boundary

The client wants a system that can use local and cloud intelligence while keeping confidential financial information under local control. The important design question is therefore not only which model is most capable. It is also:

- Can the model fit and run predictably on the supplied GPU?
- Can the runtime expose the evidence needed for confidence estimation?
- Can the router keep confidential requests local?
- Can the team measure when escalation helps?
- Can every result be explained to the client with latency, cost, accuracy, and privacy evidence?

Recommended request flow:

1. Classify the request and its sensitivity.
2. Keep confidential requests local.
3. For an approved cloud path, detect PII locally, replace it with stable placeholders, and keep the placeholder mapping local.
4. Run the local model and calculate confidence.
5. Return the local result when it clears a threshold validated on held-out data.
6. Otherwise escalate the redacted request to the approved external service.
7. Re-identify only at the local boundary, if policy permits.
8. Record model revision, runtime version, quantization, prompt, routing decision, latency, and confidence evidence.

The PII mapping table must never be sent with the redacted request. The local-first and confidential-data requirements come from the project materials, not from a model vendor.

## 2. Model selection and current landscape

### 2.1 MVP pair

Llama 3.1 8B and Qwen3 8B are the right first comparison because they are close enough in size to make a T4/A10G experiment interpretable, but different enough to reveal model-specific behavior.

Llama 3.1 8B is a text-only model with grouped-query attention and a 128K context window in the official model card. Its custom community license requires careful recording of the exact model revision and distribution conditions. The official license includes an attribution requirement when distributing a product or service and a “Built with Llama” notice. It also contains a 700 million monthly active user provision, so legal review is required before any commercial deployment ([official model card](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/MODEL_CARD.md), [official license](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE)).

Qwen3 8B is a useful independent comparator with a different training and alignment stack. Record the exact revision, license, tokenizer, prompt template, and reasoning-mode setting because these can change results ([official model card](https://huggingface.co/Qwen/Qwen3-8B)).

Do not select a winner from published benchmark tables alone. Published scores can use different prompts, chat templates, tool settings, context lengths, sampling parameters, versions, and hardware. The capstone should report the same held-out task set and the same generation contract for both models.

### 2.2 Newer models to track, not silently substitute

The current ecosystem has moved beyond the original Gemini comparison table:

- Qwen3.5-9B is a current near-size challenger, but it is a multimodal model with a hybrid Gated DeltaNet and sparse MoE architecture, long-context support, and optional multi-token prediction. It needs a separate smoke test for hidden states, generated scores, memory, and prompt formatting before it can replace Qwen3 8B ([Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B)).
- Qwen3.8-27B is not a responsible T4 MVP candidate. A simple lower-bound calculation gives 27 billion parameters times 4 bits, or about 13.5 GB of nominal weight storage before scales, runtime buffers, activations, and KV cache. That leaves too little headroom on a 16 GB T4 for the required confidence instrumentation. This is an engineering inference from the official model card and T4 memory specification, not a published end-to-end result ([Qwen3.8-27B model card](https://huggingface.co/Qwen/Qwen3.8-27B), [T4 datasheet](https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/tesla-t4/t4-tensor-core-datasheet-951643.pdf)).
- Meta Llama 4 Scout and Maverick are newer multimodal mixture-of-experts models. Meta describes Scout as a 17B active-parameter model with 16 experts and reports single-H100 Int4 deployment. That hardware profile is not evidence that it fits the capstone T4 with hidden-state and logit instrumentation ([Meta Llama 4 announcement](https://ai.meta.com/blog/llama-4-multimodal-intelligence/)).

The correct policy is to keep a small candidate watchlist, but require every candidate to pass the same artifact, hardware, interface, and quality gates before changing the MVP.

### 2.3 Jev

Jev is relevant as a hosted decision-model baseline, not as a local replacement for Llama or Qwen. Its public documentation describes typed outputs such as Choice, Score, and Noul, with probabilities and confidence. It is designed to answer structured questions and does not provide ordinary free-form text generation in the same way as a chat model ([Jev introduction](https://typesafe.ai/blog/introducing-system-one-models-and-jev), [Jev documentation](https://docs.typesafe.ai/introduction)).

Use Jev only for a separate comparison on approved data:

- decision accuracy and calibration;
- latency and cost per decision;
- schema reliability;
- behavior on ambiguous financial classification tasks.

Do not use Jev for the local confidence baseline because its public interface does not expose the token log probabilities or hidden states required by the planned W7 and SEP experiments. Its advertised latency and price are vendor-reported early-access figures and must be measured independently before they enter a client recommendation ([official announcement](https://typesafe.ai/blog/introducing-system-one-models-and-jev)). The hosted service also creates a separate data-processing and contract review boundary ([Jev master customer agreement](https://typesafe.ai/legal/mca)).

## 3. Local inference design

### 3.1 Why Transformers runs in-process

The confidence experiments need more than the final generated string. The project needs access to:

- raw next-token logits;
- processed generation scores;
- per-token transition scores;
- hidden states for probing;
- generation metadata;
- model and tokenizer revisions.

Hugging Face Transformers exposes these through generation controls such as output_logits, output_scores, and output_hidden_states. The distinction matters:

- logits are the model's unprocessed output values before generation processors and warpers;
- scores are the values used by the generation loop after applicable processing;
- a selected-token log probability should normally be derived from the raw logits when the goal is to measure the base model rather than a sampling policy.

This is why the MVP should keep the model in-process. A serving boundary can be added later, but it must be proven to preserve the evidence required by the confidence method. The relevant output contract is documented in the current Transformers generation implementation ([generation API](https://huggingface.co/docs/transformers/main_classes/text_generation), [GenerationMixin output definitions](https://github.com/huggingface/transformers/blob/main/src/transformers/generation/utils.py)).

### 3.2 4-bit NF4 on T4 and A10G

The intended quantization configuration is:

    load_in_4bit = True
    bnb_4bit_quant_type = "nf4"
    bnb_4bit_use_double_quant = True
    bnb_4bit_compute_dtype = torch.float16  # T4 baseline

NF4 stores model weights in a 4-bit representation. It does not mean that every activation, temporary tensor, KV-cache value, or hidden-state capture is 4-bit. Peak memory must therefore be measured from the actual run.

The original Gemini research recommended BF16 as the default compute type. That recommendation is corrected here. The T4 is compute capability 7.5, so the baseline should use FP16. An A10 is a different Ampere-class device and may support BF16, but the project should select the dtype from an explicit hardware check rather than a generic default.

Keep the quantization implementation fixed for the first comparison. Do not mix NF4, GPTQ, AWQ, and runtime-specific kernels in the same first experiment unless the question is specifically about serving performance.

### 3.3 KV-cache memory

For a decoder model using grouped-query attention, a useful first-order estimate is:

    KV bytes per token =
    2 x number of layers x number of KV heads x head dimension x bytes per value

For the Llama 3.1 8B configuration, using 32 layers, 8 KV heads, head dimension 128, and FP16 KV values:

    2 x 32 x 8 x 128 x 2 = 131,072 bytes per token
    32,768 tokens = about 4 GiB per sequence

This is per sequence and excludes allocator overhead, temporary activations, model scales, logits, and captured hidden states. It explains why a nominal 128K context window is not the same thing as a practical 128K context on a 16 GB T4. The layer and attention configuration should be read from the exact model revision used in the experiment ([Llama model card](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/MODEL_CARD.md), [Llama configuration example](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct/blob/main/config.json)).

Transformers currently documents several cache strategies:

- Dynamic cache: the default flexible option;
- Static cache: more memory up front, but potentially useful for compilation;
- Quantized cache: lower cache precision with its own compatibility tradeoffs;
- Offloaded cache: can reduce GPU memory pressure by moving cache data to host memory, at a latency cost.

Start with DynamicCache for correctness. Then compare StaticCache, QuantizedCache, or OffloadedCache only when a measured memory problem justifies the added complexity ([KV-cache documentation](https://huggingface.co/docs/transformers/main/en/kv_cache)).

### 3.4 Throughput and version discipline

Do not carry the Gemini source's exact token-per-second claims into the client presentation. Those figures came from non-equivalent public tests and are not a project measurement.

For each run, record:

- model and tokenizer revision;
- Transformers, PyTorch, CUDA, and bitsandbytes versions;
- GPU type and free memory before loading;
- quantization and compute dtype;
- prompt token count and generated token count;
- time to first token;
- decode tokens per second;
- p50 and p95 latency;
- peak allocated and reserved GPU memory;
- batch size and cache strategy.

Pin the library versions used for the report. The Transformers documentation currently identifies v5.17.0 as the stable documentation version, while the main branch can describe unreleased behavior ([current Transformers documentation](https://huggingface.co/docs/transformers/main/en/index)).

### 3.5 Speculative decoding and multi-token prediction

Speculative decoding and model-specific multi-token prediction can improve throughput, but they belong in a separate performance experiment. They change the generation path and may complicate the interpretation of token-level confidence. Current model cards and implementation issue reports also show that support is version- and model-dependent ([Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B), [Transformers speculative-generation issue](https://github.com/huggingface/transformers/issues/47932)).

Keep speculative decoding disabled for the W7 confidence baseline. Re-enable it only after the baseline raw-logit path is validated and the team has decided what confidence evidence should be attached to drafted and verified tokens.

## 4. Confidence and uncertainty

### 4.1 Baseline: selected-token log probability

For a generated answer, collect the raw logit vector at each generated step, apply log-softmax, and record the log probability of the token that was selected. Useful summary features include:

- mean token log probability;
- lower-tail token log probability;
- fraction of tokens below a threshold;
- answer length;
- whether the answer contains a required citation or structured field;
- agreement with a deterministic validation rule.

This is a confidence feature, not a correctness proof. A model can be confidently wrong, especially on unfamiliar financial documents or ambiguous questions. Calibrate the score against a labeled development set and report reliability, not just correlation.

### 4.2 Multi-sample semantic agreement

The next experiment should generate several answers with controlled diversity, then compare their meanings rather than their exact wording. A cross-encoder or NLI model can judge whether two answers entail, contradict, or are unrelated to each other. The project should benchmark the extra latency and memory instead of copying throughput claims from the Gemini source.

Start with k=5 samples on a small held-out set. Move to k=10 only if the additional uncertainty signal justifies the cost. Keep sampling parameters, maximum output length, and random seeds in the run manifest.

### 4.3 Semantic Entropy Probes

Semantic Entropy Probes use internal hidden-state representations to predict whether an answer is likely to be semantically uncertain. The paper describes two probe families, TBG and SLT, and shows that useful layers differ across model families and tasks. Therefore:

- do not hard-code a universal layer number;
- sweep a small candidate layer set on held-out development data;
- freeze the selected layer before test evaluation;
- report calibration and task transfer;
- compare against the simple log-probability baseline.

SEP is a research extension, not a reason to delay the MVP. The in-process runtime is valuable because it makes the required hidden states available ([SEP paper](https://arxiv.org/html/2406.15927)).

### 4.4 Routing rule

The router should be trained and evaluated as a policy:

    if request is confidential:
        keep it local
    else if local confidence >= validated threshold:
        return local result
    else:
        redact approved fields and escalate

The threshold must be selected on development data. Report the tradeoff between accuracy and escalation rate rather than presenting one threshold as universally correct.

## 5. Privacy, security, and governance

### 5.1 PII redaction and re-identification

Microsoft Presidio provides local analyzer and recognizer components for PII detection. The project can combine recognizers with regular expressions, document-specific deny lists, and test cases for financial identifiers ([Presidio Analyzer documentation](https://microsoft.github.io/presidio/analyzer/)).

The safe round trip is:

1. Analyze locally.
2. Replace detected values with stable placeholders such as PERSON_01 or ACCOUNT_01.
3. Send only approved redacted content.
4. Keep the mapping table local.
5. Re-identify only after the response returns and policy allows it.

Redaction is not perfect. Measure false negatives and false positives on a labeled set. Also validate that placeholders preserve enough structure for the downstream model to solve the task.

Do not describe a provider's zero-data-retention setting as a mathematical guarantee. It is a contractual, configuration, and operational claim that must be verified for the chosen account and endpoint.

### 5.2 Prompt injection and privilege separation

Documents, web pages, and retrieved text are untrusted inputs. A prompt-injection defense should therefore not depend only on another model saying that the input is safe.

Use separate privileges:

- document extraction and reasoning may read content but cannot perform side effects;
- tool execution accepts only a typed allowlisted schema;
- writes, messages, payments, and external transfers require an explicit policy check and, where appropriate, human confirmation;
- the router records the source document, instruction boundary, tool arguments, and final decision.

Input guard models can add signal, but they are one layer in a defense-in-depth design. The client presentation should show the privilege boundary and the blocked-action test cases.

### 5.3 Model and artifact supply chain

Use safetensors when the model supports it, pin the model revision, verify a SHA-256 hash from an independently trusted source, and keep the downloaded artifact in a controlled cache. Safetensors avoids pickle-style arbitrary-code deserialization risk, but it does not prove that the model weights are benign or that the model behaves safely ([safetensors documentation](https://huggingface.co/docs/safetensors/index)).

Also record:

- repository and exact revision;
- tokenizer files and revision;
- quantization configuration;
- conversion tool and version, if any;
- whether custom model code was enabled;
- offline or restricted-network execution status.

Prefer trust_remote_code=False unless a model genuinely requires custom code and the code has been reviewed.

### 5.4 Governance

Map the capstone controls to the NIST Generative AI Profile:

- Govern: ownership, policy, approvals, and incident handling;
- Map: data sensitivity, users, model limits, and failure modes;
- Measure: quality, calibration, latency, cost, leakage, and injection resistance;
- Manage: routing thresholds, mitigations, rollback, and residual risk.

The NIST profile is a governance framework, not a substitute for testing the actual model and system ([NIST AI RMF Generative AI Profile](https://www.nist.gov/itl/ai-risk-management-framework/ai-rmf-generative-ai-profile)).

## 6. Experiment plan for the client discussion

| Experiment | Controlled comparison | Required outputs |
|---|---|---|
| Model fit | Llama 3.1 8B versus Qwen3 8B, same prompts and generation contract | load success, peak VRAM, throughput, latency, quality |
| Precision | FP16 baseline where feasible versus 4-bit NF4 | quality delta, memory reduction, latency delta |
| Hardware | T4 versus A10G, same model and software versions | throughput, p50/p95 latency, peak memory |
| Context | 4K, 8K, and 32K prompts | quality, latency, KV-cache growth, OOM behavior |
| Cache | DynamicCache versus one justified alternative | memory, latency, correctness |
| Confidence W7 | raw-logit token features | calibration, AUROC or AUPRC, error slices |
| Confidence extension | k=5 semantic agreement and SEP probe | incremental accuracy, calibration, latency, memory |
| Routing | local-only versus thresholded local/cloud | accuracy, escalation rate, cost per request, latency |
| Privacy | redacted versus non-redacted approved test data | PII recall, false positives, task-quality impact |
| Security | direct and indirect prompt-injection cases | blocked-action rate, false positives, audit completeness |
| Jev comparison | typed decision task on approved data | decision accuracy, calibration, latency, cost, schema reliability |

Every result should include the dataset version, prompt template, model revision, software lockfile, hardware, seed, and run identifier. Without that metadata, a new model release cannot be compared fairly with the original result.

## 7. Client decisions to confirm

The client discussion should confirm:

1. Which request categories are always local, even when local confidence is low?
2. Which categories may be redacted and escalated?
3. Is the GPU sandbox T4, A10G, or both, and what concurrency target matters?
4. What is the acceptable latency budget for interactive requests?
5. What escalation rate is acceptable if it improves correctness?
6. Which PII classes must be detected before any external call?
7. Is Jev allowed for any client data, or only synthetic and public data?
8. Which legal review is required for the Llama license and any hosted service?
9. Does the client prefer a smaller, auditable local model or a larger model with higher infrastructure cost?
10. Which failure cases must be demonstrated in the final presentation?

## Final position

The capstone should present a measured local-first system, not a race to adopt the newest model. Llama 3.1 8B and Qwen3 8B provide a manageable first comparison. Transformers in-process plus bitsandbytes NF4 gives the project the local evidence needed for log-probability and hidden-state experiments. FP16 on the T4, explicit cache measurements, pinned revisions, and a project-owned router keep the MVP reproducible.

Jev is worth testing as a separate structured-decision baseline, but it is hosted and does not replace local token-level or hidden-state evidence. Qwen3.5-9B, Qwen3.8-27B, Llama 4, speculative decoding, and more elaborate semantic-entropy pipelines should be treated as controlled follow-up experiments.

The client-facing conclusion should be supported by four numbers for each tested configuration: accuracy, p95 latency, cost per request, and escalation rate. Add PII leakage and prompt-injection resistance as release gates, not as informal claims.

## Evidence discipline applied to the Gemini research

Retained and integrated:

- local-first hybrid architecture;
- the KV-cache sizing method;
- log-probability, multi-sample, and SEP confidence paths;
- local PII replacement and re-identification;
- privilege separation for prompt injection;
- pinned artifacts, safetensors, and NIST governance mapping.

Corrected or excluded:

- BF16 was replaced with FP16 for the T4 baseline;
- unverified model benchmark tables and exact tokens-per-second claims were not presented as project results;
- absolute claims about zero data retention and safetensors safety were rewritten as conditions requiring verification;
- newer models were separated from the MVP instead of being treated as automatic replacements;
- Jev was classified as a hosted typed-decision comparison, not a text-generation substitute.

## Selected sources

- [Hugging Face Transformers generation API](https://huggingface.co/docs/transformers/main_classes/text_generation)
- [Transformers generation output implementation](https://github.com/huggingface/transformers/blob/main/src/transformers/generation/utils.py)
- [Hugging Face bitsandbytes quantization](https://huggingface.co/docs/transformers/main/en/quantization/bitsandbytes)
- [Hugging Face KV-cache strategies](https://huggingface.co/docs/transformers/main/en/kv_cache)
- [Meta Llama 3.1 model card](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/MODEL_CARD.md)
- [Meta Llama 3.1 license](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE)
- [Qwen3 8B model card](https://huggingface.co/Qwen/Qwen3-8B)
- [Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B)
- [Qwen3.8-27B model card](https://huggingface.co/Qwen/Qwen3.8-27B)
- [Meta Llama 4 announcement](https://ai.meta.com/blog/llama-4-multimodal-intelligence/)
- [Semantic Entropy Probes paper](https://arxiv.org/html/2406.15927)
- [NVIDIA T4 datasheet](https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/tesla-t4/t4-tensor-core-datasheet-951643.pdf)
- [NVIDIA CUDA compute capabilities](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/compute-capabilities.html)
- [Microsoft Presidio Analyzer](https://microsoft.github.io/presidio/analyzer/)
- [safetensors documentation](https://huggingface.co/docs/safetensors/index)
- [NIST AI RMF Generative AI Profile](https://www.nist.gov/itl/ai-risk-management-framework/ai-rmf-generative-ai-profile)
- [Jev announcement](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
- [Jev documentation](https://docs.typesafe.ai/introduction)
- [Jev master customer agreement](https://typesafe.ai/legal/mca)
