# Team To-Do

Single place for open decisions and pending actions. Tick items here; when a decision changes the architecture, update `docs/` in the same PR.
Fill in **Owner** and **Due** at the team meeting. Chinese version: [`TODO-zh.md`](TODO-zh.md).

Meeting cadence (US Eastern, all weekly): client Monday 18:00–19:00 · professor Tuesday 17:00–18:20 · team Friday 15:30–16:30.

> **Baseline as of 2026-10-03: the midterm deck is the team consensus.**
> [`meetings/client/2026-10-05/slides-midterm-en.pdf`](../meetings/client/2026-10-05/slides-midterm-en.pdf) was agreed inside the team and with the professor.
> No other notes from the Sep 28 client meeting, the Sep 29 professor meeting or the Oct 2 team meeting exist. Where an earlier entry here, the Sep 27 team notes or a research document disagrees with the deck, the deck wins.
> The decisions it settles are in the decision log (rows dated 2026-10-03). Items it made obsolete are listed in [Closed and superseded](#closed-and-superseded) with the reason. Their full text is in git history.

## A. Open decisions

| # | Item | Notes | Owner | Due | Done |
|---|---|---|---|---|---|
| 11 | **Who owns the confidence score, and the `score_method` field** | Carried from the Sep 27 deferred item B. The deck fixes the method (raw model score, calibrated by binning on labelled emails, slide 14) but not who builds which step. Proposed split, still unconfirmed: Anmol produces the raw score, Yudi supplies the calibration procedure, Karina picks thresholds (an evaluation output), Zhexuan's API field carries the **calibrated** score. Add a `score_method` field per span, or nobody reading a 0.55 knows what it is | Anmol | W9 | [ ] |
| 12 | **Fallback if the model's scores do not discriminate** | The 2026-09-14 screen found that 8B models' self-stated confidence saturates (91.7% of answers at ≥95%). If the slide 14 calibration bins come out flat, the deck's method has nothing to calibrate. Yudi's proposal has the fallback: agreement-based scoring (share of detectors that flag a span, share of 3–5 repeated runs). Decide when the first baseline numbers are in | Anmol, Yudi | Phase 1 | [ ] |
| 13 | **Which open-source model(s)** | The deck says "local model via Ollama, using Rescriber's open-source prompt" (slide 17) and "open-source models, cloud-hosted or local" for testing (slide 40), but names no model. Llama 3.1 8B / Qwen3 8B came from the pre-pivot plan and are not confirmed for this service | Anmol | Oct 11 | [ ] |

## B. Pending actions

### Before the midterm (Monday 2026-10-05, 18:00)

| # | Action | Owner | Due | Done |
|---|---|---|---|---|
| 36 | **Revise the Scope of Work to the deck's scope and send it before the meeting.** The Sep 28 agenda (item E6) told the client we would revise it, send it in advance and ask them to sign at the midterm. `Scope of Work v2.docx` predates the Sep 21 pivot: it has no redaction service, 100-email benchmark or dashboard, and the cost line is still `$[X]` (E26). Write `Scope of Work v3.docx`. The deck does not mention the SOW, so raise it in the closing section | Mark | 2026-10-04 | [ ] |
| 37 | **Reset the "show what is running" expectation.** The Sep 28 agenda (item E3) promised to "show what is running by then, with measurements of what redaction costs in answer quality". The deck has no demo and no numbers. Say so up front: first measurements come with Phase 1 (from late October), dashboard and load-test results by Nov 8 | Mark | 2026-10-05 | [ ] |
| 38 | **Agree one answer for three likely questions.** (1) Slide 9 says items with insufficient confidence are redacted by default. Slides 12 and 26 keep a span scored below its tier's threshold. Explain the difference: a low score means "confidently public", and redact-by-default covers items that cannot be classified (slide 26, branch A). (2) Why Ollama, when the Sep 15 decision chose transformers (decision log 2026-10-03). (3) What happens if model scores saturate (A12) | Yudi, Zhexuan, Anmol | 2026-10-05 | [ ] |
| 39 | **Record the midterm** in `meetings/client/2026-10-05/notes-*`: client answers to the four slide-40 requests and to section D below, SOW status, milestone agreement | Mark | 2026-10-06 | [ ] |

### Build (milestones from deck slide 39)

| # | Action | Owner | Due | Done |
|---|---|---|---|---|
| 40 | **M1: API contract 0.4.2 and service skeleton.** The repo holds only `docs/research/zhexuan/2026-09-27/redaction-api-contract-en.md` (0.3.0-draft). That draft still has `LOCAL_ONLY`, `PENDING_REVIEW`, the polling endpoint, a global cross-caller context store and opt-in `allow_degraded`, none of which are in the deck's design. Commit 0.4.2 and mark 0.3.0 superseded | Zhexuan | 2026-10-11 | [ ] |
| 41 | M2: end-to-end pipeline with failure path | Zhexuan | 2026-11-01 | [ ] |
| 42 | M3: dashboard (Prometheus + Grafana) and load-test results | Zhexuan | 2026-11-08 | [ ] |
| 43 | M4: VG08 integration (Phase 2, from Nov 2); contract freeze. Needs D52 | Zhexuan, Mark | 2026-11-15 | [ ] |
| 44 | M5: code freeze (soft freeze Nov 18) | all | 2026-11-22 | [ ] |
| 45 | M6: final presentation | Mark | 2026-11-30 | [ ] |
| 46 | **Put the evaluation dataset in the repo** (`data/`): 100 fictional emails, 999 labelled items, 18 types, JSONL as on slide 36. Not committed yet. It is fictional, so the "no real data" rule allows it | Karina | 2026-10-11 | [ ] |
| 47 | **Baseline, then ablation** (slide 16): Rescriber-style baseline → + detector union → + name propagation → + repeated runs → + tier thresholds. Tune on one subset, report on a held-out subset. Leak rate per tier is the primary metric; over-redaction, calibration and seconds per email are also tracked | Karina | Phase 1 | [ ] |
| 48 | **Architecture document v0.4.** `docs/architecture/` still holds v0.3, the pre-pivot hybrid design. Until v0.4 exists, the deck (slides 10, 11, 19–29) is the architecture of record | Mark | W9 | [ ] |
| 35 | **Close Karina's PRs #3, #4, #5.** Built for the vertical trading scenario; the 100-email dataset replaces them | Karina | 2026-10-11 | [ ] |

## D. Waiting on the client

| # | Item | Asked on | Answer |
|---|---|---|---|
| 49 | **Review the tier table and the confidential term list** (slide 40, request 1). `business_confidential` cannot be detected without a client-supplied list of project code names, deal names and counterparties | 2026-10-05 | |
| 50 | **Can the API request label each text's source?** (body, quoted thread, the executive's own words; slide 40, request 2). May or may not be affected by the NDA | 2026-09-28 | |
| 51 | **GPU and sandbox access for the local model** (slide 40, request 3). Open since 2026-09-15. Mark told Aarvin on 2026-09-27 that the team has personal laptops only. The CMU Public Cloud Services route stays an internal fallback; do not raise it | 2026-09-15 | |
| 52 | **Make VG08 available for integration** (slide 40, request 4). Phase 2 starts Nov 2 | 2026-10-05 | |
| 53 | NDA addendum with CMU: status (Sep 28 agenda, E2) | 2026-09-28 | |
| 54 | Shared Google Drive and who has access; Slack or Google Chat (Sep 28 agenda, E4 and E5) | 2026-09-28 | |
| 55 | Does the client need restore, or does their system handle it? Latency target per email and daily volume (API contract open questions 1 and 2) | 2026-09-27 | |

