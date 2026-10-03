# Virtual Gold Capstone — Hybrid Local/Cloud AI Assistant

CMU MISM Capstone, Fall 2026, for **Virtual Gold Inc** (AI consulting, Brooklyn NY).
Client contact: Urte Jesina. Team: 5 people.

We are building and evaluating a **local sanitization service**: a standalone HTTP service, running an open-source model on our own hardware, that strips private information out of text before it reaches a cloud AI model. The client's own assistant calls it automatically, before any text leaves for the cloud. Deciding what counts as private — reliably enough to measure, in a setting where the same string is confidential in one context and public in another — is the research problem.

> **Direction set at the Sep 21 client meeting:** the horizontal scenario (this service) first; the vertical scenario (a trading assistant over public filings) deferred to time-permitting status. Anything in this repository written before that date describes the earlier design, a hybrid assistant with confidence-based escalation.
>
> **Current baseline (2026-10-03): the midterm deck** [`meetings/client/2026-10-05/slides-midterm-en.pdf`](meetings/client/2026-10-05/slides-midterm-en.pdf) is the team consensus, agreed inside the team and with the professor. Where any older document disagrees with it, the deck wins. Its decisions are in the `todo/TODO.md` decision log (rows dated 2026-10-03).

## Where we are (Week 6, updated 2026-10-03)

| Item | Status |
|---|---|
| Design: six steps in one local service ("the model judges, code decides"), three sensitivity tiers, calibrated scores, fail-safe redaction, restore as a separate call | Agreed 2026-10-03, midterm deck slides 10–29 |
| Evaluation dataset: 100 fictional executive emails, 999 labelled items, 18 types | Built (Karina); not yet committed to `data/` |
| Midterm presentation to the client | Monday 2026-10-05, 18:00 |
| Scope of Work v3, revised to the deck's scope, to be signed at the midterm | Owed before the meeting (`todo/TODO.md` B36) |
| API contract 0.4.2 and service skeleton | Milestone 1, due 2026-10-11 |
| GPU / sandbox for the local model | Waiting on the client since 2026-09-15 |
| Architecture document v0.4 | Not started; the deck stands in until then |

Milestones from the deck: Oct 11 contract 0.4.2 and service skeleton · Nov 1 end-to-end pipeline with failure path · Nov 8 dashboard and load-test results · Nov 15 VG08 integration, contract freeze · Nov 22 code freeze (soft freeze Nov 18) · Nov 30 final presentation.

## History (Weeks 1–5)

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
| Client meeting Sep 28 (Mon): presented the horizontal architecture; six asks (GPU, NDA, midterm, Drive, chat, SOW) | Agenda in `meetings/client/2026-09-28/`; no notes recorded |
| Midterm deck agreed by the team and the professor | 2026-10-03, `meetings/client/2026-10-05/` |

## Read this first

