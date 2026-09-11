# Team To-Do

Single place for open decisions and pending actions. Tick items here; when a decision changes the architecture, update `docs/` in the same PR.
Fill in **Owner** and **Due** at the team meeting. Chinese version: [`TODO-zh.md`](TODO-zh.md).

## A. Decisions to make this week (Week 3)

| # | Item | Notes | Owner | Due | Done |
|---|---|---|---|---|---|
| 1 | **Tool selection** (not yet decided) | Proposal: LiteLLM routing gateway, Ollama local inference, Presidio PII detection, RouteLLM approach for routing signal. Confirm: can LiteLLM host a custom routing policy and de-identification hooks; RouteLLM is pre-generation routing (looks at the query) vs post-generation confidence scoring (looks at the answer), evaluate separately; does Ollama expose logprobs conveniently or do we need vLLM. | | | [ ] |
| 2 | **Keep a minimal RAG knowledge layer or drop it** | Teammate proposal has none; architecture doc has one. Affects enterprise-document demo value, the retrieval-grounding confidence strategy, and whether de-identification handles document chunks. Leaning: keep minimal, cut if time runs out and tell the client. | | | [ ] |
| 3 | **Data sensitivity classification in MVP?** | "Confidential never leaves local" rule. One extra rule in the router; low cost, recommended. | | | [ ] |
| 4 | **De-identification round trip: MVP or stretch** | Re-identification step is missing from the teammate proposal. Decide placeholders vs format-preserving fake values for numeric data at the same time. | | | [ ] |
| 5 | **Local models and sandbox** | **Decided 2026-09-10: no LLMs on laptops.** Models run on a GPU sandbox that simulates on-premises; laptops are for development only. Still open: confirm the sandbox the client offered on Sep 3 (provider, GPU, access, availability, who pays), confirm cloud API credits, pick quantization level. CMU cloud (B15) is the fallback. | Mark | W4 | [ ] |
| 6 | **Cloud provider: OpenAI or Anthropic** | Compare enterprise data-retention terms and pricing. | | | [ ] |
| 7 | **What to show at the W7 midpoint** | Suggested minimum: local-only vs hybrid accuracy and escalation rate on MMLU subset and GSM8K. | | | [ ] |
| 8 | **Use case / sector** | Client said on Sep 3 that a sector focus (e.g. financial or real estate) is welcome and that data will be provided once the use case is set. Proposed default: financial-services SMB document workflows (Q&A, summarization, extraction). Confirm with the client. | | W4 | [ ] |
| 9 | **Work split and research** | Five workstreams, one owner each: router and integration; models and inference; confidence scoring and evaluation harness; security and de-identification; RAG and synthetic data. Each workstream starts with applied-paper and tool research for its area, see section F. Docs and slides: each owner writes their part, Mark consolidates. | | W4 | [ ] |

## B. Pending actions

| # | Action | Owner | Due | Done |
|---|---|---|---|---|
| 10 | Send section 10 defaults (architecture doc) to the client for confirmation; proceed on defaults unless the client objects | | | [ ] |
| 11 | Bump architecture doc to v0.3 once A1–A4 are decided and the client answers B10 | | | [ ] |
| 12 | Set up the sandbox: Ollama plus the two models on the GPU host; laptops get only the client code and a small dev model | | W4 | [ ] |
| 13 | Stand up the evaluation-harness skeleton (three configurations, six metrics, logging) | | W4 | [ ] |
| 14 | Prepare MMLU subset and GSM8K test sets; generate first synthetic enterprise queries | | W5 | [ ] |
| 15 | **Confirm compute and credits with the client, CMU cloud as fallback.** Ask the client: (a) the cloud sandbox offered on Sep 3: provider, GPU, access method, availability, who pays; (b) cloud model API credits or keys (OpenAI or Anthropic) and a budget cap; (c) whether the sandbox can host both the simulated-local VM and the cloud calls. If either is unavailable, request a GPU instance through CMU Public Cloud Services: consultation form with Randy as faculty contact, then email Randall Trzeciak with justification and cost estimate (T4-class VM, 100 GB, $100 cap), cc Randy. Needed by W4. | Mark | W4 | [ ] |

## C. Corrections to the teammate Data & Architecture proposal

File: `reference/team/Virtual_Gold_Data_Architecture_Proposal_1.docx`

| # | Fix | Done |
|---|---|---|
| 16 | "Llama 3.3 8B" → Llama 3.1 8B (Llama 3.3 exists only at 70B) | [ ] |
| 17 | "Qwen3 7B" → Qwen3 8B (7B is Qwen2.5) | [ ] |
| 18 | Diagram: the "high confidence → return answer" arrow must not pass through the PII redaction gate | [ ] |
| 19 | Cite Meta and Qwen model cards for model figures and the NIST AI RMF text for the framework, instead of blog posts | [ ] |
| 20 | Align timeline with the course: W7 midpoint, W8 fall break, W14 Thanksgiving | [ ] |

## D. Waiting on the client

| # | Item | Asked on | Answer |
|---|---|---|---|
| 21 | Confirm or redirect the eight defaults in section 10 | | |
| 22 | Any example documents or formats for the "enterprise and small business data" mentioned in the brief | | |
| 23 | Whether international open-source models (Qwen3) may be included in the evaluation | | |

## E. Scope of Work edits before signing

Original: `docs/Scope of Work.docx` (dated Sep 15, 2026). **Revised: `docs/Scope of Work v2.docx`, changes in red.** Everything else in the SOW is consistent with the architecture doc.

