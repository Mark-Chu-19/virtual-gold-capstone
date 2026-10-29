# Baseline Redaction Dataset v1.1

The same 100 fictional executive emails as v1, with three changes:

1. **Each email is also a service request.** A `request` object validates against `RedactionRequestV3` in `service/vg_redactor/contracts/types.py` (V3 contract), so it can go straight to `/v3/redaction`.
2. **Each span carries the service's own coordinates and types.** `field`, `field_start` and `field_end` follow the contract's FieldPath. `service_type` and `tier` follow `service/config/policy.yaml` 0.1.3.
3. **A `ground_truth` column, reviewed by hand.** Each span is `redact` or `retain`. This answers Aarvin's question from the Oct 5 midterm about how we can trust LLM-generated labels: a person checks every label.

**Status: reviewed.** Claude proposed the ground truth on Oct 24 and Karina checked every row in `baseline_v1.1_review.xlsx` (`Karina check` is `OK` on all 1,058 rows). There is no separate status field: the `ground_truth` column is the final label.

The original v1 labels are kept inside v1.1 (`type` and `must_mask` on every span), so v1 scores can still be reproduced with `--truth must_mask`. The separate v1 file is in the Drive zip from Sep 27 and in the Capstone project if it is ever needed.

## Files

| File | What it is |
|---|---|
| `baseline_v1.1.jsonl` | The dataset, and the source of truth for scoring |
| `baseline_v1.1_review.xlsx` | Review workbook: one row per span, with the yellow `ground_truth` and `Karina check` columns to edit |
| `score.py` | Scorer for v1 or v1.1. Accepts text offsets or the service's field offsets |
| `baseline_regex.py` | Rules-only floor, unchanged |
| `check_with_service.py` | Runs the dataset through the team's own service code (contract models, segmentation, `rules.py`, `decide()`) |

## Record format

```json
{
  "id": "E002", "domain": "Finance & Accounting", "industry": "Banking", "exec": "CFO",
  "task": "Is this wire request legitimate? ...", "tags": ["fin_account", "wire", "vendor"],
  "text": "From: Allison Grant <agrant@tidewaterrb.com>\nTo: ...\nSubject: ...\n\nHi Victor, ...",
  "request": {
    "purpose": "Is this wire request legitimate? ...",
    "email": {"subject": "...", "from": {"name": "Allison Grant", "address": "agrant@tidewaterrb.com"},
              "to": [{"name": "Victor Ames", "address": "vames@tidewaterrb.com"}], "cc": [], "body": "Hi Victor, ..."}
  },
  "field_offsets": {"email.from.name": 6, "email.from.address": 21, "email.to[0].name": 49, "email.to[0].address": 62, "email.subject": 94, "email.body": 145},
  "spans": [{
    "start": 406, "end": 420, "text": "4402 1187 9930",
    "type": "FIN_ACCOUNT", "must_mask": true,
    "ground_truth": "redact", "gt_note": "",
    "field": "email.body", "field_start": 261, "field_end": 275,
    "service_type": "ACCOUNT_NUMBER", "tier": "high", "in_policy": true,
    "source": "v1"
  }]
}
```

| Span field | Meaning |
|---|---|
| `start`, `end` | Offsets into `text`, same as v1 |
| `type`, `must_mask` | The original v1 label. `must_mask` is `null` for spans added in review |
| **`ground_truth`** | **`redact`: a leak if it reaches the cloud raw. `retain`: public or harmless. Scoring uses this.** |
| `gt_note` | Why the review differs from v1. Empty means the review agrees |
| `field`, `field_start`, `field_end` | Where the span sits in `request`. `field_offsets[field] + field_start == start` always holds |
| `service_type`, `tier` | Type and tier from policy.yaml. `in_policy: false` means the type is not in policy.yaml yet, and then `tier` is `high`, because that is what `Policy.tier_of()` does with unknown types |
| `source` | `v1`, or `added_in_review` |

## What changed from v1

