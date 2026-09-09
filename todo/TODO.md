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
| 5 | **Local models and hardware** | Llama 3.1 8B primary, Qwen3 8B secondary. Confirm RAM and GPU on all five laptops; pick quantization level. Local inference environment: develop on laptops with a small model (Qwen3 4B / Llama 3.2 3B), run benchmarks on a CMU cloud GPU instance (see B14). A self-hosted VM we control still counts as "local" in the architecture. | | | [ ] |
| 6 | **Cloud provider: OpenAI or Anthropic** | Compare enterprise data-retention terms and pricing. | | | [ ] |
| 7 | **What to show at the W7 midpoint** | Suggested minimum: local-only vs hybrid accuracy and escalation rate on MMLU subset and GSM8K. | | | [ ] |
| 8 | **Work split** | Router / models and inference / evaluation harness / security and de-identification / docs and presentations. One owner each. | | | [ ] |

## B. Pending actions

| # | Action | Owner | Due | Done |
|---|---|---|---|---|
| 9 | Send section 10 defaults (architecture doc) to the client for confirmation; proceed on defaults unless the client objects | | | [ ] |
| 10 | Bump architecture doc to v0.3 once A1–A4 are decided and the client answers B9 | | | [ ] |
| 11 | Set up local environments: Ollama plus the two models on every laptop | | W4 | [ ] |
| 12 | Stand up the evaluation-harness skeleton (three configurations, six metrics, logging) | | W4 | [ ] |
| 13 | Prepare MMLU subset and GSM8K test sets; generate first synthetic enterprise queries | | W5 | [ ] |
| 14 | **Request a GPU instance through CMU Public Cloud Services.** Submit the no-cost consultation form (students must name a faculty/staff member: Randy), then email Randall Trzeciak with the justification and cost estimate, cc Randy. Ask for one T4-class VM (AWS g4dn.xlarge or equivalent), 100 GB storage, $100 budget cap with alerts. Needed by W4 for first benchmark runs. | Mark | W4 | [ ] |
| 15 | **Ask whether the team can get a CMU GitHub Enterprise Cloud organization.** Free, includes branch protection, but the service is aimed at internal projects and faculty/staff must request it. Add the question to the same email to Randall/Randy. If yes, move the repo there and enable protection on `main`; if no, keep the convention-based PR workflow. | Mark | W4 | [ ] |

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

## Decision log

Record decisions here so nobody reopens them.

| Date | Decision | Rationale |
|---|---|---|
| 2026-09-07 | Local-first hybrid architecture with confidence-based escalation and sensitivity gating (architecture v0.1) | Matches the client brief |
| 2026-09-08 | Adopt teammate proposal's three-configuration evaluation, named datasets, defaults-instead-of-questions style, MVP vs stretch split (architecture v0.2) | More concrete and matches client's preference for defaults |
| 2026-09-08 | Timeline follows the course's 15-week structure without change | Midpoint W7 and breaks are fixed by the course |
