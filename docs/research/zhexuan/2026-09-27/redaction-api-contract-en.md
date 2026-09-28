# Local Redaction Service — API Contract Summary

**Version:** 0.3.0-draft &nbsp;|&nbsp; **Status:** Draft for team and client review &nbsp;|&nbsp; **Owner:** Service Engineering

**Changelog (0.3.0):** Human review is now explicitly asynchronous — `/v1/redactions` never blocks
waiting for a person. Renamed the overloaded `NEEDS_REVIEW` value into two distinct outcomes:
`PENDING_REVIEW` (the initial request — a human hasn't looked yet) and `REVIEW_BLOCKED` (the
restore endpoint's leak-scan/placeholder check failed). Added `GET /v1/redactions/{id}` so a
client can poll a `PENDING_REVIEW` request until it resolves. Clarified that `DELETE` also cancels
a still-pending review, and that `session_id` exists to keep placeholder labels consistent within
one mapping, not to look up known entities (that's the separate, global context store). `Fail
closed` and `allow_degraded` unchanged from 0.2.0; see Open Question 8.

## 1. Purpose

This service sits between the client's system and their cloud AI assistant. Before any text
reaches the cloud model, the client's system sends the user's task/purpose and the relevant
email (subject, sender, recipients, body, and quoted thread) here first. A local open-source
model — backed by rule-based checks — identifies spans of private data in context (e.g. a
personal mobile number vs. a published support line, or a name quoted inside an email thread),
assigns each a confidence score, and replaces them with placeholders. The service also makes a
single, conservative **request-level release decision** covering the whole purpose + email +
thread — not just an aggregation of the individual span scores.

The service never calls the cloud itself and needs no outbound network access. What happens to
the redacted content afterward — sending it to the cloud model, and using its reply — is
entirely the client system's responsibility.

## 2. Design Principles

- **Fail closed.** Any error response means the content was *not* redacted. A successful (2xx)
  response whose `decision` is not `READY` carries the same consequence: the client must not
  forward it to the cloud model.
- **Confidence-based redaction, category-gated for regulated data.** Every detected span carries
  a confidence score; for standard entity types, a span is redacted once its score clears a
  threshold (low by default, so the service errs toward caution). For **regulated categories**
  (health, financial, credential/secret, confidential-business, confidential-email/thread), a
  confidence score alone never authorizes release — the request-level `decision` stays
  `LOCAL_ONLY` until the approved policy explicitly covers that category.
- **Review is asynchronous, not a blocking wait.** When a standard-category span's confidence
  falls between the auto-redact threshold and the reject threshold, the service does not pause the
  HTTP call for a human to look at it. `/v1/redactions` returns `PENDING_REVIEW` immediately — no
  content, no partial redaction — and the client polls `GET /v1/redactions/{id}` until a reviewer
  resolves it. The synchronous call stays bounded by `timeout_ms` no matter how long review takes.
- **No sensitive logging.** Input text, detected values, and restored text are never logged —
  only IDs, counts, timings, decisions, and error types.
- **Local only.** No outbound network calls; nothing leaves the machine unless the client system
  chooses to send the already-redacted content onward.

## 3. Endpoints

Auth: `Authorization: Bearer <api-key>` on every endpoint except `/healthz` and `/readyz`.
All error bodies are RFC 9457 Problem Details (`application/problem+json`) with `type`, `title`,
`status`, and `request_id`.

### POST `/v1/redactions` — detect, redact, and decide

**Purpose:** Detect private data across the user's purpose and structured email content, return
it with private spans replaced by placeholders, and return a request-level `decision`.
**Fail closed:** any non-2xx means the content was *not* processed at all; a 2xx response with
`decision` other than `READY` means it was processed but must not be released to the cloud.

**Request body** (structured email object, replaces the flat `text` field):

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
        "role": "quoted_sender",
        "source": "quoted_email",
        "text": "Our public support line is 800-555-0100."
      }
    ]
  },
  "source_context": {"sensitivity": "unverified", "access": "authorized_for_request"},
  "session_id": "optional-string",
  "mapping": {"retain": false, "ttl_seconds": 3600},
  "policy": {"overrides": {"...": "standard entity types only — see §4"}}
}
```

**Response 200:**

```json
{
  "request_id": "opaque-id",
  "decision": "READY | LOCAL_ONLY | PENDING_REVIEW",
  "decision_reason": "stable reason code, no private text",
  "redacted_email": "same shape as input email, transformed — present only if decision=READY",
  "redacted_purpose": "string — present only if decision=READY",
  "spans": [
    {
      "field": "email.body",
      "start": 0,
      "end": 0,
      "type": "PHONE_PERSONAL",
      "category": "standard | regulated:health | regulated:financial | regulated:credential | regulated:confidential_business | regulated:confidential_email",
      "action": "redact | retain",
      "confidence": 0.0,
      "detector": "string",
      "reason": "string"
    }
  ],
  "policy_version": "string",
  "model_version": "string"
}
```

`request_id` is issued for every `READY` **and** `PENDING_REVIEW` decision, even when no span
required a placeholder, so `/restore` and the status check below can reference it. On
`PENDING_REVIEW`, `spans` still lists what was detected (so the client can see *why* it's
pending) but `redacted_email`/`redacted_purpose` are absent, exactly as for `LOCAL_ONLY`.

| Code | Meaning |
|---|---|
| 200 | Request processed — see `decision` for whether content may be released |
| 400 | Malformed JSON or missing body |
| 401 | Missing or invalid API key |
| 409 | A request with the same `Idempotency-Key` is still in progress |
| 413 | Request exceeds `max_request_bytes` (provisional; see Open Question 6) |
| 415 | Body is not `application/json` |
| 422 | Valid JSON but fails a schema/business rule (e.g. `session_id` without `mapping.retain: true`, a regulated-category override attempted in `policy.overrides`, or same `Idempotency-Key` with a different body) |
| 429 | Rate limit exceeded — see `Retry-After` |
| 500 | Internal error — content was not processed |
| 503 | Local model unavailable — see Open Question 8 on `allow_degraded` |
| 504 | Model exceeded `timeout_ms` (default 15,000 ms) |

### GET `/v1/redactions/{id}` — check status / retrieve a resolved review

**Purpose:** For a request that returned `PENDING_REVIEW`, poll this endpoint to learn whether a
human reviewer has resolved it yet, and retrieve the redacted content once they have. This is the
only way a `PENDING_REVIEW` request ever produces content — the original call never blocks for
review (see Open Question 9 on whether a webhook should exist alongside polling).

**Response 200:**

```json
{
  "request_id": "opaque-id",
  "status": "PENDING_REVIEW | RESOLVED | EXPIRED",
  "decision": "READY | LOCAL_ONLY — present only if status=RESOLVED",
  "redacted_email": "present only if status=RESOLVED and decision=READY",
  "redacted_purpose": "present only if status=RESOLVED and decision=READY",
  "spans": "same shape as /v1/redactions — present only if status=RESOLVED",
  "resolved_at": "timestamp — present only if status=RESOLVED",
  "policy_version": "string",
  "model_version": "string"
}
```

An `EXPIRED` status means no reviewer acted within the record's bounded lifetime (see Open
Question 10) — the client must resubmit the original request rather than keep polling; the
`request_id` is no longer usable.

| Code | Meaning |
|---|---|
| 200 | Found — see `status` |
| 401 | Missing or invalid API key |
| 404 | No record with this `id` (including one that never reached `decision: READY` or `PENDING_REVIEW`) |
| 410 | Record was deleted (see `DELETE` below) before it resolved |

### POST `/v1/redactions/{id}/restore` — scan and restore

**Purpose:** Before touching any placeholder, scan the cloud reply for newly-introduced private
content that wasn't part of the original request. Only if that scan is clear does the service
exact-match known placeholders back to their original values.

**Request body:** `{"reply_text": "string containing placeholders"}`

**Response 200** (the call succeeded; `restore_decision` carries the business outcome):

```json
{
  "restore_decision": "RESTORED | REVIEW_BLOCKED",
  "restored_text": "present only if restore_decision=RESTORED",
  "unmatched_placeholders": ["listed, never silently dropped"],
  "reason": "present only if REVIEW_BLOCKED — e.g. new_private_content_detected, unknown_placeholder, mapping_not_retained, expired, restart_state_lost"
}
```

`REVIEW_BLOCKED` here is a synchronous, fail-closed refusal — not a queued human review. It's
named separately from the `/v1/redactions` `PENDING_REVIEW` decision on purpose: one means "a
person needs to look at this before it can go out," the other means "this specific restore call
was rejected outright and nothing further happens automatically."

If `mapping.retain` was not set on the original request, the record still exists (for scanning)
but holds no original values — the leak scan still runs, but every placeholder in the reply
comes back in `unmatched_placeholders` rather than being restored.

| Code | Meaning |
|---|---|
| 200 | Processed — see `restore_decision` |
| 400 | Malformed JSON or missing body |
| 401 | Missing or invalid API key |
| 404 | No record with this `id` (including one that never reached `decision: READY`) |
| 410 | Record existed but expired, was deleted, or was already consumed (one-time use) |
| 422 | Request fails validation |
| 500 | Internal error |

### DELETE `/v1/redactions/{id}` — delete a record

**Purpose:** Remove a request's record — mapping, restore-scan state, and any still-pending
review — before its TTL expires or before a reviewer acts on it.

| Code | Meaning |
|---|---|
| 204 | Record deleted (or was already gone) — restore and status checks now return 410 |
| 401 | Missing or invalid API key |
| 404 | No record with this `id` |

### GET `/v1/info` — service metadata

Returns service/model/policy version, default threshold (standard categories only), max input
size, entity type taxonomy, and the regulated-category groupings currently in effect.

### GET `/healthz` — liveness (no auth)

Process is running. Does **not** check the model.

### GET `/readyz` — readiness (no auth)

Model loaded, warmed up, ready to serve; 503 if not — stop sending traffic.

## 4. Key Concepts

- **Redaction result.** Each call to `/v1/redactions` returns a request-level `decision`, the
  redacted content, and a list of spans — each with its entity type, category, confidence, the
  detector that made the call, and a short reason — but never the original value.
- **Session-based label consistency, not entity lookup.** `session_id` exists to keep one mapping
  internally consistent: the same real-world entity gets the same placeholder label (e.g.
  `[PERSON_1]`) across every request in that session, so the mapping never drifts or collides
  between turns. It is unrelated to the context store below — it doesn't look anything up, it just
  keeps this session's own labels stable.
- **Global context store, separate from the session.** Independently of `session_id`, the service
  consults a standing, cross-session store of known and previously-labeled entities (e.g. a
  contact already seen as personal vs. public) to inform detection. This store holds known private
  information persistently and is shared across all callers and sessions — it is not scoped to one
  conversation.
- **Policy overrides — standard categories only.** A caller can adjust the confidence threshold,
  restrict which entity types to look for, or supply allow/deny lists, but only for **standard**
  entity types. Regulated categories (health, financial, credential/secret,
  confidential-business, confidential-email/thread) are governed entirely by the fixed
  `policy_version` and cannot be loosened per request; a request touching one of them returns
  `decision: LOCAL_ONLY` until the approved policy explicitly covers it.
- **Answer-scan record (always created).** Every `decision: READY` **or** `PENDING_REVIEW` result
  automatically creates an in-memory, request-scoped record — even when no span needed a
  placeholder — so `/restore` can later scan the cloud reply for newly-introduced private content,
  and so `GET /v1/redactions/{id}` has something to report on. The record has a bounded lifetime
  and a service-wide capacity cap; if capacity is exhausted the service returns `LOCAL_ONLY`
  rather than evicting a live record or issuing `READY`/`PENDING_REVIEW`. A process restart loses
  all records, so any restore or status check attempted afterward fails closed.
- **Mapping retention (opt-in, separate from the record above).** Setting `mapping.retain: true`
  additionally stores the placeholder-to-original mapping inside that record, so `/restore` can
  substitute real values back in. Without it, `/restore` still performs the leak scan but cannot
  restore any placeholder — all of them come back as unmatched. The record itself (used for
  scanning and for review) always exists regardless of this flag; only the reversible mapping is
  opt-in.
- **Review is asynchronous, not a blocking wait.** When a standard-category span's confidence
  falls between the auto-redact threshold and the reject threshold, `/v1/redactions` returns
  `PENDING_REVIEW` immediately — no content, no partial redaction — while a human reviewer looks
  at it out-of-band, outside this HTTP call entirely. The client must poll
  `GET /v1/redactions/{id}` (or, pending Open Question 9, receive a webhook) until `status`
  resolves to `RESOLVED`, at which point `decision` becomes `READY` (with the now-approved
  redaction) or `LOCAL_ONLY` (the reviewer declined release). This keeps `/v1/redactions` bounded
  by `timeout_ms` no matter how long a human takes.
- **Restore, in two steps.** `/restore` first scans the reply text itself for newly-introduced
  private content unrelated to any known placeholder; finding any — or hitting an
  unknown/malformed/case-changed placeholder — returns `REVIEW_BLOCKED` with no restored text.
  Only once that scan is clear does it proceed to exact-match substitution. **Known limitation:**
  restore still works against one redaction's mapping at a time — if a reply mixes placeholders
  from multiple redactions (e.g. a multi-turn session, or a summary of several documents), only
  that one redaction's placeholders come back restored; the rest are reported as unmatched, never
  silently dropped.
- **Graceful degradation (opt-in) — pending, not yet merged.** If the local model is unavailable,
  `allow_degraded: true` currently lets the caller opt into a rules-only fallback instead of an
  error. This has not been reconciled with the stricter principle proposed alongside this
  contract, under which any detector/model failure blocks release entirely with no partial
  fallback. Treat this as provisional; see Open Question 8.

## 5. Open Questions

| # | Question | Owner |
|---|---|---|
| 1 | Does the client need restore, or does their system handle it? | Client |
| 2 | Latency target per email, and expected daily volume | Client |
| 3 | Confirm fail-closed as the default behavior on errors | Client |
| 4 | Entity type taxonomy and its mapping into standard vs. regulated categories (current list is provisional) | Privacy Research |
| 5 | Default redaction threshold, calibrated on the 100-email baseline | Evaluation |
| 6 | Maximum request size and deployment target (TLS, host) | Service Eng. + Client |
| 7 | Restore scope: should a session- or batch-level restore endpoint be added to cover cloud replies that mix placeholders from more than one redaction? | Client + Service Eng. |
| 8 | Reconcile `allow_degraded` (rules-only fallback) with the fail-closed principle that treats any detector failure as blocking release — keep as opt-in, or remove entirely? | Service Eng. + Security/De-id |
| 9 | Should the client also receive a webhook/callback when a `PENDING_REVIEW` request resolves, instead of (or alongside) polling `GET /v1/redactions/{id}`? | Client + Service Eng. |
| 10 | What is the bounded lifetime for a pending human review before it expires to `EXPIRED`? Does it share the same capacity cap as the answer-scan record, or does review get its own, separate cap? | Service Eng. |
| 11 | Can a caller `DELETE` a request that is still `PENDING_REVIEW` to cancel the review outright, or should `DELETE` only be allowed once a request has resolved? | Client + Service Eng. |

## 6. Out of Scope for v0

Attachments and OCR, batch requests, streaming, and multi-language tuning.