**1,058 spans: 1,009 `redact`, 49 `retain`.** v1 had 999 spans: 971 must_mask and 28 ok either way.

| | Spans | What |
|---|---|---|
| Agree with v1 | 984 | 9 of them carry a note: kept as redact but worth a look, or the type changed |
| Changed to `retain` | 15 | 12 role or system mailboxes, 1 company business address, and "Abuela" twice |
| Added | 59 | 29 entities inside FACT clauses, 12 missed facts or health details, 18 other misses |

**Changed to `retain`.** These were all must_mask in v1. Each has a reason in `gt_note`.

| Email | Span | Why |
|---|---|---|
| E004, E013, E020, E022, E026, E035, E043, E047, E056, E077, E078 | `no-reply@`, `benefits@`, `servicedesk@` and other role mailboxes | Not a person, and they tell the cloud nothing it doesn't already know |
| E050 | `security-alert@micros0ft-support.co` | The phishing sender. The assistant needs it to answer "is this phishing?" |
| E006 | 1200 Harbor Point Blvd, Baltimore | The executive's own company office address, which is public |
| E076 | "Abuela" (twice) | Means "grandma". A family word, not a name. Her health detail is still redacted |

Three role mailboxes stay `redact` because they do reveal something private: outside counsel on a legal matter (E011), the executive's doctor (E073) and personal broker (E074).

**Added.**

1. **Entities inside FACT clauses (29).** A FACT only needs 50% coverage to count as caught, so a name inside one could leak while the score still looks fine. Each entity now has its own span. The serious ones are a patient name (E093 "Tanya Brooks"), a whistleblower subject (E013 "Carl Dennison") and the cancer center that gives away a diagnosis (E021 "MD Anderson").
2. **Missed facts and health details (12).** For example, the impairment memo (E005), a missed regulatory filing (E017), medical leave (E018), a drug test (E055), unreported injury complaints and litigation (E058), and unannounced deals and delays (E028, E060, E066, E067).
3. **Other misses (18).** A greeting name (E075 "Dan"), the CEO's destination and dates in a security brief (E083 "Mexico City", "Oct 26 to 28"), outside counsel (E004), sender names that give away a doctor or broker (E073, E074), and some amounts. Six public items were added as `retain` so the decision is on record: published tariff rates (E094), a support email address (E031), an IT desk extension (E047), a public SKU (E058) and a retail price (E065).

