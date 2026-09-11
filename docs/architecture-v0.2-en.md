# Hybrid AI Assistant Architecture Draft

**Capstone · Virtual Gold Inc · Week 3 · Scope & Project Charter**

A local-first enterprise AI assistant: open-source models are the primary intelligence layer, and requests escalate to cloud models only when confidence scores and data sensitivity allow.

| Version | Date | Status | Team | Client |
|---|---|---|---|---|
| v0.2.1 | 2026-09-10 | Team discussion | Anmol · Mark · Yudi · Zhexuan · Karina | Inderpal Bhandari · Alex Bhandari · Urte Jesina |

---

## 1. Problem and objective

Organizations want to deploy AI assistants but struggle to balance data privacy, security, cost, model reliability, and vendor dependence. Open-source models offer control and privacy but may fall short on complex tasks. Cloud models are more capable but raise compliance, security, and cost concerns.

This project designs and evaluates a hybrid architecture: **local open-source models act as the primary intelligence layer**, every response gets a **measured confidence score**, and requests are **escalated to cloud models only when necessary**, keeping sensitive data local whenever possible.

## 2. Design principles

| Principle | Meaning |
|---|---|
| **Local first** | Every request is handled by a local model by default. The cloud is an escalation path, not the default path. |
| **Data classification decides routing** | Confidential data never leaves the local environment, regardless of how low local confidence is. |
| **Escalation must be justified** | Every escalation can state its reason: score, task type, budget. All of it is logged. |
| **Replaceable components** | Models, vector stores, and cloud providers plug in through abstract interfaces to avoid vendor lock-in. |

## 3. System layers

There is exactly one place where the system crosses the trust boundary: the routing layer sends redacted, minimized content to the cloud. Every other layer runs inside the enterprise network.

```mermaid
flowchart TB
  subgraph LOCAL["Local environment · enterprise network"]
    L1["1 User interface<br/>Web chat UI · CLI · REST API"]
    L2["2 Gateway & policy<br/>Auth · PII redaction · sensitivity classification · prompt-injection filter · rate limiting"]
    L3["3 Router & orchestration<br/>Task classification · policy check · escalation decision · response assembly"]
    L4["4 Local inference<br/>Ollama / vLLM · Llama 3.x, Qwen, Mistral"]
    L5["5 Confidence scoring<br/>logprob · self-consistency · verifier · grounding"]
    L6["6 Knowledge (RAG)<br/>Local embeddings · Chroma / Qdrant / pgvector"]
    L7["7 Governance & observability<br/>Audit log · cost tracking · benchmarks · model provenance"]
    L8["8 Security foundation<br/>Egress allow-list · sandbox · secrets · model hash & license checks"]
    L1 --> L2 --> L3
    L3 -- generate --> L4
    L3 <-- score --> L5
    L4 -- retrieve --> L6
    L3 -.logs.-> L7
    L7 --- L8
  end
  subgraph CLOUD["External · cloud providers"]
    C["Cloud escalation<br/>Claude / GPT / Gemini API"]
  end
  L3 -- "redacted, minimized (trust boundary)" --> C
  C -- reply --> L3
  style L5 stroke:#A8842C,stroke-width:2px
  style C fill:#E5ECF6,stroke:#4B6A9B,stroke-width:2px
```

**Figure 1.** Everything inside the local box runs in the enterprise environment. The only channel crossing the trust boundary carries redacted content from the router to the cloud and the reply back. The confidence scoring module is the research core of this project. See Figure 3 for the detail of this channel.

| # | Layer | Responsibilities |
|---|---|---|
| 1 | User interface | Web chat UI, CLI, REST API |
| 2 | Gateway & policy | Auth, PII detection & redaction, sensitivity classification, prompt-injection filter, rate limiting |
| 3 | Router & orchestration | Task classification, policy check, escalation decision, response assembly |
| 4 | Local inference | Ollama / vLLM; Llama 3.x, Qwen, Mistral |
| 5 | Confidence scoring | logprob, self-consistency, verifier model, retrieval grounding |
| 6 | Knowledge (RAG) | Local embeddings; Chroma / Qdrant / pgvector |
| 7 | Governance & observability | Audit log, cost tracking, benchmarks, model provenance |
| 8 | Security foundation | Egress allow-list, sandbox, secrets management, model hash & license checks |
| — | Cloud escalation (external) | Claude / GPT / Gemini API; receives only redacted, minimized content |