## E. Scope of Work before signing

| # | Edit | Done |
|---|---|---|
| 26 | Section 6 cost ownership. **Settled 2026-10-03 without a figure:** v3 says that where the project needs paid resources (GPU or other hardware, sandbox compute, model API usage), the Client sponsors or covers them, and the team agrees any such usage with the Client in advance. No `$[X]` cap. The SOW does not mention the CMU fallback | [x] |

## Closed and superseded

Closed on 2026-10-03 against the midterm deck. Original wording is in git history (`todo/TODO.md` before this date).

| # | Was | Status |
|---|---|---|
| A1 | Tool selection: HF transformers, own router, Presidio, cloud SDK | **Superseded.** Runtime is Ollama (decision log 2026-10-03). Presidio stays as one of three detectors. There is no router and no cloud call: the service never calls the cloud |
| A2 | RAG as stretch | Closed. Not part of the redaction service |
| A3 | Confidential requests never leave local | **Superseded.** No whole-request block; regulated items are replaced with placeholders and the rest is sent (slide 13) |
| A4 | De-identification round trip in the MVP | Carried into the deck: placeholders, mapping stays local, restore is a separate call (slide 28) |
| A5 | Models on a GPU sandbox, Llama 3.1 8B / Qwen3 8B | The sandbox ask is D51; the model choice is open again (A13) |
| A6 | Cloud provider | Closed. The service does not call a cloud model |
| A7 | Midpoint content (MMLU/GSM8K three configurations, escalation chart, CLI demo) | Replaced by the deck |
| A8 | Use case | Done 2026-09-21: horizontal, chief-of-staff assistant over executive email |
| A9 | Work split | Done 2026-09-25; the deck uses the same five areas (slide 2) |
| A10 | Six sensitivity-gate points from PRs #3–#5 | Closed. Written for the vertical scenario; (f) is settled by leak rate per tier (slide 16) |
| B10, B15 | Walk the client through §10 defaults; confirm compute | Open part moved to D51 |
| B11 | Architecture v0.3.1 | Replaced by B48 (v0.4) |
| B12 | Sandbox setup | Waits on D51; re-scope once hardware is known |
| B13, B14 | Harness skeleton; MMLU and GSM8K test sets | Closed. Evaluation is the 100-email benchmark |
| B14a | Synthetic enterprise data | Replaced by the 100-email dataset (B46) |
| B33, B34 | Confidence and metrics handovers from Zhexuan | Folded into A11 |
| C16–C20 | Corrections to the teammate Data & Architecture proposal | Closed. The proposal describes the pre-pivot design and is no longer maintained |
| D21–D23 | §10 defaults; example documents; Qwen3 confirmation | Closed. Pre-pivot questions |
| D24 | Hardware | Moved to D51 |
| D25 | API contract from Aarvin | The team now writes the contract (0.4.2, B40) |
| F28–F32 | Research list by pre-pivot workstream | Delivered items stay on record in `docs/research/`; the rest is closed |
| Sep 27 team items 1–4 | Five-tier id split, six labelling fields, mask-anyway when unsure, whole-email vs section | Settled differently by the deck (decision log 2026-10-03) |
| Sep 27 deferred A | Three names for state storage | Settled: a local mapping store per redaction; the context store holds only a term list and an allow-list; no cross-caller store |

