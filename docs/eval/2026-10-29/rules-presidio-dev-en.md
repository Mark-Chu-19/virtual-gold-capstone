# Rules and Presidio: tuning on baseline v1.1 (development split)

Yudi · 29 Oct 2026 · branch `feat/privacy-detection-fixes` · tier table tier-v3 (0.1.3 + `ID_NUMBER: high`)

## Summary

Starting from main's rules + Presidio, 13 strategies were added one at a time and measured on the 60 development emails of Karina's baseline v1.1. Together they raise recall from 79.8% to 89.1% and High-tier recall from 22% to 78%. They also cut extra masks from 169 to 82. The 40 test emails were not used.

main keeps the simplest version as the baseline. The tuned version lives on `feat/privacy-detection-fixes`.

Tier table tier-v3 (formerly 0.1.3) adds `ID_NUMBER: high` (case, medical record, member and invoice numbers), provisional until the client answers Q1. It changes no score here: unknown types were already treated as High, and the labels already mark these spans High.

## Setup

| Item | Value |
|---|---|
| Data | `data/baseline/baseline_v1.1_dev.jsonl`: 60 emails; 578 must-redact spans excluding FACT (63 High, 462 Medium, 53 Low) |
| Detectors | Rules + Presidio 2.2.364; union merged by character position, using the service's own `merge` |
| Scoring | Karina's `score.py`; a span counts as found when 95% of its characters are covered |
| Recall | Share of must-redact spans fully covered, excluding FACT |
| Leak rate | Share of emails with at least one missed span |
| Extra masks | Predictions that overlap no labelled span |
| Retain masked | Spans labelled *retain* that get a non-Public mask |

## Results: each strategy added in order (cumulative)

| # | Strategy | Where | Effect of this step | Recall | High recall | Leak rate | Extra masks | Retain masked |
|---|---|---|---|---|---|---|---|---|
| 0 | main baseline | — | — | 79.8% | 22% | 75% | 169 | 22 |
| 1 | US postal address rule | Rules | recall +0.5 | 80.3% | 22% | 75% | 169 | 22 |
| 2 | Driver-licence filter ("Q3", "x4521" are not GOV_ID) | Presidio | extra −4 | 80.1% | 22% | 75% | 165 | 22 |
| 3 | Fiscal periods are not places | Presidio | extra −4 (only with #2) | 80.1% | 22% | 75% | 161 | 22 |
| 4 | Account number / card ending after a label | Rules | High +8 pts | 81.0% | 30% | 73% | 161 | 22 |
| 5 | SSN / Tax ID / licence number after a label | Rules | High +5 pts | 81.5% | 35% | 73% | 161 | 22 |
| 6 | ID numbers (after a label, or a prefixed code) | Rules | **High +28 pts** | 84.6% | 63% | 67% | 161 | 24 |
| 7 | Credentials (passcode, link with token, API key) | Rules | High +10 pts | 85.6% | 73% | 63% | 161 | 24 |
| 8 | "Project X" code names and the bare "X" | Rules | High +5 pts | 86.2% | 78% | 60% | 161 | 24 |
| 9 | Amounts: ranges, signs, percentages, RMB 万元 | Rules | **recall +2.7** | 88.9% | 78% | 57% | 163 | 26 |
| 10 | Role-mailbox senders are not people | Rules | extra −23 | 88.9% | 78% | 57% | 140 | 26 |
| 11 | Toll-free numbers and role mailboxes typed PUBLIC | Both | retain masked −15 | 88.9% | 78% | 57% | 140 | 11 |
| 12 | Dates must contain a digit | Presidio | **extra −58** | 88.9% | 78% | 57% | 82 | 11 |
| 13 | Remove ">" quote markers before detection | Both | recall +0.2 | 89.1% | 78% | 57% | 82 | 11 |

Rows 1–3 come from earlier fixes made on the ai4privacy dataset; rows 4–13 are new. Every row was kept only if it moved at least one metric on this data.

**Notes**
- **Row 3 needs row 2.** Presidio tags "Q3" twice: as a driver's licence (GOV_ID) and as a place (CITY). The two overlapping spans merge into one mask, so removing only one of the tags changes nothing.
- **Row 2 alone lowers recall by 0.2.** It drops "W2284", part of a member ID; row 6 recovers it.
- **Row 11 changes both detectors.** Its type function runs on rule and Presidio output alike. Otherwise the merge would keep the stricter, personal type from the other detector.

## What the strategies do

- **Values after a label (rows 4–7).** Account, ID and secret values have no fixed shape, so the rule reads the label in front of the value ("Account:", "Invoice No.", "MRN", "passcode") and masks the value only. A value must contain a digit, so "pin the doc" and "in order to" are ignored. IDs also exclude fiscal periods and bare years.
- **Code names (row 8).** "Project Kestrel" marks a code name, so the bare "Kestrel" elsewhere in the email is CODENAME too; spaCy had read it as a person. Names without the prefix ("Harbor Light") still need the client's term list.
- **Public contacts (rows 10–11).** A sender name from no-reply@ or billing@ is not a person. Role mailboxes and toll-free numbers are business contact points, so they get the Public tier: kept unless the model is fairly sure they are private.
- **Quote markers (row 13).** Detectors run on the text with leading ">" markers removed, and offsets are mapped back to the original text. This finds a phone number wrapped inside a quoted reply ("410-555-\n> 0171"). The code is in `privacy/quotes.py`; `segment()` is unchanged.

## Still missed

| Type | Recall | Why | Owner |
|---|---|---|---|
| HEALTH | 0% | Needs context ("treated for a heart attack") | Model |
| FACT | 0% | Confidential business facts | Model |
| ORG | 25% | Company names: whether a name is sensitive depends on context | Model |
| CODENAME | 60% | No "Project" prefix ("Harbor Light", "Bluebird") | Client term list |
| ID_NUMBER | 87% | In "MRN 00731946" the gold span includes the label, but only the value is masked | Rules (minor) |

## Segmentation

`segment()` (`service/vg_redactor/stubs/components.py`) is still a stub. It produces one segment per request field and does not split a signature or quoted text out of the body. Quote markers are now handled inside detection (row 13).

Signature and quote tags are deferred until model assessment is wired in, and will be added only if the model needs them as context. The evaluation set should gain some long reply chains: executive mail has them, and the current set has almost none.

## Limits

- **Overfitting.** All rules were written against the 60 development emails, so these numbers are optimistic. The real figure comes from a single run on the 40 test emails, once the pipeline is frozen.
- **Domain coverage.** Finance, HR and Legal have no test emails (TODO #16).
- **Over-redaction.** Four more *retain* spans are masked than in the baseline: two SKU-style IDs and two percentages. Percentages are Medium tier, so the model's score decides whether they stay masked.

## Reproduce

The scripts are in `service/scripts/eval/`; see the README there. Run them from the repo root with the service virtualenv.

| Script | Output |
|---|---|
| `eval_detectors.py` | Per-detector scores and a per-type check |
| `strategy_table.py` | The table above |
| `show_misses.py` | Missed spans with the text around them |
