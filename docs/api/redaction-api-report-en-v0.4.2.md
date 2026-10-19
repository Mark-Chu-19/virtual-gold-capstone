# Local Redaction Service — API Contract Summary

**Version:** 0.4.2-draft &nbsp;|&nbsp; **Status:** Draft for team and client review &nbsp;|&nbsp; **Owner:** Service Engineering

**Changelog (0.4.2):** Pinned down details the first implementation needs; no change to the
architecture. Component interfaces are in `service-interfaces-v0.4.2-en.md`.

- **Path.** All endpoints live under `/v1/redactions` (the workflow diagram's `POST /redact` is
  shorthand for `POST /v1/redactions`).
- **Recognizer failure.** If Presidio raises, the response is a degraded `200` with
  `degraded_reason: recognizer_failure` (new value). If the rule engine raises, the service
  returns `500` (there is no safe fallback below it).
- **`DELETE` is idempotent.** It always returns `204`, whether the record exists, expired, was
  already deleted, or never existed. The `404` is removed.
- **`/restore` does not consume the record.** It is read-only and idempotent, so a caller can retry
  safely. A record ends at its TTL or on `DELETE`. `410` now means expired or deleted only
  ("already consumed" is removed). Deleted and expired ids are remembered (id only) for
  `max_ttl_seconds` so `410` can be told apart from `404`.
- **Allow-list in degraded mode:** not applied (Open Question 13 resolved).
- **Field paths, validation rules, `policy.overrides` structure** are now specified (§3, §4).
- **Problem Details** carry a `type` from a fixed list (§3) and never echo input values.
- **`/metrics`** added: Prometheus text format on a separate local-only port.
- **`409` and `429` are reserved, not implemented** in this version (idempotency and rate limiting
  are deferred).
- **Response additions:** `record` object (`expires_at`, `mapping_retained`), `X-Request-ID` and
  `X-Degraded` headers, `contract_version` and `limits` in `/v1/info`, `components` in `/readyz`.
- **Open Questions** 6, 9, 10, 12, 13 resolved with provisional values (§5); 16 added.

**Changelog (0.4.1):** Matched the contract to the failure path in the architecture diagrams and
the midterm slides: the service **fails safe** instead of failing closed on model errors.

- **Degraded responses replace model errors.** If the local model is unavailable, times out, or
  returns unparseable output on either call, the service keeps only the rule and Presidio
  candidates, redacts every one of them, and returns `200` with `degraded: true`. The 503
  (model unavailable) and model-related 504 responses from 0.4.0 are removed.
- **New response fields.** `degraded` (always present), `degraded_reason`, `degraded_stage`.
  Degraded spans have `confidence: null`, `reason: degraded_redact_all`, and only the `rules` and
  `presidio` detectors.
- **Timeouts.** `timeout_ms` remains the end-to-end limit. A separate internal per-call model
  deadline lets the degraded path finish inside it. `504` now means even the degraded path could not
  finish.
- **`/readyz`, `/v1/info`, audit log.** `/readyz` reports `mode: ready | degraded`; `/v1/info`
  reports `failure_behavior`; the audit log records the degraded flag and failure type.
- **Open Questions** 3, 12 updated; 13–15 added. Degraded mode removed from §7.

**Changelog (0.4.0):** Aligned the contract with the first-version architecture.

- **Per-span decisions only.** Removed the request-level `decision` (`READY` / `LOCAL_ONLY` /
  `PENDING_REVIEW`) and `decision_reason`. Every span carries a `tier` and an `action`, decided by
  code from the tier table (tier × threshold).
- **Regulated categories replaced by tiers.** The `regulated:*` categories no longer force
  `LOCAL_ONLY`. They are High-tier types, redacted at a low confidence threshold, and cannot be
  loosened per request.
- **Asynchronous review removed from v0.** Removed `PENDING_REVIEW`, `GET /v1/redactions/{id}`,
  `EXPIRED`, the review-related `410`, and Open Questions 9–11 (old numbering). See §7.
- **Timeout is end-to-end.** `timeout_ms` bounds the whole request, from receipt to response.
- **Static context store.** A client-supplied term list and allow-list, not a cross-session store.
- **Two independent prompts.** One local model is called twice per request: a detection prompt and
  an assessment prompt. Responses report both prompt versions.
