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
| 9 | **Work split** | Router / models and inference / evaluation harness / security and de-identification / docs and presentations. One owner each. | | | [ ] |

## B. Pending actions

| # | Action | Owner | Due | Done |
|---|---|---|---|---|
| 10 | Send section 10 defaults (architecture doc) to the client for confirmation; proceed on defaults unless the client objects | | | [ ] |
| 11 | Bump architecture doc to v0.3 once A1–A4 are decided and the client answers B10 | | | [ ] |
| 12 | Set up the sandbox: Ollama plus the two models on the GPU host; laptops get only the client code and a small dev model | | W4 | [ ] |
| 13 | Stand up the evaluation-harness skeleton (three configurations, six metrics, logging) | | W4 | [ ] |
| 14 | Prepare MMLU subset and GSM8K test sets; generate first synthetic enterprise queries | | W5 | [ ] |
| 15 | **Confirm compute and credits with the client, CMU cloud as fallback.** Ask the client: (a) the cloud sandbox offered on Sep 3: provider, GPU, access method, availability, who pays; (b) cloud model API credits or keys (OpenAI or Anthropic) and a budget cap; (c) whether the sandbox can host both the simulated-local VM and the cloud calls. If either is unavailable, request a GPU instance through CMU Public Cloud Services: consultation form with Randy as faculty contact, then email Randall Trzeciak with justification and cost estimate (T4-class VM, 100 GB, $100 cap), cc Randy. Needed by W4. | Mark | W4 | [ ] |
| 16 | **Ask whether the team can get a CMU GitHub Enterprise Cloud organization.** Free, includes branch protection, but the service is aimed at internal projects and faculty/staff must request it. Add the question to the same email to Randall/Randy. If yes, move the repo there and enable protection on `main`; if no, keep the convention-based PR workflow. | Mark | W4 | [ ] |

## C. Corrections to the teammate Data & Architecture proposal

File: `reference/team/Virtual_Gold_Data_Architecture_Proposal_1.docx`

| # | Fix | Done |
|---|---|---|
| 17 | "Llama 3.3 8B" → Llama 3.1 8B (Llama 3.3 exists only at 70B) | [ ] |
| 18 | "Qwen3 7B" → Qwen3 8B (7B is Qwen2.5) | [ ] |
| 19 | Diagram: the "high confidence → return answer" arrow must not pass through the PII redaction gate | [ ] |
| 20 | Cite Meta and Qwen model cards for model figures and the NIST AI RMF text for the framework, instead of blog posts | [ ] |
| 21 | Align timeline with the course: W7 midpoint, W8 fall break, W14 Thanksgiving | [ ] |

## D. Waiting on the client

| # | Item | Asked on | Answer |
|---|---|---|---|
| 22 | Confirm or redirect the eight defaults in section 10 | | |
| 23 | Any example documents or formats for the "enterprise and small business data" mentioned in the brief | | |
| 24 | Whether international open-source models (Qwen3) may be included in the evaluation | | |

## E. Scope of Work edits before signing

File: `docs/Scope of Work.docx` (dated Sep 15, 2026). Everything else in the SOW is consistent with the architecture doc.

| # | Edit | Done |
|---|---|---|
| 25 | Section 6, assumption 3: replace "Development and experimentation will primarily occur on student laptops, desktops, or other approved sandboxed computing environments" with "Development and experimentation will primarily occur in a cloud-based sandbox environment provided by the Client or by CMU Computing Services, configured to simulate an on-premises enterprise deployment; student laptops are used for development only." | [ ] |
| 26 | Section 6: add a dependency: "The Client will provide access to a cloud-based sandbox environment for testing, as discussed on September 3, 2026." | [ ] |
| 27 | Section 6: add cost ownership once B15 is answered, e.g. "The Client will provide cloud model API credits up to $X and sandbox compute; otherwise compute is provided through CMU Public Cloud Services." | [ ] |
| 28 | Section 5, Phase 1: append "and begin early prototyping to validate architectural assumptions" (requested by Alex on Sep 3). | [ ] |

## Decision log

Record decisions here so nobody reopens them.

| Date | Decision | Rationale |
|---|---|---|
| 2026-09-07 | Local-first hybrid architecture with confidence-based escalation and sensitivity gating (architecture v0.1) | Matches the client brief |
| 2026-09-08 | Adopt teammate proposal's three-configuration evaluation, named datasets, defaults-instead-of-questions style, MVP vs stretch split (architecture v0.2) | More concrete and matches client's preference for defaults |
| 2026-09-08 | Timeline follows the course's 15-week structure without change | Midpoint W7 and breaks are fixed by the course |
| 2026-09-10 | No local LLM on laptops. Models run on a cloud GPU sandbox that simulates an on-premises environment; laptops are for development only | Laptops cannot run 8B models at benchmark speed; the client offered a sandbox on Sep 3; a VM we control still satisfies the "local" requirement |