## 4. Core request flow

A request passes three decision points on its way to a reply: sensitivity classification, the confidence threshold, and whether escalation is permitted. All three outcomes are written to the audit log.

```mermaid
flowchart LR
  U[User request] --> G["Gateway<br/>PII redaction · classify"]
  G --> M["Local model<br/>generate with RAG"]
  M --> S[Confidence score]
  S --> D1{Score ≥ threshold?}
  D1 -- yes --> R[Reply to user]
  D1 -- no --> D2{Sensitivity allows escalation?}
  D2 -- "yes (public / internal)" --> C["Cloud model<br/>redact, minimize"]
  C --> R
  D2 -- "no (confidential)" --> H["Reply: cannot answer locally<br/>or hand off to a human"]
  style M fill:#E1EFEC,stroke:#2A6E68
  style S stroke:#A8842C,stroke-width:2px
  style C fill:#E5ECF6,stroke:#4B6A9B
  style H stroke:#B4562A
```

**Figure 2.** The confidence score decides whether escalation is needed; the sensitivity class decides whether escalation is allowed. When both fail, the system admits uncertainty rather than sending confidential data out.

Step by step:

1. The gateway authenticates the user, scans for PII, and tags the request as public, internal, or confidential.
2. The router classifies the task (Q&A, summary, code, reasoning) and retrieves relevant documents through RAG.
3. The local model generates a response and the confidence module scores it.
4. If the score meets the threshold, the response is returned directly.
5. If the score is below the threshold and the sensitivity class permits, the content is redacted and minimized, then sent to a cloud model.
6. If the class is confidential, the request is never sent out. The system replies that it cannot answer locally or hands off to a human.
7. Every decision, score, cost, and latency is written to the audit log for later evaluation.

## 5. Confidence scoring: the research core

The client proposal's "measure confidence in generated responses" is the technical highlight of this project. We recommend building it as a standalone module that supports several strategies, then comparing them in the benchmark. The midpoint presentation can show the trade-offs across three dimensions: escalation rate, answer quality, and cost.

| Strategy | How it works | Extra cost | Accuracy tendency | Best for |
|---|---|---|---|---|
| Token probability | Mean logprob or entropy, taken directly from model output | Near zero | Moderate; prone to overconfidence | Baseline for the MVP |
| Self-consistency | Sample the same question N times and check agreement | Latency × N | Better | Q&A and calculations with a definite answer |
| Verifier model | A small local model acts as judge and grades the response | One extra small inference | Good, but depends on judge quality | Open-ended generation, summaries |
| Retrieval grounding | Whether the response is supported by retrieved RAG documents | Low | Very good for knowledge Q&A | Internal knowledge-base questions |
| Task heuristics | Decide by task type, e.g. multi-step reasoning escalates by default | Zero | Coarse but predictable | Stacked on top of other strategies |

> **Recommendation:** start the MVP with token probability plus task heuristics. They cost the least and produce the first batch of data fastest. Add the other strategies one at a time for comparison.

## 6. De-identification and re-identification pipeline (for discussion)

The "redacted, minimized" arrow in Figure 1 unfolds into a round-trip pipeline. When a request really has to go to the cloud, this pipeline is itself a design feature, and the "map it back on return" step is the one most often forgotten.

