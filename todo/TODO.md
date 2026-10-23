# Team To-Do

Single place for open decisions and pending actions. Tick items here; when a decision changes the architecture, update `docs/` in the same PR.
Fill in **Owner** and **Due** at the team meeting. Chinese version: [`TODO-zh.md`](TODO-zh.md).

Meeting cadence (US Eastern, all weekly): client Monday 18:00–19:00 · professor Tuesday 17:00–18:20 · team Friday 15:30–16:30.

> **Baseline: the midterm deck as presented on 2026-10-05.**
> [`meetings/client/2026-10-05/Midterm Client Presentation Slides(Virtual Gold).pdf`](<../meetings/client/2026-10-05/Midterm Client Presentation Slides(Virtual Gold).pdf>) (49 slides) is the team consensus, agreed inside the team and with the professor. **Slide numbers in this file refer to it.** Until 2026-10-23 this file cited the 42-slide draft of Oct 3; those references were renumbered.
> Client notes for Sep 28 and Oct 5 are now on file (`meetings/client/2026-09-28/`, `2026-10-05/`, Gemini). There are no notes for the Sep 29 professor meeting or the Oct 2 team meeting. Where an earlier entry here, the Sep 27 team notes or a research document disagrees with the deck, the deck wins.
> The decision log rows dated 2026-10-03 were written from the Oct 3 draft. The final deck adds **routing rules** and **"English text and documents"** as inputs; A14 and A15 track where that leaves the API contract.

## For the team meeting, Friday 2026-10-23

Bring these to today's meeting. Phase 1 starts Monday Oct 26, the same day as the next client meeting.

| Topic | Items | What to settle today |
|---|---|---|
| Scope against the final deck | A14 routing, A15 documents as input | Whether to build routing and document input, or tell the client the scope narrowed. Owner and date for the contract change (before the Nov 15 freeze) |
| Evaluation | A16 ground truth, B59, B60, B46 | How the external labelled dataset and the 100 emails split the work; when the 100 emails go into `data/` |
| Model and scores | A13, B58, A11, A12 | Who runs Gemma 4 and by when; confirm the confidence-score split and who owns `score_method` |
| M2 (due Nov 1) | B41 | Who writes the detection and assessment prompts and parsers (still stubs); first end-to-end run on Ollama |
| Mark's client actions | B56, B57, B62, B63 | Status of each; what goes out before Monday |
| Repo and process | B64, B65, B35 | Zhexuan's `docs/api/` updates; the review-before-merge rule; closing PRs #3–#5 |
| For Monday's client meeting | D49, D50, D52, E68 | Ask again for the tier table review, source labels and VG08 access; the SOW is not signed yet |

## A. Open decisions