- **Restore simplified.** `/restore` looks up the local mapping and checks placeholders; the
  leak-scan of the cloud reply is removed from v0 (§7). `REVIEW_BLOCKED` is renamed `BLOCKED`.
- **Request fields.** `thread[].role` removed; `thread[].source` limited to coarse values.
  `source_context` is reserved and ignored.

## 1. Purpose

This service sits between the client's system and their cloud AI assistant. Before any text
reaches the cloud model, the client's system sends the user's task/purpose and the relevant
email (subject, sender, recipients, body, and quoted thread) here first. Rules, Presidio, and a
local open-source model together find candidate spans of private data. The same local model then
judges each candidate in its surrounding context and assigns a confidence score. Code compares each
calibrated score with the threshold for the span's tier and replaces the spans that qualify with
placeholders.

If the local model fails, the service falls back to rules and Presidio, redacts every candidate
they found, and flags the response as degraded.

The service never calls the cloud itself and needs no outbound network access. What happens to
the redacted content afterward — sending it to the cloud model, and using its reply — is
entirely the client system's responsibility.

## 2. Design Principles

- **Fail safe.** When a component fails, redact rather than guess. If the local model is
  unavailable, times out, or returns unparseable output on either call, the service keeps only the
  rule and Presidio candidates, redacts all of them, and returns `200` with `degraded: true` (the same applies if Presidio fails). A
  degraded result is safer than passing text through, but it cannot find what only the model finds
  (for example business-confidential items outside the term list), so the client should treat its
  residual risk as higher and decide whether to forward it.
- **Non-2xx means not processed.** Any non-2xx response means the content was *not* processed or
  redacted, and the client must not forward it to the cloud model.
- **The model proposes; code decides.** The local model finds candidate spans and scores how likely
  each is to be private in context. The redaction decision for each span is made by code, using the
  calibrated score and the tier table (tier × threshold). The model never decides alone.
- **Tier-based thresholds.** The more severe the potential harm, the lower the confidence required
  before a span is redacted. The tier table and its initial thresholds are for client review (§4).
- **High tier is fixed.** High-tier types (government IDs, credentials, financial, health,
  business-confidential) are governed entirely by the fixed `policy_version` and cannot be loosened
  per request.
- **Static context store.** The context store is a read-only term list and allow-list supplied by
  the client. It is loaded with the service and versioned; it is not modified by requests.
- **No sensitive logging.** Input text, detected values, and restored text are never logged —
  only IDs, counts, timings, tiers, actions, scores, and error types.
- **Local only.** No outbound network calls; nothing leaves the machine unless the client system
  chooses to send the already-redacted content onward.

## 3. Endpoints

Auth: `Authorization: Bearer <api-key>` on every endpoint except `/healthz` and `/readyz`.
`/metrics` is not on the main port (see below).
All error bodies are RFC 9457 Problem Details (`application/problem+json`) with `type`, `title`,
`status`, and `request_id`. `type` is one of: `urn:vg:problem:malformed-json` (400),
`unauthorized` (401), `not-found` (404), `gone` (410), `payload-too-large` (413),
`unsupported-media-type` (415), `validation-failed` (422, adds `violations`), `internal` (500),
`capacity-exhausted` (503, sets `Retry-After`), `deadline-exceeded` (504). `detail` and
`violations` (`[{"field": "...", "code": "..."}]`) contain only field paths and error codes,
never input values.

`request_id` (`req_<ULID>`) is generated on receipt and appears in every response, including
errors. On a `200` it is also the record id used by `/restore` and `DELETE`. A caller-supplied
`X-Request-ID` is ignored.

### POST `/v1/redactions` — detect and redact

**Purpose:** Detect private data across the user's purpose and structured email content, and
return it with the qualifying spans replaced by placeholders.
**Fail safe:** any non-2xx means the content was *not* processed. A `200` means the content was
processed and the redacted content is returned; check `degraded` to learn whether the model
contributed.

**Request body** (structured email object):