**Type changes (4).** E021 FACT to HEALTH (a family member's cancer treatment). E055 driver license number from ID_NUMBER to GOV_ID. E077 utility account number from ID_NUMBER to ACCOUNT_NUMBER (policy 0.1.3 covers client account numbers). E083 hotel and street from CITY to ADDRESS_HOME (private in context; as CITY the service would keep it).

## What to notice

1. **Every label was checked by hand.** Karina reviewed all 1,058 rows in the workbook, so the dataset can be described to the client as hand-checked.
2. **The v1 README overstates its negative controls.** It says ten emails have nothing that must be masked. Only four are fully clean (E007, E023, E052, E095). The other six (E014, E031, E045, E059, E071, E085) still contain recipient names or addresses. They are still useful for measuring over-masking, but the claim should change.
3. **87 must-redact spans fall in the Low tier**: 68 ORG, 11 CITY, 7 DATE and 1 AGE. `decide()` keeps a Low-tier item unless 3 different Low-tier types appear in the same field. Running the real `decide()` on these spans, with the model fully confident they are private (score 0.9), all 87 are still kept (`isolated_low_tier`), so the service would let every one of them through. The worst cases are dates of birth (DOB maps to DATE) and deal counterparties (ORG). Counterparties belong in the client's term list (TODO D49). DOB likely needs its own Medium or High type. This is a policy decision for the team.
4. **39 spans have no type in policy.yaml**: 38 ID_NUMBER (case numbers, medical record numbers, order numbers) and 1 plain URL. They are marked `in_policy: false`. The service already handles unknown types safely: `Policy.tier_of()` calls them High and `decide()` redacts them (`cannot_classify_default_redact`), so `tier` says `high`. The 5 ID_NUMBER spans marked `retain` (public filing and SKU numbers) will be over-redacted until ID_NUMBER gets a real tier. URLs that contain a token, key or password map to CREDENTIAL.
5. **Contract mismatches.** 0.4.2 has no `bcc`, so E043's Bcc address is placed in `cc`. List recipients with no address ("All Employees") are dropped, which affects 7 emails, none with labels. Policy 0.1.3 adds ADDRESS_PUBLIC, so the employer's own bill-to address in E006 is ADDRESS_PUBLIC. Office addresses that are private in context (E073 clinic location, E086 unannounced HQ lease) stay ADDRESS_HOME with ground truth redact. Quoted and forwarded text stays in `email.body` (E003, E099), the way a raw email arrives. Splitting it out is the segmentation step's job.
6. **Regex floor scores moved slightly.** Against the v1.1 ground truth: recall 0.40, leak rate 96%, fact recall 0.00. By tier, 32% of emails leak a High-tier span, 96% leak a Medium-tier span and 51% leak a Low-tier span. `--truth must_mask` reproduces the v1 recall and leak rate exactly. `extra_masks` drops from 12 to 4, because some of the regex's "extra" masks now land on spans added in review.

7. **The team's rules detector needs a fix (for Yudi).** `rules.py` takes every header display name as a person, and `NON_PERSON_WORDS` misses many mailbox names. "Concur Expense", "Benefits Center", "Ethics Hotline", "SEC Filing Alerts", "Google Calendar", "FDIC Updates", "BGE Billing" and similar names get flagged as PERSON, and so do their parts elsewhere in the text ("Expense", "Treasury", "FDIC"). That accounts for all 30 extra masks below. Adding words like alerts, updates, billing, center, hotline, calendar, workflow, screening, escalations and insights to `NON_PERSON_WORDS` would fix most of them.

## Tested against the team's code

`check_with_service.py` imports the service from `service/` and runs four checks:

1. All 100 `request` objects validate with the real `RedactionRequestV3` model.
2. The real segmentation step produces exactly the fields in `field_offsets`, at exactly those offsets, for every email.
3. The real `rules.py` runs on every request, and its output scores directly with `score.py`, with no conversion. Rules alone: recall 0.66, leak rate 87%, fact recall 0.00, extra masks 30. By tier, 46% of emails leak a High-tier span and 66% a Medium-tier span. Rules catch every email address and 79% of names, but no bank accounts, codenames, health details or ID numbers. The model has to close that gap.
4. The real `decide()` confirms the Low-tier gap in note 3.

## Scoring

```bash
python baseline_regex.py baseline_v1.1.jsonl > pred.jsonl
python score.py baseline_v1.1.jsonl pred.jsonl                    # grades against ground_truth
python score.py baseline_v1.1.jsonl pred.jsonl --truth must_mask  # v1 labels, for old numbers
```

Predictions can use v1 text offsets (`start`, `end`) or the service's internal component spans (`field`, `start`, `end`; V3 omits spans from HTTP responses). Service spans with `"action": "retain"` are ignored. v1.1 adds `leak_rate_by_tier`, the primary metric on deck slide 19.

## Checks run on this version

1. All 100 `request` objects validate against the service's own `types.py`, and segmentation matches `field_offsets` (see above).
2. For every span, the text at `start:end` and the text at `field_start:field_end` inside its field both equal `text`. There are no duplicate spans and no partial overlaps.
3. A prediction that masks exactly the `redact` spans scores recall 1.0, fact recall 1.0 and leak rate 0.
4. A final sweep found nothing unlabeled: every money amount, percentage, email address, phone number, long number, URL and proper noun is either labeled or judged public. The leftovers are public or generic, like the employer's own name, regulators, trip destinations, product names and calendar words.