| # | Item | Notes | Owner | Due | Done |
|---|---|---|---|---|---|
| 14 | **Request-level routing: in or out?** | The final deck lists "Tier + routing rules" as a deliverable (slide 5), the service "redacts and applies routing" and VG08 "checks release eligibility" (slide 33), Phase 2 "checks routing before cloud use" (slide 45), and the dashboard counts routing statuses (slide 37). The SOW given to the client (`Scope of Work -  20261005.docx`) adds "a separate request-routing policy that determines whether the complete request remains local". But the 2026-10-03 decision log says no whole-request block (`LOCAL_ONLY`), API contract 0.4.2 removed the request-level decision, and `service/` has none. Decide what routing means (the service returns a status, or VG08 decides from the spans) and add it to the contract, or tell the client the scope narrowed. Must be settled before the Nov 15 contract freeze | Mark, Zhexuan | next client meeting | [ ] |
| 15 | **Input scope: email only, or English text and documents?** | Sep 28 aligned on "English-only input language and documents" for this phase; the final deck (slides 4, 5, 45) and the SOW say "English-language text and documents", with email as the first benchmark format. Contract 0.4.2 accepts an email structure only and lists attachments and OCR as out of scope. Decide what a "document" request looks like in the API (plain text with source tags?) or limit the claim to email | Zhexuan, Mark | before M4 | [ ] |
| 16 | **Ground truth for evaluation** | Oct 5 aligned on sourcing an already-labelled dataset (internet or Kaggle) as ground truth, after Aarvin asked how the team can trust LLM-generated test cases. Decide how it sits next to the 100-email benchmark: external set for calibration and recall, the 100 emails for the executive-email cases (context, attacks, business secrets)? Calibration (A11) depends on it | Karina | Phase 1 | [ ] |
| 13 | **Which open-source model** | Oct 5: the preliminary benchmark ran Llama 3.1 8B and Qwen 2.5 7B through Groq and OpenRouter; both beat the rules-plus-Presidio baseline and came close to the cloud model. Aarvin advised trying Gemma and sticking to **one** model for now (decision log 2026-10-05). `service/config/service.yaml` currently says `llama3:8b`. Pick the one model after the Gemma run (B58) | Anmol, Mark | after B58 | [ ] |
| 11 | **Who owns the confidence score, and the `score_method` field** | Carried from the Sep 27 deferred item B. The deck fixes the method (raw model score, calibrated by binning on labelled emails, slide 17) but not who builds which step. Proposed split, still unconfirmed: Anmol produces the raw score, Yudi supplies the calibration procedure (now in `service/vg_redactor/privacy/calibration.py`, identity until fitted), Karina picks thresholds (an evaluation output), the API field carries the **calibrated** score. Add a `score_method` field per span, or nobody reading a 0.55 knows what it is | Anmol | W9 | [ ] |
| 12 | **Fallback if the model's scores do not discriminate** | The 2026-09-14 screen found that 8B models' self-stated confidence saturates (91.7% of answers at ≥95%). Aarvin raised the same doubt on Oct 5. If the slide 17 calibration bins come out flat, there is nothing to calibrate. Yudi's proposal has the fallback: agreement-based scoring (share of detectors that flag a span, share of 3–5 repeated runs). Decide when the first baseline numbers are in | Anmol, Yudi | Phase 1 | [ ] |

## B. Pending actions

### From the client meetings (Sep 28, Oct 5)