## Decision log

Record decisions here so nobody reopens them.

| Date | Decision | Rationale |
|---|---|---|
| 2026-09-03 | Client kickoff decisions: hybrid architecture with a mandatory local model; evaluate with general-purpose benchmarks and show performance comparable to cloud; local model enhancement in scope; no GUI; client provides a cloud sandbox; weekly meetings during discovery | Sep 3 client meeting notes (`meetings/client/2026-09-03/`) |
| 2026-09-07 | Local-first hybrid architecture with confidence-based escalation and sensitivity gating (architecture v0.1) | Matches the client brief |
| 2026-09-08 | Adopt teammate proposal's three-configuration evaluation, named datasets, defaults-instead-of-questions style, MVP vs stretch split (architecture v0.2) | More concrete and matches client's preference for defaults |
| 2026-09-08 | Timeline follows the course's 15-week structure without change | Midpoint W7 and breaks are fixed by the course |
| 2026-09-10 | No local LLM on laptops. Models run on a cloud GPU sandbox that simulates an on-premises environment; laptops are for development only | Laptops cannot run 8B models at benchmark speed; the client offered a sandbox on Sep 3; a VM we control still satisfies the "local" requirement |
| 2026-09-14 | Confidence-scoring MVP excludes verbalized confidence; prioritizes token-probability confidence and Semantic Entropy Probes over self-consistency/full semantic entropy | 2026 screen of seven 3B–9B open-weight models found verbalized confidence saturates (91.7% of responses self-report ≥95% confidence regardless of correctness); see `docs/research/zhexuan/2026-09-15/confidence-harness-design-en.md` and `docs/research/zhexuan/2026-09-13/confidence-scoring-harness-report-en.md` |
| 2026-09-15 | Local inference and the evaluation harness run on HF transformers (bitsandbytes 4-bit); Ollama is not used | The harness needs per-token logprobs and hidden states for the Semantic Entropy Probe (PR #2); one stack for harness and router avoids threshold drift between quantization formats |
| 2026-09-15 | RAG knowledge layer is a stretch goal, not in the MVP | Not in the client's requirements or evaluation criteria; no client data yet (A8); retrieval grounding already out of the confidence harness (PR #2). Reconsider after the W7 midpoint |
| 2026-09-15 | Data sensitivity classification is in the MVP: confidential requests never leave local, regardless of confidence | Policy half of the SOW's routing requirement; the client's core motivation is protecting proprietary data; one rule in the router |
| 2026-09-15 | De-identification and re-identification both in the MVP; re-identification is a per-request placeholder mapping table; numeric data uses placeholders, fake values are stretch | Redaction is required by the client's privacy parameters; without re-identification the cloud answer is unusable; the mapping table is a one-day task |
| 2026-09-21 | FinQA (MIT) is the finance QA benchmark for the accuracy_benchmark batch; FinanceBench (CC BY-NC) stays in reserve for coursework only | Karina's research (`docs/research/karina/2026-09-20/financial-data-sources-en.md`): zero licensing risk for the client, and FinQA's ground truth includes the reasoning program, so both the final number and the reasoning can be scored |
| 2026-09-21 | Horizontal scenario first: build the sanitization service as a standalone HTTP service for a chief-of-staff assistant; the vertical trading assistant is deferred to time-permitting status | Inderpal and Alex argued that pursuing both at once risked finishing neither, and that the horizontal applies more broadly. Mark accepted the recommendation. Sep 21 client meeting notes, Decisions/Aligned |
| 2026-09-25 | Workstreams reassigned one-to-one onto Aarvin's five areas of responsibility: Evaluation & Test Data Karina · Privacy Research Yudi · Model Work Anmol · Service Engineering Zhexuan · Integration & Coordination Mark. Mark is the single point of contact | Aarvin's onboarding email defines the five areas and asks for one named contact, and says the full specification follows once role assignments are confirmed. A one-to-one mapping is the form he can act on. Team meeting 2026-09-25 |
| 2026-09-27 | Answer Aarvin's hardware question with personal laptops only; do not raise CMU Public Cloud Services | Consistent with the standing B15 decision that the CMU route is an internal fallback not to be raised with the client. Keeps the sandbox question (B15, open since 2026-09-15) on Virtual Gold's side |
| 2026-10-03 | **Scope.** A local redaction and restore service: an HTTP service that replaces private data in executive email with reversible placeholders before a cloud assistant sees it, and restores them in the reply. Deliverables: the service, sensitivity tiers and decision rules, a 100-email evaluation benchmark, a monitoring dashboard. Constraints: project hardware, open-source model, no outbound network access, automatic on every request, finished by the final presentation on Nov 30. The service never calls a cloud model. Supersedes the hybrid routing design (2026-09-07, 2026-09-08), the three-configuration evaluation and FinQA (2026-09-21) | Midterm deck slides 3–4, 7; team consensus, agreed with the professor |
| 2026-10-03 | **"The model judges, code decides."** Six steps inside the service: segmentation (body, quote, signature, with source tags) → candidate detection (rules + Presidio + local model, union by character position) → context assessment (model gives private-or-public and a raw score, then calibration) → decision in code (tier × score vs threshold) → placeholders (mapping stays local) → restore as a separate, deliberate call. One local model, two independent prompts: detection and assessment | Slides 10, 19–28 |
| 2026-10-03 | **Three tiers, starting thresholds.** High (IDs, passwords and keys, bank and card numbers, health, business-confidential): redact at score ≥ 0.2. Medium (names of private individuals, personal phone, personal email, home address): redact at ≥ 0.5. Low (city, dates, organisation names, age, gender): keep alone, redact if combined. Tiers follow NIST SP 800-122. Thresholds are starting values to be tuned. The Sep 27 five-tier id split, the "can the model decide" column, the `health` → `medical` rename and the `quantity` category are not carried into this table | Slide 11 |
| 2026-10-03 | **Decision outcomes.** Score at or above the tier threshold, or a span that cannot be classified: redact. Score below the threshold, or a Low-tier item on its own: keep. No human review queue (`PENDING_REVIEW`) and no whole-request block (`LOCAL_ONLY`): regulated items become placeholders and the rest of the email goes to the cloud. This replaces the Sep 27 "mask anyway, tag not sure" rule and settles the Sep 27 item 4 (whole email vs section) | Slides 13, 26 |
| 2026-10-03 | **Fail safe.** If the model call fails or its output cannot be parsed, keep the rule and Presidio candidates, redact every candidate without thresholds, and flag the response `degraded: true`. Always on, not an opt-in. Any placeholder in a reply that the service did not issue is flagged, not guessed. The audit log records category, score, action and the degraded flag, never raw text. Settles API contract open question 8 | Slides 19, 23, 27, 29 |
| 2026-10-03 | **Confidence score.** The model's raw score per span is calibrated on labelled emails: group spans by raw score, measure the share that is actually private, use that share as the calibrated score | Slide 14; Xiong et al. 2024 |
| 2026-10-03 | **Local model runs via Ollama, using Rescriber's open-source prompt.** Supersedes 2026-09-15 (transformers, no Ollama). That decision existed because the hybrid harness needed hidden states for Semantic Entropy Probes; the redaction service's score comes from the assessment prompt and calibration, so that requirement no longer applies | Slide 17 |
| 2026-10-03 | **Context store holds only a term list and an allow-list.** There is no persistent, cross-session or cross-caller store of known entities. The placeholder mapping is kept per redaction in the local mapping store. Settles the Sep 27 deferred item A | Slides 20–21, 23 |
| 2026-10-03 | **Evaluation.** 100 fictional executive emails, 15 business areas, 9 industries, 4 executive roles, 999 labelled items of 18 types. Built-in cases: Aarvin's context cases, 10 clean emails, forwarded threads, 5 attack emails, 56 business secrets with no single name (FACT label). Per email: domain, industry, exec role, task, tags. Per span: start, end, type, `must_mask` (true or false). Model output: one JSON line per email, start and end required, type and score optional. Primary metric: leak rate per tier. Also tracked: over-redaction, calibration, seconds per email. Ablation from a Rescriber-style baseline. Replaces the Sep 27 three-value right answer and six-field labelling | Slides 16, 34–36 |
| 2026-10-03 | **Our two contributions.** Running without a person reviewing each item (Rescriber asks the user to confirm every redaction). A labelled email benchmark and an ablation showing what each part adds | Slide 17 |
| 2026-10-03 | **Schedule.** Phase 1, the service tested on its own, from late October. Phase 2, VG08 integration, from Nov 2. Week of Oct 12 is fall break, no work. Milestones: Oct 11 contract 0.4.2 and service skeleton · Nov 1 end-to-end pipeline with failure path · Nov 8 dashboard and load-test results · Nov 15 VG08 integration and contract freeze · Nov 22 code freeze (soft freeze Nov 18) · Nov 30 final presentation. Dashboard on Prometheus and Grafana | Slides 31, 32, 39, 40 |
