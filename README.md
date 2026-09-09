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
| PR workflow set up (branch → PR → Mark reviews and merges) | Done, 2026-09-08 |
| Week 4: start MVP build, evaluation harness skeleton | Not started |
| Week 7: midpoint presentation with first local-only vs hybrid numbers | Target |

## Read this first

The single source of truth is the architecture document. Same content in four formats:

| File | Language | Format |
|---|---|---|
| [`docs/architecture-v0.2-en.md`](docs/architecture-v0.2-en.md) | English | Markdown, Mermaid diagrams (renders on GitHub) |
| [`docs/architecture-v0.2-en.html`](docs/architecture-v0.2-en.html) | English | HTML with SVG diagrams, open in a browser |
| [`docs/architecture-v0.2-zh.md`](docs/architecture-v0.2-zh.md) | Traditional Chinese | Markdown, Mermaid diagrams |
| [`docs/architecture-v0.2.html`](docs/architecture-v0.2.html) | Traditional Chinese | HTML with SVG |

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
├── docs/                          documents WE write (the deliverables in progress)
│   ├── architecture-v0.2-en.md    current architecture doc, English (Markdown, renders on GitHub)
│   ├── architecture-v0.2-en.html  same, HTML with SVG diagrams
│   ├── architecture-v0.2-zh.md    current architecture doc, Chinese
│   └── architecture-v0.2.html     same, HTML
├── todo/                          team to-do: open decisions, pending actions, decision log
│   ├── TODO.md                    English
│   └── TODO-zh.md                 Traditional Chinese
├── reference/                     inputs we did NOT write; read-only
│   ├── client/                    from Virtual Gold and the course
│   │   ├── Virtual Gold Inc - AI Assistant.pdf    original capstone brief
│   │   └── Proposed Weekly Structure.pdf          15-week course structure
│   └── team/                      individual teammates' proposals and notes
│       └── Virtual_Gold_Data_Architecture_Proposal_1.docx   Data & Architecture proposal (merged into v0.2)
├── src/                           (from week 4) prototype code: router, confidence scoring, PII gate, eval harness
└── data/                          (from week 4) synthetic datasets and benchmark subsets; never real data
```

Rule of thumb: `docs/` is what we hand to the client, `reference/` is what we were handed, `todo/` is what we still have to decide, `src/` and `data/` are the prototype.

## Timeline (follows the course structure, not negotiable)

| Weeks | Phase |
|---|---|
| W1–W3 | Setup: team, kickoff, **architecture sign-off (now)** |
| W4–W7 | MVP build. **W7 midpoint presentation** |
| W8 | Fall break |
| W9–W11 | Full three-configuration evaluation, red-teaming, de-identification round trip |
| W12–W15 | Analysis, report, client feedback. **W15 final presentation** (W14 Thanksgiving) |

## Open decisions

Tracked in [`todo/TODO.md`](todo/TODO.md) (English) and [`todo/TODO-zh.md`](todo/TODO-zh.md) (Traditional Chinese): this week's decisions, pending actions, corrections to the teammate proposal, items waiting on the client, and a decision log. Section 11 of the architecture doc mirrors the decision items.

## Contributing workflow

Three rules:

1. **Never push to `main` directly.** Not even for a one-line fix.
2. **One branch, one topic.** Small PRs get reviewed fast; big ones sit.
3. **Every change goes through a pull request.** Mark reviews and merges. Nobody merges their own PR.

There is no technical lock on `main` right now, so this works only if all of us follow it. If we later turn on branch protection, the steps below stay exactly the same.

### Branch names

| Prefix | Use for | Example |
|---|---|---|
| `docs/` | architecture document, README | `docs/v0.3-rag-decision` |
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

- Anything we author goes in `docs/`; anything a teammate or the client sends us goes in `reference/`.
- Decisions go in `todo/`: tick the item and add a row to the decision log. If a decision changes the architecture, update `docs/` in the same PR.
- `docs/` and `todo/` exist in English and Traditional Chinese; keep both in sync, or say in the PR which one is ahead. The README is English only.
- Datasets and code go in `data/` and `src/` once the MVP starts in week 4.

## Notes on data

The client provides **public data only**, no PII. All evaluation uses public datasets plus LLM-generated synthetic enterprise data. Do not commit any real customer or third-party data to this repository.
