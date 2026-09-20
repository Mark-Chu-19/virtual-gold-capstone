# Synthetic data: record schema (workstream 5)

**Owner:** Karina · **Status:** proposed, not yet reviewed by Zhexuan (PR #2) · **Format:** JSON Lines (one JSON object per line)

This turns TODO.md item 14a and F32, plus the Sep 18 team decision to pursue the financial trading assistant as the vertical, into one schema the confidence-harness (workstream 3) and the security tests (workstream 4) can both consume without re-parsing.

## Why JSONL

The harness already loads MMLU and GSM8K through Hugging Face `datasets`, which reads JSONL natively. Using the same format means workstream 3 does not need a second loader for our data.

## Record fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Unique record id, e.g. `synth-0001` |
| `batch` | enum | yes | `demo_w5` (the dozen PII-bearing requests for the midpoint CLI demo, TODO 14a-i), `pii_leak_w9` (bulk documents/queries for the W9–W11 PII-leak and prompt-injection tests, TODO 14a-ii), or `accuracy_benchmark` (the finance QA sample used for scored accuracy) |
| `query` | string | yes | The user-facing request text the router receives |
| `sensitivity` | enum | yes | `public`, `internal`, or `confidential`, exactly the three levels in architecture §10. Confidential must never leave local regardless of confidence (architecture §4, §10). |
| `query_split` | object or null | no | Only for mixed requests like the Apple 10-Q / "my position" example from the Sep 18 agenda. `{ "public_text": "...", "confidential_text": "..." }`, the substrings of `query` that should be routed differently. Lets the harness check the router's query-split component, not just the top-level sensitivity tag. |
| `source_type` | enum | yes | `real_filing`, `real_market_data`, `synthetic_strategy_note`, `synthetic_document`, or `external_benchmark` |
| `source_ref` | string or null | no | What the record is grounded in, e.g. `"AAPL 10-Q 2026-Q2"` for a real filing, or the FinanceBench/FinQA/TAT-QA item id for a benchmark record |
| `document_text` | string or null | no | Full synthetic document body, for `pii_leak_w9` records that are documents rather than short queries (Presidio is tested against realistic document length, not just one-line prompts) |
| `ground_truth_answer` | string or null | no | Only populated for `accuracy_benchmark` records pulled from a scored dataset. Everything else is null, there is no objectively correct answer to check a generated strategy note against. |
| `planted_pii` | array | yes (empty array if none) | List of `{ "type": ..., "value": ..., "start": int, "end": int }`. `type` matches the Presidio entity categories the architecture already names in §6: `PERSON`, `ORG`, `ACCOUNT`, `AMOUNT`, `PHONE`, `DATE`. `start`/`end` are character offsets into `query` (or `document_text` if that field is used). This is what lets someone compute Presidio's miss rate later, without knowing what was planted and where, miss rate cannot be scored. |
| `expected_redaction` | boolean | yes | `true` if this record exists specifically to test that the gateway catches the planted PII (all of `pii_leak_w9`), `false` for demo or accuracy records where redaction is not the thing under test |
| `notes` | string | no | Freeform, e.g. which prompt template generated it |

## Example record

```json
{"id": "synth-0001", "batch": "demo_w5", "query": "Based on Apple's latest 10-Q, what does the services-revenue trend mean for my current position?", "sensitivity": "confidential", "query_split": {"public_text": "Based on Apple's latest 10-Q, what does the services-revenue trend mean", "confidential_text": "for my current position"}, "source_type": "real_filing", "source_ref": "AAPL 10-Q 2026-Q2", "document_text": null, "ground_truth_answer": null, "planted_pii": [], "expected_redaction": false, "notes": "worked example from the Sep 18 team agenda, item 1"}
```

```json
{"id": "synth-0142", "batch": "pii_leak_w9", "query": null, "sensitivity": "confidential", "query_split": null, "source_type": "synthetic_document", "source_ref": null, "document_text": "Trader note: contact John Meraz at 555-019-2231 or account 4471-2209 re: adding NVDA to 8% if it breaks the 200-day.", "ground_truth_answer": null, "planted_pii": [{"type": "PERSON", "value": "John Meraz", "start": 14, "end": 24}, {"type": "PHONE", "value": "555-019-2231", "start": 28, "end": 40}, {"type": "ACCOUNT", "value": "4471-2209", "start": 51, "end": 60}], "expected_redaction": true, "notes": "synthetic, generated for the PII-leak miss-rate test"}
```

## How the three batches map to what already exists

**`demo_w5`**, about a dozen records, due week 5 (TODO 14a-i). Feeds the CLI demo shown at the W7 midpoint: one request containing PII, going through redaction, escalation, and re-identification (architecture §9, "MVP: the team's committed deliverable"). Build this batch first, it is small and it is what Mark needs soonest.

**`pii_leak_w9`**, generated in volume, format and prompts fixed in W5 but the bulk generation happens before W9 (TODO 14a-ii). Feeds the PII-leak rate metric, one of the six per-configuration metrics in architecture §7, and the Presidio miss-rate evaluation named in §6 and in the F31 security research item.

**`accuracy_benchmark`**, pulled from whichever of FinanceBench, FinQA, or TAT-QA the financial-data-sources one-pager confirms has usable ground truth and a permitting license. This is the only batch with a real correct answer to score against; everything synthetic in the other two batches is there to test redaction and routing, not to test whether the model's answer is right.

## Open question for Zhexuan (PR #2)

This schema is proposed, not confirmed. If the harness design doc settles on different field names or an existing loader convention, this file should be updated to match rather than adding a second, competing shape.