```json
{
  "purpose": "Summarize this email",
  "purpose_source": "executive_instruction",
  "email": {
    "subject": "Support question",
    "from": {"name": "Example Sender", "address": "sender@example.test"},
    "to": [{"name": "Support Team", "address": "support@example.test"}],
    "cc": [],
    "body": "Please call me at 202-555-0102.",
    "thread": [
      {
        "message_id": "m-1",
        "source": "quoted_thread",
        "text": "Our public support line is 800-555-0100."
      }
    ]
  },
  "source_context": {"sensitivity": "unverified", "access": "authorized_for_request"},
  "session_id": "optional-string",
  "mapping": {"retain": false, "ttl_seconds": 3600},
  "policy": {"overrides": {"thresholds": {"medium": 0.6}, "entity_types": {"exclude": ["ORG_NAME"]}, "allow_list": ["support@example.test"], "deny_list": ["Project Falcon"]}}
}
```

**Validation.** Unknown fields are rejected (`422`) so a misspelled option such as `retain` is
never silently ignored. `purpose` is required (1–2,000 characters); `email.body` is required;
`email.thread` has at most 50 items; `session_id` matches `^[A-Za-z0-9_-]{1,64}$` and requires
`mapping.retain: true` (`422`, code `session_requires_retain`); `mapping.ttl_seconds` is between 1
and `max_ttl_seconds` (default 86,400; default value when omitted is 3,600). The request body is
limited to `max_request_bytes` (default 262,144, provisional).

**Field paths.** `spans[].field` is one of `purpose`, `email.subject`, `email.from.name`,
`email.from.address`, `email.to[i].name`, `email.to[i].address`, `email.cc[i].name`,
`email.cc[i].address`, `email.body`, `email.thread[i].text`. `start` and `end` are Unicode code
point offsets into that field's **original** text, half-open `[start, end)`.

**`policy.overrides`.** `thresholds` accepts the `medium` key only; `entity_types.exclude` lists
types to skip; `allow_list` and `deny_list` are literal strings (a `deny_list` match is treated as
a High-tier candidate). Low and public tiers are not single-threshold rules and cannot be
overridden. Touching a High-tier type (a threshold for `high`, excluding a High-tier type, or an
`allow_list` entry that matches a High-tier candidate) returns `422` with code `high_tier_fixed`.

`source_context` is reserved for a future request-level release check and is ignored in v0.4.
`thread[].source` takes coarse values only (`quoted_thread`); the body is `email.body` and the
user's own words are `purpose`. The service uses these labels to tag where each piece of text came
from.

**Response 200:**

```json
{
  "request_id": "opaque-id",
  "degraded": false,
  "degraded_reason": "model_unavailable | model_timeout | model_output_unparseable | recognizer_failure — present only if degraded=true",
  "degraded_stage": "detection | assessment — present only if degraded=true",
  "redacted_email": "same shape as input email, transformed",
  "redacted_purpose": "string",
  "spans": [
    {
      "field": "email.body",
      "start": 0,
      "end": 0,
      "type": "PHONE_PERSONAL",
      "tier": "high | medium | low | public",
      "action": "redact | retain",
      "confidence": 0.0,
      "detectors": ["rules", "presidio", "model"],
      "reason": "string"
    }
  ],
  "record": {"expires_at": "ISO-8601 timestamp", "mapping_retained": false},
  "policy_version": "string",
  "model_version": "string",
  "prompt_versions": {"detection": "string", "assessment": "string"},
  "context_store_version": "string"
}
```

- `confidence` is the **calibrated** score produced by the assessment step and used for the
  decision. The raw model score is not returned; it is recorded only in the audit log. It is `null`
  when `degraded` is `true`.
- `detectors` lists every source that produced the span. The three sources are merged by character
  position, so overlapping spans are reported once.
- `reason` is a stable code with no private text, for example `term_list_match`, `allow_list`,
  `below_threshold`, `isolated_low_tier`, or `cannot_classify_default_redact`.
- `spans` never contain the original value.
- Response headers: `X-Request-ID` (same as `request_id`) and `X-Degraded: true | false`.

**Degraded responses.** When `degraded` is `true`: every span has `action: redact`,
`confidence: null`, `reason: degraded_redact_all`, and `detectors` limited to `rules` and
`presidio` (term-list matches count as rules). `tier` is still given from the entity type. The
model's detection output, if the first call had succeeded, is not used. `degraded_stage` says which
model call failed (`detection` for `recognizer_failure`). On `recognizer_failure`, the candidates
are the rule matches plus the model's detection output if that call succeeded; assessment and
thresholds are skipped. Because every candidate is redacted without thresholds, degraded results
over-redact (for example cities and published support lines); this is intended.