| # | Action | Owner | Due | Done |
|---|---|---|---|---|
| 56 | **Send the preliminary benchmark results and the midterm slides to the client** (Oct 5 next step; materials on the project Drive) | Mark | | [ ] |
| 57 | **One-page benchmark report** for Aarvin and Alex: every model tested, including Gemma and any newly released model (Oct 5) | Mark | | [ ] |
| 58 | **Run Gemma 4 in the existing benchmark framework** (Oct 5). Feeds A13 | Mark | | [ ] |
| 59 | **Find an already-labelled PII dataset** (internet or Kaggle) to serve as the ground-truth baseline (Oct 5). Feeds A16 | Karina | | [ ] |
| 60 | **Show how the generated 100-email set can be trusted** (Oct 5; Aarvin's question). Feeds A16 | Karina | | [ ] |
| 61 | **Test complex obfuscation**: confidential ideas with no single name (the 56 business-secret items), with system prompts written for them (Oct 5, Alex's question) | Anmol, Karina | Phase 1 | [ ] |
| 62 | **Send API contract 0.4.2 to Alex and Aarvin** for review. Sep 28 next step was to send the drafted contract; 0.4.2 now exists in `docs/api/`. Send it together with the answer to A14 | Mark | after A14 | [ ] |
| 63 | **Send the information-category tables to the client** for checking against their scenarios (Sep 28). Same table as D49 | Mark | | [ ] |

### Build (milestones from deck slide 44)

| # | Action | Owner | Due | Done |
|---|---|---|---|---|
| 40 | M1: API contract 0.4.2 and service skeleton. **Done 2026-10-19** (PR #7, eight days late): contract and interfaces in `docs/api/`, service in `service/`, 43 tests | Zhexuan | 2026-10-11 | [x] |
| 41 | **M2: end-to-end pipeline with failure path.** Privacy Research components merged 2026-10-23 (PR #8, 76 tests). Still stubs: segmentation, the detection and assessment prompts and their parsers (Model Work), restore. The Ollama backend has not run end to end | Zhexuan, Anmol | 2026-11-01 | [ ] |
| 42 | M3: dashboard and load-test results. The Prometheus + Grafana stack and the 8-panel dashboard are in `service/dashboards/` (PR #7); load-test results are still to come | Zhexuan | 2026-11-08 | [ ] |
| 43 | M4: VG08 integration (Phase 2, Nov 2–15); contract freeze. Needs A14, A15 and D52 | Zhexuan, Mark | 2026-11-15 | [ ] |
| 44 | M5: code freeze (soft freeze Nov 18) | all | 2026-11-22 | [ ] |
| 45 | M6: final presentation | Mark | 2026-11-30 | [ ] |
| 46 | **Put the evaluation dataset in the repo** (`data/`): 100 fictional emails, 999 labelled items, 18 types, JSONL as on slide 41. Not committed yet. It is fictional, so the "no real data" rule allows it | Karina | | [ ] |
| 47 | **Baseline, then ablation** (slide 19): Rescriber-style baseline → + detector union → + name propagation → + repeated runs → + tier thresholds. Tune on one subset, report on a held-out subset. Leak rate per tier is the primary metric; over-redaction, calibration and seconds per email are also tracked. Phase 1 runs Oct 26–Nov 8 (slide 45) | Karina | 2026-11-08 | [ ] |
| 48 | **Architecture document v0.4.** `docs/architecture/` still holds v0.3, the pre-pivot hybrid design. Until v0.4 exists, the deck (slides 13, 14, 22–33) and `docs/api/` are the architecture of record | Mark | | [ ] |
| 64 | **Bring `docs/api/` up to date** (Zhexuan's files). (1) `service-interfaces-v0.4.2-zh.md` is still the pre-implementation plan: it cites 0.4.1, `development-schedule.md`, `protocols.py`, `pseudonym.py` and `structlog`, none of which exist, while the English file calls it "the original". (2) Neither file mentions `service/vg_redactor/privacy/` (PR #8); the English one still says "Owners are not confirmed yet". (3) `redaction-api-report-en-v0.4.2.md` puts the language before the version, unlike the other files. (4) The contract has no Chinese version | Zhexuan | | [ ] |
| 65 | **Review before merge.** PR #7 was merged by its author without a review, against the README rule "Nobody merges their own PR". Turn on branch protection (one approving review) or restate the rule to the team | Mark | next team meeting | [ ] |
| 35 | **Close Karina's PRs #3, #4, #5.** Built for the vertical trading scenario; the 100-email dataset replaces them | Karina | | [ ] |

## D. Waiting on the client

| # | Item | Asked on | Answer |
|---|---|---|---|
| 49 | **Review the tier table and the confidential term list.** `business_confidential` cannot be detected without a client-supplied list of project code names, deal names and counterparties. `service/config/context_store.yaml` is empty until then. This and D50–D52 were on the Oct 3 draft's closing slide; the final deck does not carry the four requests and the Oct 5 notes record no answer, so ask again | 2026-10-05 | |
| 50 | **Can the API request label each text's source?** (body, quoted thread, the executive's own words). May or may not be affected by the NDA | 2026-09-28 | |
| 51 | **GPU and sandbox access for the local model.** Open since 2026-09-15. Partial answer on Sep 28: test before any sandbox over the web with cloud-hosted open-source models, or locally with Ollama (e.g. Gemma); resource requests go through Aarvin and Alex, then Inderpal approves (decision log 2026-09-28). Mark told Aarvin on 2026-09-27 that the team has personal laptops only. The CMU Public Cloud Services route stays an internal fallback; do not raise it | 2026-09-15 | Partial, 2026-09-28 |
| 52 | **Make VG08 available for integration.** Phase 2 starts Nov 2 | 2026-10-05 | |
| 66 | **Alex shares the preliminary version of the service** for comparative testing (Oct 5 next step) | 2026-10-05 | |
| 67 | **Alex and Aarvin confirm the testing plan** (the two phases) to the team (Sep 28 next step) | 2026-09-28 | |
| 53 | NDA addendum with CMU: status (Sep 28 agenda, E2) | 2026-09-28 | |
| 55 | Does the client need restore, or does their system handle it? Latency target per email and daily volume (API contract open questions 1 and 2) | 2026-09-27 | |

## E. Scope of Work

| # | Item | Done |
|---|---|---|
| 26 | Section 6 cost ownership. **Settled 2026-10-03 without a figure:** where the project needs paid resources (GPU or other hardware, sandbox compute, model API usage), the Client sponsors or covers them, and the team agrees any such usage with the Client in advance. No `$[X]` cap. The SOW does not mention the CMU fallback | [x] |
| 68 | **Signature status of the SOW given at the midterm** (`docs/sow/Scope of Work -  20261005.docx`). **Not signed as of 2026-10-23** (Mark). The Sep 28 agenda asked the client to sign at the midterm; the Oct 5 notes do not mention it. Its scope also differs from contract 0.4.2 (A14, A15) | [ ] |

## Closed and superseded

Closed on 2026-10-03 against the midterm deck, and on 2026-10-23 against the final deck and the Sep 28 and Oct 5 notes. Original wording is in git history.

| # | Was | Status |
|---|---|---|
| A17 | Final delivery date | **Settled 2026-10-23:** final presentation Nov 30, as in the deck. "November 13" in the Oct 5 Gemini notes is a transcription error |
| B36 | Revise the Scope of Work before the midterm | Done: `Scope of Work -  20261005.docx` was given to the client at the midterm. Signature tracked in E68 |
| B37 | Reset the "show what is running" expectation | Closed: the midterm presented preliminary benchmark results (Oct 5 notes) |
| B38 | Agree answers to three likely questions | Closed with the midterm. The saturation question came up (Aarvin) and stays open as A12 |
| B39 | Record the midterm | Done: Gemini notes in `meetings/client/2026-10-05/notes-gemini-en.pdf` |
| D54 | Shared Drive and chat tool | Answered Sep 28: Urte set up a Slack workspace (paid plan); Mark shared the Drive link for notes and documents |
| A1 | Tool selection: HF transformers, own router, Presidio, cloud SDK | **Superseded.** Runtime is Ollama (decision log 2026-10-03). Presidio stays as one of three detectors. There is no router and no cloud call: the service never calls the cloud |
| A2 | RAG as stretch | Closed. Not part of the redaction service |
| A3 | Confidential requests never leave local | **Superseded** by the 2026-10-03 rows: no whole-request block; regulated items are replaced with placeholders and the rest is sent (slide 16). The final deck's routing reopens part of this as A14 |
| A4 | De-identification round trip in the MVP | Carried into the deck: placeholders, mapping stays local, restore is a separate call (slide 31) |
| A5 | Models on a GPU sandbox, Llama 3.1 8B / Qwen3 8B | The sandbox ask is D51; the model choice is A13 |
| A6 | Cloud provider | Closed. The service does not call a cloud model |
| A7 | Midpoint content (MMLU/GSM8K three configurations, escalation chart, CLI demo) | Replaced by the deck |
| A8 | Use case | Done 2026-09-21: horizontal, chief-of-staff assistant over executive email |
| A9 | Work split | Done 2026-09-25; the deck uses the same five areas (slide 2) |
| A10 | Six sensitivity-gate points from PRs #3–#5 | Closed. Written for the vertical scenario; (f) is settled by leak rate per tier (slide 19) |
| B10, B15 | Walk the client through §10 defaults; confirm compute | Open part moved to D51 |
| B11 | Architecture v0.3.1 | Replaced by B48 (v0.4) |
| B12 | Sandbox setup | Waits on D51; re-scope once hardware is known |
| B13, B14 | Harness skeleton; MMLU and GSM8K test sets | Closed. Evaluation is the 100-email benchmark |
| B14a | Synthetic enterprise data | Replaced by the 100-email dataset (B46) |
| B33, B34 | Confidence and metrics handovers from Zhexuan | Folded into A11 |
| C16–C20 | Corrections to the teammate Data & Architecture proposal | Closed. The proposal described the pre-pivot design; it was removed from `reference/team/` on 2026-10-23 |
| D21–D23 | §10 defaults; example documents; Qwen3 confirmation | Closed. Pre-pivot questions |
| D24 | Hardware | Moved to D51 |
| D25 | API contract from Aarvin | The team wrote the contract (0.4.2, B40) |
| F28–F32 | Research list by pre-pivot workstream | Delivered items stay on record in `docs/research/`; the rest is closed |
| Sep 27 team items 1–4 | Five-tier id split, six labelling fields, mask-anyway when unsure, whole-email vs section | Settled differently by the deck (decision log 2026-10-03) |
| Sep 27 deferred A | Three names for state storage | Settled: a local mapping store per redaction; the context store holds only a term list and an allow-list; no cross-caller store |

## Decision log

Record decisions here so nobody reopens them. Slide numbers refer to the 49-slide final deck.

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
| 2026-09-28 | **English only.** Input language and documents are restricted to English for the current phase | Sep 28 client notes, Decisions/Aligned |
| 2026-09-28 | **Two test phases.** Phase 1 tests the redaction service on its own, locally, on text and documents; Phase 2 integrates the HTTP service with Aarvin's VG08 service and tests live workflows end to end | Sep 28 client notes, Decisions/Aligned (Alex and Aarvin) |
| 2026-09-28 | **Test early, before any sandbox**, using cloud-hosted open-source models over the web or local tools such as Ollama | Sep 28 client notes; Inderpal, Alex and Aarvin. The roles are direction, not strict boundaries (Aarvin) |
| 2026-09-28 | **Resource requests:** agree the need with Aarvin and Alex first, then notify the designated person to get Inderpal's approval | Sep 28 client notes (Inderpal) |
| 2026-10-03 | **Scope.** A local redaction and restore service: an HTTP service that replaces private data in executive email with reversible placeholders before a cloud assistant sees it, and restores them in the reply. Deliverables: the service, sensitivity tiers and decision rules, a 100-email evaluation benchmark, a monitoring dashboard. Constraints: project hardware, open-source model, no outbound network access, automatic on every request, finished by the final presentation on Nov 30. The service never calls a cloud model. Supersedes the hybrid routing design (2026-09-07, 2026-09-08), the three-configuration evaluation and FinQA (2026-09-21). The final deck widens the inputs to English text and documents and adds routing rules (A14, A15) | Midterm deck slides 3–5, 8; team consensus, agreed with the professor |
| 2026-10-03 | **"The model judges, code decides."** Six steps inside the service: segmentation (body, quote, signature, with source tags) → candidate detection (rules + Presidio + local model, union by character position) → context assessment (model gives private-or-public and a raw score, then calibration) → decision in code (tier × score vs threshold) → placeholders (mapping stays local) → restore as a separate, deliberate call. One local model, two independent prompts: detection and assessment | Slides 13, 22–31 |
| 2026-10-03 | **Three tiers, starting thresholds.** High (IDs, passwords and keys, bank and card numbers, health, business-confidential): redact at score ≥ 0.2. Medium (names of private individuals, personal phone, personal email, home address): redact at ≥ 0.5. Low (city, dates, organisation names, age, gender): keep alone, redact if combined. Tiers follow NIST SP 800-122. Thresholds are starting values to be tuned. The Sep 27 five-tier id split, the "can the model decide" column, the `health` → `medical` rename and the `quantity` category are not carried into this table. PR #8 added `DEMOGRAPHIC` (High), `NETWORK_ID` and `AMOUNT` (Medium) in `service/config/policy.yaml` 0.1.1, still provisional | Slide 14 |
| 2026-10-03 | **Decision outcomes.** Score at or above the tier threshold, or a span that cannot be classified: redact. Score below the threshold, or a Low-tier item on its own: keep. No human review queue (`PENDING_REVIEW`) and no whole-request block (`LOCAL_ONLY`): regulated items become placeholders and the rest of the email goes to the cloud. This replaces the Sep 27 "mask anyway, tag not sure" rule and settles the Sep 27 item 4 (whole email vs section). The final deck's routing rules reopen the whole-request part (A14) | Slides 16, 29 |
| 2026-10-03 | **Fail safe.** If the model call fails or its output cannot be parsed, keep the rule and Presidio candidates, redact every candidate without thresholds, and flag the response `degraded: true`. Always on, not an opt-in. Any placeholder in a reply that the service did not issue is flagged, not guessed. The audit log records category, score, action and the degraded flag, never raw text. Settles API contract open question 8 | Slides 22, 26, 30, 32 |
| 2026-10-03 | **Confidence score.** The model's raw score per span is calibrated on labelled emails: group spans by raw score, measure the share that is actually private, use that share as the calibrated score | Slide 17; Xiong et al. 2024 |
| 2026-10-03 | **Local model runs via Ollama, using Rescriber's open-source prompt.** Supersedes 2026-09-15 (transformers, no Ollama). That decision existed because the hybrid harness needed hidden states for Semantic Entropy Probes; the redaction service's score comes from the assessment prompt and calibration, so that requirement no longer applies | Slide 20 |
| 2026-10-03 | **Context store holds only a term list and an allow-list.** There is no persistent, cross-session or cross-caller store of known entities. The placeholder mapping is kept per redaction in the local mapping store. Settles the Sep 27 deferred item A | Slides 23–24, 26 |
| 2026-10-03 | **Evaluation.** 100 fictional executive emails, 15 business areas, 9 industries, 4 executive roles, 999 labelled items of 18 types. Built-in cases: context cases, 10 clean emails, forwarded threads, 5 attack emails, 56 business secrets with no single name (FACT label). Per email: domain, industry, exec role, task, tags. Per span: start, end, type, `must_mask` (true or false). Model output: one JSON line per email, start and end required, type and score optional. Primary metric: leak rate per tier. Also tracked: over-redaction, calibration, seconds per email. Ablation from a Rescriber-style baseline. Replaces the Sep 27 three-value right answer and six-field labelling | Slides 19, 39–41 |
| 2026-10-03 | **Our two contributions.** Running without a person reviewing each item (Rescriber asks the user to confirm every redaction). A labelled email benchmark and an ablation showing what each part adds | Slide 20 |
| 2026-10-03 | **Schedule.** Phase 1, the service tested on its own, from late October. Phase 2, VG08 integration, from Nov 2. Week of Oct 12 is fall break, no work. Milestones: Oct 11 contract 0.4.2 and service skeleton · Nov 1 end-to-end pipeline with failure path · Nov 8 dashboard and load-test results · Nov 15 VG08 integration and contract freeze · Nov 22 code freeze (soft freeze Nov 18) · Nov 30 final presentation. Dashboard on Prometheus and Grafana | Slides 35, 36, 44, 45 |
| 2026-10-05 | **Phase dates.** Phase 1 runs Oct 26–Nov 8: English text and documents, redaction and restore, benchmark performance, degraded fallback. Phase 2 runs Nov 2–15: VG08 sandbox, complete workflows, routing before cloud use, contract freeze | Final deck slide 45 |
| 2026-10-05 | **Ground truth from an already-labelled external dataset** (internet or Kaggle), alongside the generated benchmark. How the two fit is A16 | Oct 5 client notes, Decisions/Aligned. Aarvin asked how a generated dataset can be trusted; Mark proposed the Kaggle route and Aarvin supported it |
| 2026-10-05 | **One model for the current phase.** Model swappability comes later, through a helper or middleware, once the service improves | Oct 5 client notes, Decisions/Aligned (Aarvin) |
| 2026-10-23 | **As-given files keep their names.** `docs/sow/Scope of Work -  20261005.docx` and `meetings/client/2026-10-05/Midterm Client Presentation Slides(Virtual Gold).pdf` are what the client received; they are not renamed. The Oct 3 deck draft and the SOW v3 PDF were removed | Mark |
