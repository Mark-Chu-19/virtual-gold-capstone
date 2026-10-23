# Virtual Gold Capstone — Hybrid Local/Cloud AI Assistant

CMU MISM Capstone, Fall 2026, for **Virtual Gold Inc** (AI consulting, Brooklyn NY).
Client contact: Urte Jesina. Team: 5 people.

We are building and evaluating a **local sanitization service**: a standalone HTTP service, running an open-source model on our own hardware, that strips private information out of text before it reaches a cloud AI model. The client's own assistant calls it automatically, before any text leaves for the cloud. Deciding what counts as private — reliably enough to measure, in a setting where the same string is confidential in one context and public in another — is the research problem.

> **Direction set at the Sep 21 client meeting:** the horizontal scenario (this service) first; the vertical scenario (a trading assistant over public filings) deferred to time-permitting status. Anything in this repository written before that date describes the earlier design, a hybrid assistant with confidence-based escalation.
>
> **Current baseline: the midterm deck as presented on 2026-10-05** [`meetings/client/2026-10-05/Midterm Client Presentation Slides(Virtual Gold).pdf`](<meetings/client/2026-10-05/Midterm Client Presentation Slides(Virtual Gold).pdf>) (49 slides) is the team consensus, agreed inside the team and with the professor. Where any older document disagrees with it, the deck wins. Its decisions are in the `todo/TODO.md` decision log; slide numbers there refer to this deck.

## Where we are (Week 9, updated 2026-10-23)

| Item | Status |
|---|---|
| Design: six steps in one local service ("the model judges, code decides"), three sensitivity tiers, calibrated scores, fail-safe redaction, restore as a separate call | Agreed 2026-10-03, midterm deck slides 13–32 |
| Midterm presentation to the client | Held 2026-10-05; notes in `meetings/client/2026-10-05/` |
| Scope of Work | `docs/sow/Scope of Work -  20261005.docx` given to the client at the midterm; signature not recorded (`todo/TODO.md` E68) |
| API contract 0.4.2 and service skeleton (M1) | Done 2026-10-19, PR #7: `docs/api/`, `service/` |
| Privacy Research components (rules, Presidio, merge, calibration, decision, pseudonymisation) | Done 2026-10-23, PR #8: `service/vg_redactor/privacy/` |
| End-to-end pipeline with failure path (M2) | In progress, due 2026-11-01; prompts and parsers are still stubs |
| **Open: request-level routing and "documents" as input.** The final deck and the SOW include both; contract 0.4.2 has neither | To decide, `todo/TODO.md` A14, A15 |
| Evaluation dataset: 100 fictional executive emails, 999 labelled items, 18 types | Built (Karina); not yet committed to `data/`. Oct 5: also source an already-labelled external dataset as ground truth (A16) |
| Model | Benchmarked Llama 3.1 8B and Qwen 2.5 7B; Gemma 4 next; one model for now (A13) |
| GPU / sandbox for the local model | Waiting on the client since 2026-09-15; test over the web or with Ollama meanwhile |
| Architecture document v0.4 | Not started; the deck and `docs/api/` stand in until then |

Milestones from the deck: Oct 11 contract 0.4.2 and service skeleton · Nov 1 end-to-end pipeline with failure path · Nov 8 dashboard and load-test results · Nov 15 VG08 integration, contract freeze · Nov 22 code freeze (soft freeze Nov 18) · Nov 30 final presentation. Phase 1 (service on its own) Oct 26–Nov 8, Phase 2 (VG08) Nov 2–15.

## History (Weeks 1–9)

