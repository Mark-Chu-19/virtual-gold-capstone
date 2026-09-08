# Virtual Gold Capstone — Hybrid Local/Cloud AI Assistant

CMU MISM Capstone, Fall 2026, for **Virtual Gold Inc** (AI consulting, Brooklyn NY).
Client contact: Urte Jesina. Team: 5 people.

We are designing and evaluating a **local-first enterprise AI assistant**: open-source models running locally are the primary intelligence layer, every response gets a measured confidence score, and requests escalate to a cloud model only when confidence is low **and** data sensitivity allows. Sensitive data stays local.

## Current status (Week 3, updated 2026-09-08)

| Milestone | Status |
|---|---|
| Client kickoff, brief received | Done |
| Architecture draft v0.1 (layers, request flow, confidence scoring, de-identification pipeline) | Done, 2026-09-07 |
| Teammate proposal (tooling, datasets, defaults, MVP vs stretch) reviewed and merged into **v0.2** | Done, 2026-09-08 |
| Team decisions on the section 11 to-do list (tool selection, RAG, sensitivity classification, cloud provider) | **Open, this week** |
| Send section 10 defaults to the client for confirmation | Pending |
| Week 4: start MVP build, evaluation harness skeleton | Not started |
| Week 7: midpoint presentation with first local-only vs hybrid numbers | Target |

## Read this first

The single source of truth is the architecture document. Same content in four formats:

| File | Language | Format |
|---|---|---|
| [`architecture-v0.2-en.md`](architecture-v0.2-en.md) | English | Markdown, Mermaid diagrams (renders on GitHub) |
| [`architecture-v0.2-en.html`](architecture-v0.2-en.html) | English | HTML with SVG diagrams, open in a browser |
| [`architecture-v0.2-zh.md`](architecture-v0.2-zh.md) | 繁體中文 | Markdown, Mermaid |
| [`architecture-v0.2.html`](architecture-v0.2.html) | 繁體中文 | HTML with SVG |

Sections in the document:

1. Problem and objective
2. Design principles
3. System layers (Figure 1)
4. Core request flow (Figure 2)
5. Confidence scoring — the research core
6. De-identification and re-identification pipeline (Figure 3), *for discussion*
7. Evaluation design and datasets (three configurations, six metrics, named public datasets)
8. Security and governance
9. Scope and timeline, MVP commitments vs stretch goals
10. Proposed defaults and assumptions for the client to confirm
11. **Team discussion items (to-do)**
12. Next steps

## Repository layout

```
.
├── README.md
├── architecture-v0.2-en.md / .html      current architecture doc (English)
├── architecture-v0.2-zh.md / .html      current architecture doc (Chinese)
├── Virtual_Gold_Data_Architecture_Proposal_1.docx   teammate's Data & Architecture proposal (source for v0.2 merge)
├── Virtual Gold Inc - AI Assistant.pdf  client's original capstone brief
├── Proposed Weekly Structure.pdf        15-week course structure
└── archive/                             v0.1 drafts, kept for history
```

## Timeline (follows the course structure, not negotiable)

| Weeks | Phase |
|---|---|
| W1–W3 | Setup: team, kickoff, **architecture sign-off (now)** |
| W4–W7 | MVP build. **W7 midpoint presentation** |
| W8 | Fall break |
| W9–W11 | Full three-configuration evaluation, red-teaming, de-identification round trip |
| W12–W15 | Analysis, report, client feedback. **W15 final presentation** (W14 Thanksgiving) |

## Open decisions (see section 11 of the architecture doc)

- [ ] Tool selection: LiteLLM / Ollama / Presidio / RouteLLM approach — proposed, **not yet decided**
- [ ] Keep a minimal RAG knowledge layer or drop it
- [ ] Include data sensitivity classification (confidential never leaves local) in the MVP
- [ ] De-identification round trip: MVP or stretch; placeholders vs format-preserving fake values for numbers
- [ ] Local models and hardware: Llama 3.1 8B primary, Qwen3 8B secondary; confirm laptop specs
- [ ] Cloud provider: OpenAI or Anthropic
- [ ] What to show at the W7 midpoint
- [ ] Corrections to the teammate proposal (model names, diagram arrow, citations, timeline)
- [ ] Work split across the five of us

## How to contribute

- Edit the **Markdown** files for content changes; the HTML versions are the presentation copies and get regenerated from the same content.
- Keep English and Chinese versions in sync, or note in the PR which one is ahead.
- Version bumps: v0.2 → v0.3 when the section 11 decisions are made and the client confirms section 10.
- Datasets and code will live in `data/` and `src/` once the MVP starts in week 4.

## Notes on data

The client provides **public data only**, no PII. All evaluation uses public datasets plus LLM-generated synthetic enterprise data. Do not commit any real customer or third-party data to this repository.

---

## 中文摘要

這是 CMU MISM Capstone 專案,客戶是 Virtual Gold Inc。目標是設計並評估一套本地優先的混合式企業 AI 助理:本地開源模型為主,量測回覆信心,只有在信心低且資料敏感度允許時才升級到雲端模型。

目前進度在第 3 週:架構文件 v0.2 已完成,合併了組員的工具、資料集與預設方案提案。本週要在團隊會議上決定第十一節的待討論事項(工具選型、RAG 去留、敏感度分級、雲端供應商),然後把第十節的預設方案送客戶確認,第 4 週開工建 MVP。

架構文件請看 `architecture-v0.2-zh.md`,英文版是 `architecture-v0.2-en.md`,內容相同。