1. **Detect:** find sensitive entities in the request and the retrieved document chunks: names, organizations, amounts, account numbers, dates. Use an NER model plus regex rules, for example a tool like Presidio.
2. **Replace with placeholders:** not blacked out, but swapped for an identifier, e.g. "Jane Doe" becomes PERSON_1. The same entity keeps the same identifier for the whole conversation.
3. **Keep the mapping table local:** the table that says PERSON_1 = Jane Doe never leaves the local environment.
4. **Minimize, then send:** send only the chunks this question needs, never the whole document or conversation history.
5. **Re-identify:** placeholders in the cloud reply are mapped back to real names locally before the reply reaches the user.

Even if a cloud provider stores the request, what it holds cannot be linked to a real individual. This goes straight into the security assessment and answers the client's compliance and international-model concerns.

```mermaid
flowchart LR
  subgraph LOCAL["Local environment · enterprise network"]
    A[Raw request] --> B["Detect entities<br/>NER + regex rules"]
    B --> C["Replace<br/>PERSON_1 · ORG_1"]
    C --> D["Minimize<br/>only needed chunks"]
    C -- write --> T["Mapping table<br/>PERSON_1 = Jane Doe<br/>never leaves local"]
    T -- look up --> E["Re-identify<br/>placeholders back to names"]
    E --> F[Reply to user]
  end
  D -- "placeholders only (trust boundary)" --> X["Cloud model<br/>sees only PERSON_1, ORG_1"]
  X -- reply with placeholders --> E
  style T fill:#F4ECD8,stroke:#A8842C,stroke-width:2px
  style X fill:#E5ECF6,stroke:#4B6A9B,stroke-width:2px
```

**Figure 3.** De-identification and re-identification pipeline. Sensitive entities are swapped for placeholders locally, the mapping table stays local, and the cloud sees only placeholders; the reply is mapped back to real names on the way in. This pipeline is the concrete evidence behind "sensitive data stays local."

### Four design challenges for discussion

| Challenge | What goes wrong | Candidate approaches |
|---|---|---|
| Placeholders break reasoning | "How much higher is this amount than last quarter?" cannot be computed once the amount is AMOUNT_1. | Tiered handling: identity fields become identifiers; numeric fields get format-preserving fake values that are scaled back afterwards; or keep only the numbers the calculation needs. |
| Detection miss rate | Any entity the NER model misses leaks straight through. | Plant sensitive data in many formats into synthetic datasets and measure how much the pipeline catches. A good experiment in its own right. |
| Semantic leakage | The name is gone, but "the consulting firm in Brooklyn founded in 1997" still identifies it. | Cannot be fully prevented. Let sensitivity classification mark such content as non-exportable and rate the residual risk. |
| Re-identification accuracy | The cloud model may rewrite PERSON_1 as "Person 1" or "that individual", so the lookup fails. | Fuzzy matching; flag unmatched placeholders to the user instead of silently dropping them. |

**Where it sits in the architecture:** detection and replacement belong to layer 2, the gateway; the mapping table, minimization, and re-identification belong to layer 3, the router.
**Measurable metrics** go on the layer 7 governance dashboard: tokens sent per request, entities replaced, re-identification success rate, miss rate. These numbers turn "privacy" into something visible.

## 7. Evaluation design and datasets

The same test set runs under three configurations. That is the only way to answer the client's real question: how much cost the hybrid design saves, how much quality it gives up, and how much data it leaks. This is the main experimental design for the midpoint and final presentations.

| Configuration | Description | Purpose |
|---|---|---|
| Local-only | Every request answered by the local model, no escalation | Quality floor, cost floor, privacy ceiling |
| Hybrid | Local first; confidence score and sensitivity decide escalation | This project's proposal; measure where it lands between the two extremes |
| Cloud-only | Every request sent straight to the cloud model | Quality ceiling, cost ceiling, privacy floor |

**Six metrics per configuration:** accuracy, latency, cost per query, escalation rate, PII-leak rate, prompt-injection resistance. For the hybrid configuration we also plot the escalation-rate vs accuracy curve, AUROC, and calibration error from section 5.

### Datasets and benchmarks

The client provides public data only, so each evaluation dimension uses an established public dataset instead of labeling from scratch. All items are public, license-permitting, and contain no PII.

