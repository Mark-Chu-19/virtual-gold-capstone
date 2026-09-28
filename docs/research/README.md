# Research and design documents

One document per workstream question, written by the workstream owner, in English with a Traditional Chinese copy where the team needs one (`-en` / `-zh` suffix). Markdown preferred; `.docx` and `.html` are fine when that is what the author works in.

## Layout

```
docs/research/<author>/<date>/<file>
```

- **`<author>`** is the writer's first name in lower case: `anmol`, `karina`, `mark`, `yudi`, `zhexuan`.
- **`<date>`** is `YYYY-MM-DD`, the date the document carries for itself. For a versioned document it is the date of its current version, so revising a document to a new version moves it to a new folder and the old one stays as history. Where a document states no date, the date it was delivered is used.
- File names keep the `-en` / `-zh` suffix and do not repeat the author or the date.

A document belongs to whoever wrote it, not to whoever the topic now belongs to. The Sep 25 reassignment moved several areas between people; the folders record authorship and do not move with it.

## What is here

| Author | Date | Document |
|---|---|---|
| Anmol | 2026-09-20 | `models-inference-research-en.md` — model selection, local inference, quantization, KV-cache sizing |
| Karina | 2026-09-20 | `financial-data-sources-en.md` — licensing review of financial data sources; FinQA adopted |
| Karina | 2026-09-24 | `redact-always-proposal-en.html` — mask every detected span, restore locally; alternative privacy design |
| Yudi | 2026-09-19 | `security-deidentification-report-en.docx` — 17-paper review: sensitivity is not PII, two scores not one gate |
| Yudi | 2026-09-27 | `sensitive-data-classification-proposal-{en,zh}.html` — tiers, thresholds, calibration, evaluation plan |
| Zhexuan | 2026-09-13 | `confidence-scoring-harness-report-{en,zh}.md` — literature review behind the confidence harness |
| Zhexuan | 2026-09-15 | `confidence-harness-design-{en,zh}.md` — harness design, v0.2 |
| Zhexuan | 2026-09-21 | `confidence-gating-design-draft-zh.pdf` — confidence scheduling and the confidentiality gate |

## What belongs here

- The one-page research summaries from `todo/TODO.md` section F.
- Design documents that turn a research result into a build plan, and design proposals put to the team.

## What does not

Meeting agendas and notes (`meetings/`), the architecture document itself (`docs/architecture/`), documents other people handed us (`reference/`).

## Note for open pull requests

PR #3 adds `docs/research/synthetic-data-schema-en.md` at the old flat path, and `financial-data-sources-en.md` already links to it there. When that branch is brought up to date the file goes to `docs/research/karina/<its date>/synthetic-data-schema-en.md` and the link needs updating in the same pass.
