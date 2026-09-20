# Virtual Gold Capstone — Hybrid Local/Cloud AI Assistant

CMU MISM Capstone, Fall 2026, for **Virtual Gold Inc** (AI consulting, Brooklyn NY).
Client contact: Urte Jesina. Team: 5 people.

We are designing and evaluating a **local-first enterprise AI assistant**: open-source models running locally are the primary intelligence layer, every response gets a measured confidence score, and requests escalate to a cloud model only when confidence is low **and** data sensitivity allows. Sensitive data stays local.

## Current status (Week 4, updated 2026-09-18)

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
| Team meeting Sep 19: settle the use-case answer, workstream owners, two research one-pagers; one email to the client before the Sep 22 client meeting | Agenda in `meetings/team/2026-09-19/` |
| Confidence-scoring harness design doc (PR #2, Zhexuan Ye) | Under review, changes requested 2026-09-14 |
| Week 4: sandbox setup, harness skeleton (sampling core, loaders, metrics), workstream research one-pagers | In progress |
| Week 7: midpoint presentation with first local-only / hybrid / cloud-only numbers on MMLU subset and GSM8K (scope in `todo/TODO.md` A7) | Target |

## Read this first

The single source of truth is the architecture document. Same content in four formats:

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
│   │   └── architecture-v0.3-zh.html    Traditional Chinese, HTML
│   ├── sow/                       Scope of Work drafts
│   │   ├── Scope of Work v1.docx        original draft (W3)
│   │   └── Scope of Work v2.docx        revised, changes in red; sign this one once the cost line is filled in
│   └── research/                  one-pagers and design docs per workstream (see its README)
├── meetings/                      one folder per meeting, named YYYY-MM-DD: the agenda we bring plus the notes that come out
│   ├── client/                    meetings with Virtual Gold
│   │   ├── 2026-09-03/            notes-gemini-en.docx
│   │   └── 2026-09-15/            agenda-en.html · agenda-zh.html · notes-gemini-en.pdf · notes-zh.md
│   ├── team/                      internal team meetings, not shared with the client
│   │   └── 2026-09-19/            agenda-en.html · agenda-zh.html
│   └── professor/                 weekly check-ins with the faculty advisor
├── todo/                          team to-do: open decisions, pending actions, decision log
│   ├── TODO.md                    English
│   └── TODO-zh.md                 Traditional Chinese
├── reference/                     inputs we did NOT write; read-only
│   ├── client/                    Virtual Gold Inc - AI Assistant.pdf          original capstone brief
│   ├── course/                    Proposed Weekly Structure.pdf                15-week course structure we must follow
│   └── team/                      Virtual_Gold_Data_Architecture_Proposal_1.docx   teammate proposal (merged into v0.2)
├── src/                           (from week 4) prototype code: router, confidence scoring, PII gate, eval harness
└── data/                          (from week 4) synthetic datasets and benchmark subsets; never real data
```

Rule of thumb: `docs/` is what we author and hand over (architecture, SOW, research), `meetings/` is everything about one meeting in one place, `reference/` is what we were handed (client, course, or a teammate), `todo/` is what we still have to decide, `src/` and `data/` are the prototype.

### Naming conventions

- Every bilingual file carries a language suffix: `-en` or `-zh`. The exception is `todo/TODO.md`, which is English (`TODO-zh.md` is the Chinese copy).
- Meeting folders are `YYYY-MM-DD`. Inside: `agenda-<lang>.html` for what we bring, `notes-<source>-<lang>` for what comes out (`gemini` = the auto-generated notes, `zh` = our translation).
- Versions live in the filename: `architecture-v0.3-*`, `Scope of Work v2`. A new version is a new file; old versions stay for history.

## Meeting cadence

| Meeting | When | Folder |
|---|---|---|
| Client meeting (Virtual Gold) | Monday 18:00–19:00 | `meetings/client/` |
| Internal meeting with the professor | Tuesday 17:00–18:20 | `meetings/professor/` |
| Internal team meeting | Friday 15:30–16:30 | `meetings/team/` |

Agendas go up before the meeting, notes go in after, both in the meeting's own dated folder.

## Timeline (follows the course structure, not negotiable)

| Weeks | Phase |
|---|---|
| W1–W3 | Setup: team, kickoff, architecture sign-off |
| W4–W7 | **MVP build (now).** **W7 midpoint presentation** |
| W8 | Fall break |
| W9–W11 | Full three-configuration evaluation, SEP and sampling-ensemble confidence signals, red-teaming, format-preserving fake values |
| W12–W15 | Analysis, report, client feedback. **W15 final presentation** (W14 Thanksgiving) |

## Open decisions

Tracked in [`todo/TODO.md`](todo/TODO.md) (English) and [`todo/TODO-zh.md`](todo/TODO-zh.md) (Traditional Chinese): decisions, pending actions, corrections to the teammate proposal, items waiting on the client, the SOW cost line, the per-workstream research list, and a decision log. Section 11 of the architecture doc mirrors the decision items but lags behind the TODO until v0.3 (TODO B11).

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