| Purpose | Dataset / tool | Source | Why it fits |
|---|---|---|---|
| General capability gap | MMLU (subset) | Hugging Face cais/mmlu | Measures the quality gap between a small local model and a frontier cloud model across knowledge domains |
| Reasoning and escalation check | GSM8K | Hugging Face openai/gsm8k | Math reasoning where local models often fail; validates whether the router escalates correctly |
| Enterprise / SMB context | Support-ticket sets, B2B SaaS sample | Hugging Face Tobi-Bueck/customer-support-tickets, Kaludi/Customer-Support-Responses; Kaggle sarahdaily/b2b-saas-hubspot | Style and structure reference only; the team generates synthetic tickets, emails, and memos with an LLM. No real data at any point |
| Routing benchmark | RouterBench | arXiv:2403.12031 | Benchmark and methodology built for multi-LLM routing cost, quality, and latency trade-offs |
| Confidence calibration / hallucination | TruthfulQA, HaluEval | Hugging Face; GitHub EdinburghNLP/awesome-hallucination-detection | Tests whether the confidence score actually tracks factual correctness, the core of the brief's confidence objective |
| Security: PII redaction | Presidio evaluation module | GitHub microsoft/presidio | Built-in evaluation method, no hand-labeled corpus needed; also measures the miss rate from section 6 |
| Security: prompt injection | Prompt Injection & Benign Prompt Dataset | Kaggle cyberprince | Labeled injection vs benign prompts for red-teaming the security gate |

> **Midpoint target:** before the week 7 midpoint, have at least local-only vs hybrid accuracy and escalation rate on the MMLU subset and GSM8K. The full three-configuration run belongs in weeks 9 to 11.

## 8. Security and governance

- **Egress allow-list:** local inference services can only reach the approved cloud APIs, preventing models or packages from leaking data in the background.
- **Model supply-chain checks:** record every model's source, hash, and license. This directly addresses the client's concern about international AI models and lets us include Qwen, DeepSeek, and similar models in the evaluation.
- **Two-way guardrails:** block prompt injection on input and sensitive-data leakage on output.
- **Complete audit trail:** every escalation can answer "what was sent, why, and at what cost."
- **Sandboxed environment:** students work on their own machines with public or synthetic data and never touch enterprise systems.

## 9. Scope and timeline

The timeline follows the 15-week course structure and does not change. The work splits into three phases, with the first numbers due before the week 7 midpoint.

| Weeks | Phase | Scope |
|---|---|---|
| W1–W3 | Setup | Team formation, client kickoff, **architecture sign-off (this week)** |
| W4–W7 | **MVP** | Local model + basic confidence strategy + router + PII gate + evaluation harness. **W7 midpoint presentation.** |
| W8 | Fall break | — |
| W9–W11 | **Extend** | Full three-configuration run, strategy comparison, de-identification round trip, red-teaming |
| W12–W15 | **Converge** | Benchmark report, governance recommendations, draft deliverable, client feedback, **W15 final presentation** (W14 Thanksgiving) |

### MVP: the team's committed deliverable

All five team members are full-time graduate students carrying a full course load; this project is roughly a third of one semester's credits. The target is therefore a working prototype plus a rigorous evaluation, not a production platform. Existing open-source components are preferred so effort goes into integration, evaluation, and the security and governance analysis.

- **Router and orchestration:** the team writes the routing policy; the gateway tool is still open (see section 11, item 1).
- **Local inference:** Llama 3.1 8B as the primary model, Qwen3 8B as the secondary for code and multilingual queries; served with Ollama on a GPU sandbox that simulates on-premises (see "Deployment environment" below). Team decision 2026-09-10: no LLMs on laptops, laptops are for development only.
- **Confidence scoring:** self-consistency or token logprob as the baseline signal.
- **PII redaction gate:** between the router and any cloud call, directly implementing "keep sensitive data local".
- **Cloud escalation:** one mainstream enterprise-grade API, called only on low confidence.
- **Evaluation and logging harness:** the three configurations and six metrics from section 7.
- **Undecided:** a minimal RAG knowledge layer and data sensitivity classification (see section 11, items 2 and 3).