`request_id` is issued for every `200` response, even when no span required a placeholder, so
`/restore` and `DELETE` can reference it.

| Code | Meaning |
|---|---|
| 200 | Request processed and redacted — see `action` on each span and `degraded` |
| 400 | Malformed JSON or missing body |
| 401 | Missing or invalid API key |
| 409 | Reserved — idempotency is not implemented in 0.4.2 |
| 413 | Request exceeds `max_request_bytes` (provisional; see Open Question 6) |
| 415 | Body is not `application/json` |
| 422 | Valid JSON but fails a schema/business rule (e.g. `session_id` without `mapping.retain: true`, an override attempted on a High-tier type, or an unknown field) |
| 429 | Reserved — rate limiting is not implemented in 0.4.2 |
| 500 | Internal error, including rule-engine failure — content was not processed |
| 503 | Content was not processed: request-record capacity exhausted (`capacity_exhausted`); `Retry-After` is set. Model failures do **not** return 503; they return `200` with `degraded: true` |
| 504 | End-to-end `timeout_ms` exceeded, even on the degraded path — content was not processed |

**Timeout.** `timeout_ms` (service setting, default 15,000 ms, provisional) is the total time the
service may spend on a request, from receiving it to sending the response. It covers both model
calls and all other processing. Callers should set their own client timeout slightly above it.
Each model call also has an internal deadline (`model_call_timeout_ms`, service setting,
provisional). The deadline is chosen, and shortened when the remaining budget is small, so that a
failed or timed-out model call still leaves enough time for the degraded path (rules and Presidio
candidates, redact all, pseudonymise) to finish inside `timeout_ms`. A model timeout therefore
produces a degraded `200`, not a `504`.

### POST `/v1/redactions/{id}/restore` — restore placeholders

**Purpose:** Exact-match known placeholders in a reply back to their original values, using the
local mapping for this redaction. Placeholders the service did not issue are never guessed.

**Request body:** `{"reply_text": "string containing placeholders"}`

**Response 200** (the call succeeded; `restore_decision` carries the business outcome):

```json
{
  "restore_decision": "RESTORED | BLOCKED",
  "restored_text": "present only if restore_decision=RESTORED",
  "unmatched_placeholders": ["listed, never silently dropped"],
  "reason": "present only if BLOCKED — e.g. unknown_placeholder, mapping_not_retained"
}
```

Placeholders issued in a degraded response restore exactly like any other. `BLOCKED` is a
synchronous, fail-closed refusal: nothing further happens automatically. If the reply
contains a placeholder that was not issued for this redaction (unknown, malformed, or case-changed),
no text is restored and the placeholder is listed in `unmatched_placeholders`. The whole restore is
blocked (Open Question 9, resolved). Placeholder-like strings are found with the case-insensitive
pattern `\[[A-Za-z]+_\d+\]` and must then match the mapping exactly.

`/restore` is read-only and idempotent: it does not consume the record, so the same id can be
restored again until the record's TTL ends or it is deleted.

If `mapping.retain` was not set on the original request, the record exists but holds no original
values: the call returns `BLOCKED` with reason `mapping_not_retained`.

| Code | Meaning |
|---|---|
| 200 | Processed — see `restore_decision` |
| 400 | Malformed JSON or missing body |
| 401 | Missing or invalid API key |
| 404 | No record with this `id` was ever issued (including after a process restart) |
| 410 | Record existed but expired or was deleted |
| 422 | Request fails validation |
| 413 | `reply_text` exceeds `max_request_bytes` |
| 500 | Internal error |

### DELETE `/v1/redactions/{id}` — delete a record

**Purpose:** Remove a request's record and its placeholder mapping before its TTL expires.
Idempotent: the call returns `204` whether the record exists, expired, was already deleted, or
never existed, so it does not reveal whether an id was valid.

| Code | Meaning |
|---|---|
| 204 | Record deleted or already gone — restore now returns 410 for a record that existed |
| 401 | Missing or invalid API key |

### GET `/v1/info` — service metadata

Returns `service_version`, `contract_version`, model, prompt, policy, and context-store versions;
the tier table with the threshold for each tier; the entity type taxonomy with each type's tier;
`limits` (`max_request_bytes`, `timeout_ms`, `max_ttl_seconds`, `max_records`); and
`failure_behavior: "redact_all_candidates"` (what the service does when the model fails).