| Milestone | Status |
|---|---|
| Client kickoff, brief received | Done |
| Architecture draft v0.1 (layers, request flow, confidence scoring, de-identification pipeline) | Done, 2026-09-07 |
| Teammate proposal (tooling, datasets, defaults, MVP vs stretch) reviewed and merged into **v0.2** | Done, 2026-09-08 |
| Architecture **v0.3**: Sep 15 decisions written in (transformers, own router, RAG stretch, sensitivity + de-identification in MVP, midpoint scope); PR #2 confidence-harness content goes into v0.3.1 after merge | Done, 2026-09-15 |
| Team decisions on the section 11 to-do list: tool selection (HF transformers, own router, Presidio), RAG deferred to stretch, sensitivity classification and de-identification round trip in the MVP | Decided, 2026-09-15 (`todo/TODO.md` decision log) |
| Cloud provider: follows whichever the client supplies credits for, default Anthropic | Pending client answer |
| Section 10 defaults walked through with the client | Done 2026-09-15; use case and cost line deferred |
| PR workflow set up (branch → PR → Mark reviews and merges) | Done, 2026-09-08 |
| Scope of Work revised (`docs/sow/Scope of Work v2.docx`, changes in red); cost line still needs the client's answer | v2 done, 2026-09-10 |
| Team decision: no local LLM on laptops; models run on a cloud GPU sandbox simulating on-premises | Decided, 2026-09-10 |
| Client meeting Sep 15: OpenAI and Anthropic accounts confirmed; use case deferred (vertical finance vs horizontal data sanitization; Inderpal proposed a trading assistant on public filings); Alex to review the sensitivity gate; sandbox spec and SOW cost line still open | Notes in `meetings/client/2026-09-15/` |
| Team meeting Sep 18 (Fri): settle the use-case answer, workstream owners, two research one-pagers; one email to the client before the Sep 21 client meeting | Agenda in `meetings/team/2026-09-18/` |
| Confidence-scoring harness design doc and literature review (Zhexuan Ye, PR #2) | Merged 2026-09-21, in `docs/research/` |
| Workstream owners: router Mark · models Anmol · confidence/harness Zhexuan · security Yudi · synthetic data Karina | Set 2026-09-18 |
| Finance QA benchmark: FinQA (MIT); FinanceBench reserve only | Decided 2026-09-21 |
| Karina's PRs #3 (schema), #4 (demo batch), #5 (SEC fetch + data) | Open; scope questions under team discussion |
| Week 4: sandbox setup, harness skeleton (sampling core, loaders, metrics), workstream research one-pagers | In progress |
| Week 7: midpoint presentation with first local-only / hybrid / cloud-only numbers on MMLU subset and GSM8K (scope in `todo/TODO.md` A7) | Target |
| **Client meeting Sep 21: direction changed.** Team aligned to prioritize the horizontal scenario and privacy module first, deferring the vertical (trading assistant) to time-permitting; horizontal framed around a chief-of-staff assistant; the module is to be a **standalone service with an HTTP API endpoint**, not an MCP server | Notes in `meetings/client/2026-09-21/notes-gemini-en.pdf` |
| Aarvin George (Virtual Gold alumnus, developer of the VG08 assistant) joined as technical counterpart. Our service is an intermediate layer; the main agent orchestration is theirs. He owes an initial API contract; Alex and Aarvin own the endpoint spec | Notes p7; his onboarding email in `meetings/client/2026-09-21/email-aarvin-onboarding-en.md` |
| NDA addendum with CMU still unsigned; the client is reluctant to share internal architecture until it is. The standalone-HTTP approach is explicitly a workaround for that | Notes p4, p7; follow-up owned by Inderpal |
| Architecture doc v0.3 describes the pre-pivot design and has **not** been revised for the horizontal direction yet | Open; the midterm deck is the architecture of record until v0.4 |
| Team meeting Sep 25 (Fri): team produced its own architecture proposal for the horizontal direction | Held; the proposals are in `docs/research/` (2026-09-24, 2026-09-27) |
| Team alignment Sep 27 (Sun): category list, labelling fields, unsure-model handling; whole-email vs section taken to the client | Notes in `meetings/team/2026-09-27/`; partly superseded by the midterm deck |
| Client meeting Sep 28 (Mon): presented the horizontal architecture; aligned on English-only input, two test phases (standalone, then VG08), testing early with cloud-hosted open-source models or Ollama; Slack workspace and Drive set up | Agenda and Gemini notes in `meetings/client/2026-09-28/` |
| Midterm deck agreed by the team and the professor | 2026-10-03 |
| Midterm presentation Oct 5 (Mon): 49-slide deck; preliminary benchmark (local models beat rules + Presidio, close to the cloud model); aligned on an external labelled dataset as ground truth and one model for now | Deck and Gemini notes in `meetings/client/2026-10-05/` |
| PR #7 (Zhexuan): contract 0.4.2, service skeleton, dashboard | Merged 2026-10-19 |
| PR #8 (Yudi): Privacy Research components | Merged 2026-10-23 |

## Read this first

**Until architecture v0.4 exists, the source of truth is the midterm deck,
[`meetings/client/2026-10-05/Midterm Client Presentation Slides(Virtual Gold).pdf`](<meetings/client/2026-10-05/Midterm Client Presentation Slides(Virtual Gold).pdf>)**,
together with the `todo/TODO.md` decision log and the API contract in [`docs/api/`](docs/api/).

> **Note (2026-09-27):** v0.3 describes the pre-pivot design (hybrid assistant with confidence-based
> routing). The Sep 21 client meeting changed the direction to a standalone sanitization service for
> the horizontal scenario. v0.3 has not yet been revised; treat its request-flow and scope sections as
> out of date until a v0.4 lands.

The v0.3 document, kept for history, in four formats:


| File | Language | Format |
|---|---|---|
| [`docs/architecture/architecture-v0.3-en.md`](docs/architecture/architecture-v0.3-en.md) | English | Markdown, Mermaid diagrams (renders on GitHub) |
| [`docs/architecture/architecture-v0.3-en.html`](docs/architecture/architecture-v0.3-en.html) | English | HTML with SVG diagrams, open in a browser |
| [`docs/architecture/architecture-v0.3-zh.md`](docs/architecture/architecture-v0.3-zh.md) | Traditional Chinese | Markdown, Mermaid diagrams |
| [`docs/architecture/architecture-v0.3-zh.html`](docs/architecture/architecture-v0.3-zh.html) | Traditional Chinese | HTML with SVG |

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
├── README.md                      start here: progress, open decisions, layout
├── docs/                          documents WE write and hand over
│   ├── api/                       API contract 0.4.2 and service interfaces (Zhexuan), the current spec
│   │   ├── redaction-api-report-en-v0.4.2.md   the HTTP contract
│   │   └── service-interfaces-v0.4.2-{en,zh}.md  component signatures and the service layout
│   ├── architecture/              the architecture document (v0.3 is pre-pivot; the deck stands in until v0.4)
│   │   ├── architecture-v0.3-en.md      English, Markdown (renders on GitHub)
│   │   ├── architecture-v0.3-en.html    English, HTML with SVG diagrams
│   │   ├── architecture-v0.3-zh.md      Traditional Chinese, Markdown
│   │   ├── architecture-v0.3-zh.html    Traditional Chinese, HTML
│   │   └── horizontal-draft/            Mark's personal drafts for the post-pivot horizontal design.
│   │                                    NOT the team's proposal — fallback only, see the banner in each file
│   ├── sow/                       Scope of Work, every version kept
│   │   ├── Scope of Work v1.docx        original draft (W3)
│   │   ├── Scope of Work v2.docx        revised 2026-09-10, pre-pivot
│   │   ├── Scope of Work v3.docx        written from the Oct 3 deck draft
│   │   └── Scope of Work -  20261005.docx   the version given to the client at the midterm (current; name kept as given)
│   └── research/                  research reports and design docs, by author then date: anmol/ karina/ yudi/ zhexuan/ (see its README)
├── service/                       the local redaction service (Python, FastAPI); see service/README.md
│   ├── vg_redactor/               gateway, pipeline, records, model adapter, metrics; privacy/ components; stubs/
│   ├── config/                    service, policy (tiers), calibration, context store
│   ├── dashboards/                Prometheus + Grafana, 8-panel dashboard
│   └── tests/                     contract, failure-injection, leak and component tests
├── meetings/                      one folder per meeting, named YYYY-MM-DD: the agenda we bring plus the notes that come out
│   ├── client/                    meetings with Virtual Gold
│   │   ├── 2026-09-03/            notes-gemini-en.pdf
│   │   ├── 2026-09-15/            agenda-en.html · agenda-zh.html · notes-gemini-en.pdf · notes-zh.md
│   │   ├── 2026-09-21/            agenda-{en,zh}.html · notes-gemini-en.pdf
│   │   │                          briefing-security-deidentification-en.html (Yudi)
│   │   │                          financial-data-sources-en.pdf · email-aarvin-onboarding-en.md
│   │   ├── 2026-09-28/            agenda-{en,zh}.html · notes-gemini-en.pdf
│   │   └── 2026-10-05/            Midterm Client Presentation Slides(Virtual Gold).pdf   the midterm deck as given, the current baseline
│   │                              notes-gemini-en.pdf
│   ├── team/                      internal team meetings, not shared with the client
│   │   ├── 2026-09-18/            agenda-en.html · agenda-zh.html
│   │   └── 2026-09-27/            agenda-{en,zh}.html · notes-{en,zh}.md · deferred-{en,zh}.md
│   └── professor/                 (not created yet) weekly check-ins with the faculty advisor
├── todo/                          team to-do: open decisions, pending actions, decision log
│   ├── TODO.md                    English
│   └── TODO-zh.md                 Traditional Chinese
├── reference/                     inputs we did NOT write; read-only
│   ├── client/                    Virtual Gold Inc - AI Assistant.pdf          original capstone brief
│   └── course/                    Proposed Weekly Structure.pdf                15-week course structure we must follow
├── .github/                       CODEOWNERS, pull_request_template.md
└── data/                          (not created yet) the evaluation dataset; fictional or public only, never real data
```

Rule of thumb: `docs/` is what we author and hand over (API contract, architecture, SOW, research), `service/` is the code, `meetings/` is everything about one meeting in one place, `reference/` is what we were handed (client or course), `todo/` is what we still have to decide, `data/` is the evaluation dataset.

### Naming conventions

- Every bilingual file carries a language suffix: `-en` or `-zh`. The exception is `todo/TODO.md`, which is English (`TODO-zh.md` is the Chinese copy).
- Meeting folders are `YYYY-MM-DD`. Inside: `agenda-<lang>.html` for the running order, `briefing-<topic>-<lang>.html` for a presentation piece one workstream brings, `slides-<topic>-<lang>.pdf` for a full slide deck, `notes-<source>-<lang>` for what comes out (`gemini` = the auto-generated notes, `zh` = our translation), `email-<who>-<topic>-<lang>.md` for correspondence that belongs to that meeting.
- Versions live in the filename: `architecture-v0.3-*`, `Scope of Work v3`, `-v0.4.2`. A new version is a new file; old versions stay for history.
- Files exactly as the client received them keep their original name: `Scope of Work -  20261005.docx`, `Midterm Client Presentation Slides(Virtual Gold).pdf`.

## Meeting cadence

| Meeting | When | Folder |
|---|---|---|
| Client meeting (Virtual Gold) | Monday 18:00–19:00, weekly | `meetings/client/` |
| Internal meeting with the professor | Tuesday 17:00–18:20 | `meetings/professor/` |
| Internal team meeting | Friday 15:30–16:30 | `meetings/team/` |

All times US Eastern. Agendas go up before the meeting, notes go in after, both in the meeting's own dated folder.

## Timeline (follows the course structure, not negotiable)

| Weeks | Phase |
|---|---|
| W1–W3 | Setup: team, kickoff, architecture sign-off |
| W4–W6 | Direction change (Sep 21), horizontal design, evaluation dataset |
| W7 | **Midterm presentation, Mon Oct 5.** Contract 0.4.2 and service skeleton by Oct 11 |
| W8 | Fall break (week of Oct 12), no work |
| W9–W10 | Gateway, records, model adapter, pipeline wiring and failure path: end-to-end by Nov 1. Phase 1, the service tested on its own, from late October |
| W11–W13 | Phase 2, VG08 integration, from Nov 2. Dashboard and load test by Nov 8 · integration and contract freeze Nov 15 · code freeze Nov 22 (soft freeze Nov 18) |
| W14–W15 | Documentation, final evaluation, rehearsal (W14 Thanksgiving). **Final presentation Mon Nov 30** |

## Open decisions

Tracked in [`todo/TODO.md`](todo/TODO.md) (English) and [`todo/TODO-zh.md`](todo/TODO-zh.md) (Traditional Chinese): decisions, pending actions, items waiting on the client, the Scope of Work, and a decision log. The TODO is aligned with the midterm deck as presented (49 slides) and the Sep 28 and Oct 5 client notes: items they made obsolete are listed under "Closed and superseded". Section 11 of the architecture doc is out of date and will be replaced in v0.4.

## Contributing workflow

Three rules:

1. **Never push to `main` directly.** Not even for a one-line fix.
2. **One branch, one topic.** Small PRs get reviewed fast; big ones sit.
3. **Every change goes through a pull request.** Mark reviews and merges. Nobody merges their own PR.

**Owner exception:** Mark, as repository owner and the person who reviews everything, may push to `main` directly. Everyone else opens a PR.

There is no technical lock on `main` right now, so this works only if all of us follow it. If we later turn on branch protection, the steps below stay exactly the same.

### Branch names

| Prefix | Use for | Example |
|---|---|---|
| `docs/` | architecture document, SOW, research, meeting agendas, README | `docs/v0.3-rag-decision` |
| `feat/` | new code in `service/` | `feat/privacy-components` |
| `fix/` | bug fixes | `fix/tombstone-unknown-id` |
| `eval/` | datasets, benchmark runs, results | `eval/benchmark-100` |
| `todo/` | decisions and the decision log | `todo/week3-decisions` |

### Step by step

**1. Start from the latest `main`.** Do this every time before you begin, otherwise your PR will conflict.

```bash
git checkout main
git pull origin main
```

**2. Create a branch.**

```bash
git checkout -b feat/privacy-components
```

**3. Make your changes and commit.** Commit message: one line, starts with a verb, says what changed.

```bash
git add service/vg_redactor/privacy/rules.py
git commit -m "Add money-amount pattern to the rule detector"
```

**4. Push the branch to GitHub.**

```bash
git push -u origin feat/privacy-components
```

**5. Open the pull request.** GitHub shows a **Compare & pull request** button after the push. Click it, fill in the template (What, Why, Type, Checklist), and click **Create pull request**. Mark is added as reviewer automatically.

**6. Wait for review.** Mark replies within two working days. If he asks for changes, commit again on the same branch and push; the PR updates by itself:

```bash
git add .
git commit -m "Read thresholds from policy.yaml instead of hardcoding"
git push
```

**7. Merge.** When Mark approves, he clicks **Squash and merge**. Your PR becomes one commit on `main` and the branch is deleted automatically.

**8. Next task:** go back to step 1.

### If your PR has conflicts

GitHub will say "This branch has conflicts that must be resolved". Bring `main` into your branch, fix the conflicting files, then push:

```bash
git fetch origin
git merge origin/main
# open the files GitHub lists, resolve the <<<<<<< ======= >>>>>>> blocks
git add .
git commit -m "Merge main into feat/privacy-components"
git push
```

### Where files go

- Anything we author goes in `docs/` (architecture, SOW, research one-pagers); anything a teammate or the client sends us goes in `reference/`; anything about a meeting, ours or theirs, goes in that meeting's folder under `meetings/`.
- Decisions go in `todo/`: tick the item and add a row to the decision log. If a decision changes the architecture, update `docs/` in the same PR.
- `docs/`, `meetings/` agendas and `todo/` exist in English and Traditional Chinese; keep both in sync, or say in the PR which one is ahead. The README is English only.
- Code goes in `service/`; the evaluation dataset goes in `data/`.

## Notes on data

The client provides **public data only**, no PII. All evaluation uses public datasets plus LLM-generated synthetic enterprise data. Do not commit any real customer or third-party data to this repository.