### Stretch goals: only if the MVP lands early

- Task-aware routing by query type and complexity, not confidence alone, evaluated with the RouterBench methodology.
- A second local model for A/B comparison, or a small trained router instead of a threshold rule.
- Format-preserving fake values and fuzzy re-identification in the de-identification pipeline.
- Deeper red-teaming across more prompt-injection and jailbreak categories.
- Local model enhancement (confirmed in scope at the Sep 3 meeting): quantization comparison, prompt tuning, LoRA fine-tuning on synthetic data.
- An executive summary deck translating findings into governance recommendations.

### Deployment environment: a cloud sandbox that simulates on-premises

On 2026-09-10 the team decided not to run LLMs on laptops. Models run on a GPU host in a cloud sandbox instead: the client offered a sandbox at the Sep 3 meeting, with CMU Public Cloud Services as the fallback; laptops are for development only. What makes an environment "on-premises" is who controls it and whether data can leave, so the sandbox simulates that boundary, and the boundary must be verifiable.

```
internal network (no internet)      egress network (allow-list only)
├── ollama      local model          └── egress-proxy  single exit, logs every request
├── chroma      vector store / RAG           ↑
├── presidio    de-identification            │
├── audit-db    audit log                    │
└── router  ── attached to both networks ────┘
```

- **Network boundary:** the VM sits in a private network. Nothing comes in except SSH or Tailscale for the team; nothing goes out except the allow-listed cloud LLM API. This is the layer 8 egress allow-list.
- **Container isolation:** Docker Compose with two networks. The model, vector store, de-identification, and audit log live on `internal`, which cannot even resolve external DNS; only the router is attached to both networks, and it reaches the internet only through the egress proxy. The trust boundary in Figure 1 is enforced, not just drawn.
- **Audited exit:** the proxy allows only allow-listed domains and logs every request. PII-leak rate and tokens sent per request are measured here; turning the proxy off gives the local-only configuration.
- **Verifiable:** three automated tests in the evaluation harness: outbound from the model container must fail; the router must fail outside the allow-list and succeed inside it; a request containing a real name must appear in the proxy log with placeholders only. Runnable live at the midpoint.
- **Hardware scenarios:** run the same test set under no GPU (CPU), T4, A10G, 4-bit vs 8-bit, and fully offline, to answer "how much on-prem hardware buys how much less cloud traffic" and to satisfy the SOW requirement to report needs for locally attainable hardware.


## 10. Proposed defaults and assumptions for the client to confirm

The client prefers concrete defaults over open questions. Each item below has a default the team will proceed on unless the client redirects before implementation starts in week 4.

| Item | Default | Why | Client can change |
|---|---|---|---|
| Sensitivity levels | Three levels: public, internal, confidential. Defined by the team from common enterprise practice; confidential never leaves local. | No client classification standard yet; start with a working default. | Replace with the client's own standard. |
| Escalation approval | Fully automatic, every escalation logged; human approval is a stretch goal. | Feasible in one semester and consistent with "escalation must be justified". | Add a review step at the second decision point. |
| Cloud provider | One provider for the MVP: OpenAI or Anthropic, both publish enterprise data-retention commitments. | Fewer variables; multi-provider comparison is a stretch goal. | Name a provider, region, or compliance constraint. |
| International open-source models | Qwen3 8B as the secondary model, with supply-chain checks (source, hash, license). | The brief explicitly raises international-model risk; evaluating one is the only way to conclude. | Ask to exclude it. |
| Hardware and compute environment | Models run on a GPU sandbox (T4-class, 16 GB) that simulates on-premises; 8B-class model at 4-bit quantization. No LLMs on laptops. | Team decision 2026-09-10; the client offered a sandbox on Sep 3. | Confirm sandbox spec and cost; an A10G-class GPU allows 14B tests. |
| Numeric sensitive data | Placeholders for everything in the MVP; format-preserving fake values are a stretch goal. | Prevent leakage first, enable computation second. | See section 11, item 4. |
| Governance framework | NIST AI RMF (Govern, Map, Measure, Manage), noting where ISO/IEC 42001 would extend it. | Free, self-attestation based, suited to a one-semester practical risk assessment. | Switch to ISO 42001 if certification-grade work is needed. |
| Data sources | Public datasets from section 7 plus LLM-generated synthetic data; no real data at any point. | The client provides public data only. | Provide example documents or formats as an extra seed. |
| Use case / sector | Default focus: financial-services SMB document workflows (Q&A, summarization, extraction). | On Sep 3 the client said a sector focus is welcome and data follows once the use case is set. | Switch to real estate or another sector. |
| Who pays | Cloud model API credits and sandbox compute provided by the client; otherwise CMU Public Cloud Services with a $100 cap. | The SOW does not yet state cost ownership; confirm and write it in. | Set a credit cap or provide a provider account. |