### GET `/healthz` — liveness (no auth)

Process is running. Does **not** check the model.

### GET `/readyz` — readiness (no auth)

Returns `200` with `components` (`rules`, `presidio`, `model_detection`, `model_assessment`, each
`up` or `down`) and `mode: "ready"` when the model is loaded and warmed up for both prompts, or
`mode: "degraded"` when the model is not available but rules and Presidio are (requests will return
degraded responses). Returns `503` only if even the degraded path cannot serve — stop sending
traffic.

### GET `/metrics` — Prometheus metrics (separate port, local only)

Served on a separate port bound to `127.0.0.1` (default 9100), no auth, Prometheus text format.
Metrics hold only counts, timings, tiers, actions, and error types as bounded-cardinality labels;
never text, detected values, or ids. Metric names and labels are listed in
`service-interfaces-v0.4.2-en.md` §6.

## 4. Key Concepts

- **Redaction result.** Each call to `/v1/redactions` returns the redacted content and a list of
  spans — each with its entity type, tier, action, calibrated confidence, the detectors that found
  it, and a short reason — but never the original value.
- **Tiers and thresholds (initial values, for client review).**

  | Tier | Examples | Redaction rule |
  |---|---|---|
  | High | Government IDs, passwords and keys, bank and card numbers, health information; business-confidential information (unreleased results, deal terms, project code names, legal matters) | Redact at confidence ≥ 0.2 |
  | Medium | Names of private individuals, personal phone numbers, personal email addresses, home addresses | Redact at confidence ≥ 0.5 |
  | Low | City, dates, organisation names, age, gender | Retain when isolated; redact when several items together could identify an individual |
  | Public | Public figures, published support lines, company names in a public context | Retain only when the model is confident the item is public |

  Final thresholds will be set empirically on labelled emails (Open Question 5).
- **Two model calls, two independent prompts.** One local model is used twice per request. The
  *detection prompt* asks it to find sensitive spans in the text; this runs in parallel with the
  rules and Presidio. The *assessment prompt* gives it the merged candidates and asks it to judge
  each one in its surrounding text and return a raw score; this runs after the merge. The prompts
  are versioned and tuned independently. Raw scores are calibrated against labelled emails before
  they are used. Proper nouns and amounts the model cannot classify are redacted by default. If either
call fails, the request is degraded (see below).
- **Three-way candidate detection.** Candidates are the union of rules (with checksum validation),
  Presidio, and the model's detection output, merged by character position.
- **Static context store.** The service consults a read-only store supplied by the client: a
  **term list** (project code names, deal names, key counterparties — a match is a candidate in the
  High tier) and an **allow-list** of known safe items. It is loaded with the service and reported
  as `context_store_version`. It does not accumulate entities from requests and is not shared
  state across sessions. Changing it means deploying a new version.
- **Session-based label consistency.** `session_id` keeps one mapping internally consistent: the
  same real-world entity gets the same placeholder label (e.g. `[PERSON_1]`) across every request
  in that session. It is unrelated to the context store.
- **Policy overrides — medium, low, and public tiers only.** A caller can adjust the confidence
  threshold for those tiers, restrict which entity types to look for, or supply allow/deny lists,
  but never for High-tier types. High-tier handling is governed entirely by the fixed
  `policy_version`; an attempt to override it returns `422`.
- **Request record (always created).** Every `200` response creates an in-memory, request-scoped
  record with a bounded lifetime and a service-wide capacity cap. It holds no original values unless
  `mapping.retain: true`. A slot is reserved before any processing starts and released if the request fails. If capacity is
  exhausted the service returns `503` rather than evicting a live record. A process restart loses all records, so any later restore fails with `404`.
- **Mapping retention (opt-in).** Setting `mapping.retain: true` stores the placeholder-to-original
  mapping inside the record, so `/restore` can substitute real values back in. Without it, `/restore`
  returns `BLOCKED` with reason `mapping_not_retained`.
- **Restore.** `/restore` exact-matches known placeholders against one redaction's mapping. It
  bypasses detection, assessment, and the threshold decision. **Known limitation:** restore works
  against one redaction's mapping at a time; if a reply mixes placeholders from several redactions,
  the others are reported as unmatched, never silently dropped.