| # | Edit | Done |
|---|---|---|
| 24 | Section 6, assumption 3: replace "Development and experimentation will primarily occur on student laptops, desktops, or other approved sandboxed computing environments" with "Development and experimentation will primarily occur in a cloud-based sandbox environment provided by the Client, configured to simulate an on-premises enterprise deployment; student laptops are used for development only." The SOW does not mention CMU resources. | [x] |
| 25 | Section 6: add a dependency: "The Client will provide access to a cloud-based sandbox environment for testing, as discussed on September 3, 2026." | [x] |
| 26 | Section 6 cost ownership: written in v2 as a red paragraph stating the Client covers costs, with a $[X] placeholder; once B15 is answered, fill in the amount and remove the "to be confirmed" note. The SOW does not mention the CMU fallback. | [ ] |
| 27 | Section 5, Phase 1: append "and begin early prototyping to validate architectural assumptions" (requested by Alex on Sep 3). | [x] |

## F. Research list (by workstream)

Research deliverable for each workstream in W4: a one-page summary answering "can this tool or method be used in our architecture, how, and what are the limits", with source links. Read the official docs and paper abstracts first; no need to read every paper end to end.

| # | Workstream | Owner | What to research | Questions to answer |
|---|---|---|---|---|
| 28 | Router and integration | | LiteLLM docs: custom callbacks, pre-call hooks, guardrails, fallbacks. RouteLLM paper (Ong et al. 2024, arXiv:2406.18665). RouterBench (Hu et al. 2024, arXiv:2403.12031). FrugalGPT LLM cascades (Chen et al. 2023, arXiv:2305.05176). Hybrid LLM quality-aware routing (Ding et al. 2024, arXiv:2404.14618). AutoMix self-verification routing (Madaan et al. 2023, arXiv:2310.12963). | Can LiteLLM host a custom routing policy and de-identification hooks, or is it only a provider adapter? RouteLLM is pre-generation routing that looks at the query; how do we compare it in the harness against post-generation confidence scoring that looks at the answer? How does the FrugalGPT cascade differ from our design? |
| 29 | Models and inference | | Whether the Ollama API returns logprobs, current status and issues. llama.cpp server logprobs support. vLLM hardware requirements. Effect of GGUF quantization levels (Q4_K_M, Q8_0) on accuracy and speed. Official model cards and license terms for Llama 3.1 8B and Qwen3 8B. | Ollama, llama.cpp, or vLLM for logprobs? Roughly how many tokens/s for 8B at 4-bit on a T4? Does the Qwen3 license restrict enterprise use? |
| 30 | Confidence scoring and evaluation harness | | Self-consistency (Wang et al. 2022, arXiv:2203.11171). Semantic entropy (Kuhn et al. 2023, arXiv:2302.09664; Farquhar et al. 2024, Nature). Models knowing what they know (Kadavath et al. 2022, arXiv:2207.05221). SelfCheckGPT (Manakul et al. 2023, arXiv:2303.08896). Reliability of verbalized confidence (Xiong et al. 2023, arXiv:2306.13063). Calibration metrics: ECE, AUROC, escalation-rate vs accuracy curve. Data formats and scoring for MMLU, GSM8K, TruthfulQA, HaluEval. | Which confidence signals actually work on an 8B model? How many extra inferences does each cost? How should the harness be built to run three configurations and output six metrics in one pass? |
| 31 | Security and de-identification | | Presidio recognizers, custom entities, evaluation module. Privacy-conscious delegation, PAPILLON (Siyan et al. 2024, arXiv:2410.17127). OWASP Top 10 for LLM Applications. Indirect prompt injection (Greshake et al. 2023, arXiv:2302.12173). NIST AI RMF 1.0 and the Generative AI Profile (NIST AI 600-1). | Roughly what miss rate does Presidio have on synthetic enterprise documents? Is there existing work on sending placeholders to the cloud and re-identifying on return? Which NIST items does our risk assessment map to? |
| 32 | RAG and synthetic data | | Chroma vs pgvector. Chunking strategies and choice of a locally runnable embedding model (e.g. bge, nomic-embed). Retrieval grounding and faithfulness evaluation (e.g. RAGAS faithfulness). Methods for generating synthetic enterprise documents and Q&A seeded from the support-ticket and B2B datasets. | What is the scope of a minimal RAG that can be built in one day? How is a grounding score computed so it can serve as a confidence signal? How much synthetic data do we need and how do we label sensitivity levels? |

## Decision log

Record decisions here so nobody reopens them.

| Date | Decision | Rationale |
|---|---|---|
| 2026-09-03 | Client kickoff decisions: hybrid architecture with a mandatory local model; evaluate with general-purpose benchmarks and show performance comparable to cloud; local model enhancement in scope; no GUI; client provides a cloud sandbox; weekly meetings during discovery | Sep 3 client meeting notes (reference/team/Meeting Notes/2026-09-03) |
| 2026-09-07 | Local-first hybrid architecture with confidence-based escalation and sensitivity gating (architecture v0.1) | Matches the client brief |
| 2026-09-08 | Adopt teammate proposal's three-configuration evaluation, named datasets, defaults-instead-of-questions style, MVP vs stretch split (architecture v0.2) | More concrete and matches client's preference for defaults |
| 2026-09-08 | Timeline follows the course's 15-week structure without change | Midpoint W7 and breaks are fixed by the course |
| 2026-09-10 | No local LLM on laptops. Models run on a cloud GPU sandbox that simulates an on-premises environment; laptops are for development only | Laptops cannot run 8B models at benchmark speed; the client offered a sandbox on Sep 3; a VM we control still satisfies the "local" requirement |