## 11. Team discussion items (to do)

- [ ] **Tool selection, not yet decided.** Teammate proposal: LiteLLM as the routing gateway, Ollama for local models, Presidio for PII detection, the RouteLLM approach for the routing signal. To confirm: whether LiteLLM can host a custom routing policy and de-identification hooks; RouteLLM is pre-generation routing that looks at the query, which is a different thing from post-generation confidence scoring that looks at the answer, so evaluate them separately; whether Ollama exposes logprobs conveniently or vLLM is needed.
- [ ] **Keep the RAG knowledge layer or not.** The teammate version has none; this draft does. Affects: the demo value of answering questions about enterprise documents, the retrieval-grounding confidence strategy, and whether de-identification must handle document chunks. Leaning toward a minimal version; cut it and tell the client if time runs out.
- [ ] **Include data sensitivity classification in the MVP?** The teammate version has only PII redaction, no "confidential never leaves" rule. One extra rule in the router; low cost, recommended.
- [ ] **De-identification round trip: MVP or stretch?** The re-identification step is missing from the teammate version; decide placeholders vs fake values for numeric data at the same time.
- [ ] **Local models and sandbox.** Llama 3.1 8B primary, Qwen3 8B secondary; decided: no LLMs on laptops. Confirm with the client the sandbox offered on Sep 3 (spec, availability, cost) and cloud API credits; CMU cloud is the fallback.
- [ ] **Pick one cloud provider.** OpenAI or Anthropic. Compare enterprise data-retention terms and pricing, then decide.
- [ ] **What to show at the week 7 midpoint.** Suggested minimum: local-only vs hybrid accuracy and escalation rate on the MMLU subset and GSM8K.
- [ ] **Corrections needed in the teammate proposal.** "Llama 3.3 8B" should be Llama 3.1 8B (3.3 exists only at 70B); "Qwen3 7B" should be Qwen3 8B (7B is Qwen2.5); in the diagram the "high confidence, return answer" arrow should not pass through the PII gate; cite Meta and Qwen model cards for model figures and the NIST text for the framework instead of blog posts; align the timeline with the course's W7 midpoint and W8 fall break.
- [ ] **Use case and sector.** The client provides data only once the use case is set. Default: financial-services SMB document workflows; confirm with the client this week.
- [ ] **Work split.** Router, models and inference, evaluation harness, security and de-identification, documentation and presentations: one owner each.

## 12. Next steps

1. Walk through the section 11 list at this week's team meeting; settle tool selection and the RAG decision first.
2. Send the section 10 defaults to the client for confirmation; proceed on the defaults unless the client objects.
3. Start in week 4: fix the local model and inference framework, stand up the evaluation-harness skeleton, and aim for the first local-only vs hybrid numbers before W7.

---

*Hybrid AI Assistant Architecture Draft v0.2.1 · Capstone for Virtual Gold Inc · 2026-09-10*