- **Degraded mode (fail safe).** When the model cannot be used on either call (or Presidio fails), the service
  discards model output, keeps the rule and Presidio candidates (including term-list matches),
  redacts every one, and sets `degraded: true`, `degraded_reason`, and `degraded_stage`. Thresholds
  and calibration are skipped. The allow-list is not applied. Restore, mapping retention, and `DELETE` work as usual. Evaluation
  reports degraded-mode results separately from normal-mode results.
- **Audit log.** Records category (type), score, tier, action, degraded flag, failure type,
  timings, and error types. Original text is never logged.

## 5. Open Questions

| # | Question | Owner |
|---|---|---|
| 1 | Does the client need restore, or does their system handle it? | Client |
| 2 | Latency target per email, and expected daily volume. Each request makes two model calls, so the end-to-end budget needs to be measured on the confirmed hardware | Client + Service Eng. |
| 3 | Confirm fail-safe behavior on model failure: every rule and Presidio candidate redacted, response flagged `degraded`, no blocking | Client |
| 4 | Entity type taxonomy and its assignment to tiers (current list is provisional) | Privacy Research |
| 5 | Threshold for each tier, calibrated on the 100-email baseline | Evaluation |
| 6 | ~~Maximum request size and deployment target~~ **Resolved (provisional):** `max_request_bytes` 262,144; the service binds to the local host and TLS is handled by the deployment, not the service. Confirm the deployment target | Service Eng. + Client |
| 7 | Restore scope: should a session- or batch-level restore endpoint be added to cover cloud replies that mix placeholders from more than one redaction? | Client + Service Eng. |
| 8 | Term list and allow-list: who supplies them, in what format, and how are updates deployed? | Client + Privacy Research |
| 9 | ~~Restore with an unknown placeholder~~ **Resolved:** block the whole restore and list the unmatched placeholders | Service Eng. |
| 10 | ~~Bounded lifetime and capacity cap~~ **Resolved (provisional):** default TTL 3,600 s, `max_ttl_seconds` 86,400, `max_records` 1,000; tune after load testing | Service Eng. |
| 11 | Is the coarse source labelling in the request (`email.body`, `quoted_thread`, `purpose`) acceptable under the NDA? | Client |
| 12 | ~~Default `timeout_ms`~~ **Provisional:** `timeout_ms` 15,000 ms, `model_call_timeout_ms` 6,000 ms, `degraded_reserve_ms` 1,500 ms; final values come from load testing on the target hardware | Service Eng. + Client |
| 13 | ~~Allow-list in degraded mode~~ **Resolved:** not applied (safer) | Privacy Research + Service Eng. |
| 14 | Should a caller be able to opt into blocking instead (for example `on_degraded: "error"` returning an error rather than a degraded `200`)? | Client + Service Eng. |
| 15 | If the detection call succeeded but the assessment call failed, should the model's detected spans be included in the degraded redaction (safer) or discarded (current)? | Service Eng. + Privacy Research |
| 16 | Confirm `recognizer_failure` behavior: a Presidio failure returns a degraded `200`; a rule-engine failure returns `500` | Client + Service Eng. |

## 6. Out of Scope for v0

Attachments and OCR, batch requests, streaming, and languages other than English.

## 7. Future Work (not in the first version)

These were in 0.3.0 or earlier proposals and are intentionally not part of the first version.

- **Request-level release decision.** A whole-request policy gate that returns `LOCAL_ONLY` for
  confidential, health, financial, or credential content or unknown provenance. Needs a decision on
  gate granularity (whole request vs per span) before it returns. `source_context` is reserved for it.
- **Asynchronous human review.** `PENDING_REVIEW`, `GET /v1/redactions/{id}` with
  `PENDING_REVIEW | RESOLVED | EXPIRED`, cancelling a review via `DELETE`, and a webhook alongside
  polling. Open design questions: polling vs webhook, the bounded lifetime of a pending review and
  whether it shares the record capacity cap, and whether `DELETE` may cancel a pending review.
- **Restore leak-scan.** Scanning the cloud reply for newly introduced private content before
  restoring, with a blocking outcome when any is found.
- **Session- or batch-level restore** across placeholders from several redactions.
- **Caller-selectable failure behavior**, such as an opt-in `on_degraded: "error"` (Open Question 14).