**Until architecture v0.4 exists, the source of truth is the midterm deck,
[`meetings/client/2026-10-05/slides-midterm-en.pdf`](meetings/client/2026-10-05/slides-midterm-en.pdf)**,
together with the 2026-10-03 rows of the `todo/TODO.md` decision log.

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
│   ├── architecture/              the architecture document, single source of truth, four formats
│   │   ├── architecture-v0.3-en.md      English, Markdown (renders on GitHub)
│   │   ├── architecture-v0.3-en.html    English, HTML with SVG diagrams
│   │   ├── architecture-v0.3-zh.md      Traditional Chinese, Markdown
│   │   ├── architecture-v0.3-zh.html    Traditional Chinese, HTML
│   │   └── horizontal-draft/            Mark's personal drafts for the post-pivot horizontal design.
│   │                                    NOT the team's proposal — fallback only, see the banner in each file
│   ├── sow/                       Scope of Work drafts
│   │   ├── Scope of Work v1.docx        original draft (W3)
│   │   └── Scope of Work v2.docx        revised, changes in red; sign this one once the cost line is filled in
│   └── research/                  research reports and design docs, by author then date: anmol/ karina/ yudi/ zhexuan/ (see its README)
├── meetings/                      one folder per meeting, named YYYY-MM-DD: the agenda we bring plus the notes that come out
│   ├── client/                    meetings with Virtual Gold
│   │   ├── 2026-09-03/            notes-gemini-en.docx
│   │   ├── 2026-09-15/            agenda-en.html · agenda-zh.html · notes-gemini-en.pdf · notes-zh.md
│   │   ├── 2026-09-21/            agenda-{en,zh}.html · agenda-en.pdf · notes-gemini-en.pdf
│   │   │                          briefing-security-deidentification-en.{html,pdf} (Yudi)
│   │   │                          financial-data-sources-en.pdf · email-aarvin-onboarding-en.md
│   │   ├── 2026-09-28/            agenda-{en,zh}.html · agenda-en.pdf
│   │   └── 2026-10-05/            slides-midterm-en.pdf   midterm presentation, the current baseline
│   ├── team/                      internal team meetings, not shared with the client
│   │   ├── 2026-09-18/            agenda-en.html · agenda-zh.html
│   │   └── 2026-09-27/            agenda-{en,zh}.html · notes-{en,zh}.md · deferred-{en,zh}.md
│   └── professor/                 (not created yet) weekly check-ins with the faculty advisor
├── todo/                          team to-do: open decisions, pending actions, decision log
│   ├── TODO.md                    English
│   └── TODO-zh.md                 Traditional Chinese
├── reference/                     inputs we did NOT write; read-only
│   ├── client/                    Virtual Gold Inc - AI Assistant.pdf          original capstone brief
│   ├── course/                    Proposed Weekly Structure.pdf                15-week course structure we must follow
│   └── team/                      Virtual_Gold_Data_Architecture_Proposal_1.docx   teammate proposal (merged into v0.2)
├── .github/                       CODEOWNERS, pull_request_template.md
├── src/                           (not created yet) prototype code
└── data/                          (not created yet) synthetic datasets and benchmark subsets; never real data
```

Rule of thumb: `docs/` is what we author and hand over (architecture, SOW, research), `meetings/` is everything about one meeting in one place, `reference/` is what we were handed (client, course, or a teammate), `todo/` is what we still have to decide, `src/` and `data/` are the prototype.

### Naming conventions

- Every bilingual file carries a language suffix: `-en` or `-zh`. The exception is `todo/TODO.md`, which is English (`TODO-zh.md` is the Chinese copy).
- Meeting folders are `YYYY-MM-DD`. Inside: `agenda-<lang>.html` for the running order, `briefing-<topic>-<lang>.html` for a presentation piece one workstream brings, `slides-<topic>-<lang>.pdf` for a full slide deck, `notes-<source>-<lang>` for what comes out (`gemini` = the auto-generated notes, `zh` = our translation), `email-<who>-<topic>-<lang>.md` for correspondence that belongs to that meeting.
- Versions live in the filename: `architecture-v0.3-*`, `Scope of Work v2`. A new version is a new file; old versions stay for history.

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

Tracked in [`todo/TODO.md`](todo/TODO.md) (English) and [`todo/TODO-zh.md`](todo/TODO-zh.md) (Traditional Chinese): decisions, pending actions, corrections to the teammate proposal, items waiting on the client, the SOW cost line, the per-workstream research list, and a decision log. Since 2026-10-03 the TODO is aligned with the midterm deck: items the deck made obsolete are listed under "Closed and superseded". Section 11 of the architecture doc is out of date and will be replaced in v0.4.

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
| `feat/` | new code in `src/` | `feat/router-threshold` |
| `fix/` | bug fixes | `fix/logprob-parsing` |
| `eval/` | datasets, benchmark runs, results | `eval/gsm8k-subset` |
| `todo/` | decisions and the decision log | `todo/week3-decisions` |

### Step by step

**1. Start from the latest `main`.** Do this every time before you begin, otherwise your PR will conflict.

```bash
git checkout main
git pull origin main
```

**2. Create a branch.**

```bash
git checkout -b feat/router-threshold
```

**3. Make your changes and commit.** Commit message: one line, starts with a verb, says what changed.

```bash
git add src/router.py
git commit -m "Add confidence threshold to rule-based router"
```

**4. Push the branch to GitHub.**

```bash
git push -u origin feat/router-threshold
```

**5. Open the pull request.** GitHub shows a **Compare & pull request** button after the push. Click it, fill in the template (What, Why, Type, Checklist), and click **Create pull request**. Mark is added as reviewer automatically.

**6. Wait for review.** Mark replies within two working days. If he asks for changes, commit again on the same branch and push; the PR updates by itself:

```bash
git add .
git commit -m "Read threshold from config instead of hardcoding"
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
git commit -m "Merge main into feat/router-threshold"
git push
```

### Where files go

- Anything we author goes in `docs/` (architecture, SOW, research one-pagers); anything a teammate or the client sends us goes in `reference/`; anything about a meeting, ours or theirs, goes in that meeting's folder under `meetings/`.
- Decisions go in `todo/`: tick the item and add a row to the decision log. If a decision changes the architecture, update `docs/` in the same PR.
- `docs/`, `meetings/` agendas and `todo/` exist in English and Traditional Chinese; keep both in sync, or say in the PR which one is ahead. The README is English only.
- Datasets and code go in `data/` and `src/` once the MVP starts in week 4.

## Notes on data

The client provides **public data only**, no PII. All evaluation uses public datasets plus LLM-generated synthetic enterprise data. Do not commit any real customer or third-party data to this repository.
