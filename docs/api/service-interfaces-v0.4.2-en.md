# Service Engineering: Implementation Plan and Component Interfaces (contract 0.4.2, draft)

> Historical design reference: V1/V2 implementations have been removed. For the active service contract, see [V3 API](sessions-v3-en.md).

**Status:** Draft for team review · **Owner:** Zhexuan Ye (Service Engineering) · **Based on:** API contract
0.4.1 and 0.4.2 (`redaction-api-report-en-v0.4.2.md`), the midterm slides, architecture diagrams v1, and the
development schedule. The Chinese original is `service-interfaces-v0.4.2-zh.md`; this file is the English
version, updated to match the W9 skeleton in `service/`.

## 0. Who needs to read what

| You are | Read |
|---|---|
| Owner of a component (segmentation, rules, Presidio, prompts, calibration, decision, pseudonymisation, context store) | §4 (your function signature) and `service/vg_redactor/stubs/components.py` (the "REAL VERSION MUST" notes on your function) |
| Evaluation / dashboard | §5 (pipeline), §6 (metrics, audit log) |
| Client / VG08 integration | the contract `redaction-api-report-en-v0.4.2.md`, plus §3 here for exact formats |

## 1. Decisions made on top of contract 0.4.1

| # | Question | Decision |
|---|---|---|
| 1 | Workflow diagram says `POST /redact`, contract says `POST /v1/redactions` | The contract path wins. The diagram's step 1 is shorthand. |
| 2 | `spans[].field` only showed `email.body` | Field-path syntax defined in §3.3. Offsets are relative to the **original** field text. |
| 3 | `policy.overrides` was a placeholder | Structure defined in §3.2. |
| 4 | Presidio or rule engine raises an exception | Presidio failure returns a degraded `200` with `degraded_reason: recognizer_failure`. Rule-engine failure returns `500` (there is no safe fallback below it). |
| 5 | `/restore` returned 410 after "one-time use", so a network retry lost the reply | `/restore` does **not** consume the record. It is read-only and idempotent, so retrying is safe. A record ends at its TTL or on `DELETE`; callers should `DELETE` when done. `410` means expired or deleted only. |
| 6 | Allow-list in degraded mode | Not applied (safer). Setting: `allow_list_in_degraded=false`. |
| 7 | `409` (idempotency) and `429` (rate limit) | Reserved, not implemented in 0.4.2 (P1). `/metrics` is added, on a separate local-only port. |
| 8 | `DELETE` returned 404 in one place and 204 "already gone" in another | `DELETE` is idempotent: always `204` (record exists, expired, deleted, or never existed). Matches the usual HTTP convention and does not reveal whether an id was valid. |
| 9 | `request_id` vs record id | One id (`req_<ULID>`), created on receipt, present in every response including errors. On a `200` it is also the id for `/restore` and `DELETE`. |

## 2. Code layout (what exists in `service/` today)

```
service/
  config/            policy.yaml (tiers, taxonomy, thresholds)   service.yaml (timeouts, limits, model)
  vg_redactor/
    contracts/       SHARED, read-only for component owners: types.py, errors.py, fields.py,
                     policy.py, components.py (the `Components` bundle)
    stubs/           components.py: stub versions of every teammate-owned component
    api/             FastAPI app, auth, validation, problem+json            (Service Eng.)
    pipeline/        orchestrator.py, deadline.py, degrade.py                (Service Eng.)
    model/           client.py: model adapter (budget, queue, failure classification)  (Service Eng.)
    records/         store.py: TTL, capacity, tombstones, session label state            (Service Eng.)
    obs/             metrics.py, logging.py, audit.py                                    (Service Eng.)
    settings.py  main.py
  tests/             contract, failure injection, leak, records/components
  dashboards/        (W11) Grafana provisioning JSON and prometheus.yml
```

Rule: **components depend only on `contracts/`, never on each other.** The orchestrator is the only place that
wires them together. To plug in a real component, put your function into the `Components` bundle in `main.py`
(`build_stub_components` shows the shape); nothing else changes.

## 3. HTTP API, exact formats

Auth: `Authorization: Bearer <key>` on every endpoint except `/healthz` and `/readyz`. Keys come from the
`VG_API_KEYS` environment variable (comma separated), are stored as SHA-256, and compared with
`hmac.compare_digest`. `/metrics` is not on the main port.

All errors are RFC 9457 `application/problem+json`:

```json
{
  "type": "urn:vg:problem:capacity-exhausted",
  "title": "Request-record capacity exhausted",
  "status": 503,
  "request_id": "req_01J...",
  "violations": [{"field": "policy.overrides.thresholds.high", "code": "high_tier_fixed"}]
}
```

`type` values: `malformed-json` (400), `unauthorized` (401), `not-found` (404), `gone` (410),
`payload-too-large` (413), `unsupported-media-type` (415), `validation-failed` (422, adds `violations`),
`internal` (500), `capacity-exhausted` (503, sets `Retry-After`), `deadline-exceeded` (504). `detail` and
`violations` hold only field paths and error codes, **never input values**. Check order: 401, 415, 413, 400, 422.

### 3.1 `POST /v1/redactions`

Request and response fields are in the contract. Additions in 0.4.2:

- Header `Content-Type: application/json` (otherwise 415). A caller-supplied `X-Request-ID` is ignored.
- Validation: unknown fields are rejected (`extra=forbid`), so a misspelled option is never silently ignored;
  `purpose` 1 to 2,000 characters; `email.body` required; `email.thread` at most 50 items; `session_id` matches
  `^[A-Za-z0-9_-]{1,64}$` and requires `mapping.retain=true` (422, `session_requires_retain`);
  `mapping.ttl_seconds` between 1 and `max_ttl_seconds` (default 86,400; default TTL when omitted is 3,600);
  body limited to `max_request_bytes` (default 262,144, provisional).
- Response adds: `record: {"expires_at", "mapping_retained"}`, headers `X-Request-ID` and
  `X-Degraded: true|false`, and `degraded_reason: recognizer_failure`.
  `degraded_reason` and `degraded_stage` are absent unless `degraded=true`.

### 3.2 `policy.overrides` (proposal, to be reviewed by Privacy Research)

```json
"policy": {"overrides": {
  "thresholds": {"medium": 0.6},
  "entity_types": {"exclude": ["ORG"]},
  "allow_list": ["support@example.test"],
  "deny_list": ["Project Falcon"]
}}
```

`thresholds` accepts only the `medium` key. Low and public tiers are not single-threshold rules, so they cannot
be overridden. Touching a High-tier type (a `high` threshold, excluding a High-tier type, or an `allow_list`
entry that matches a High-tier candidate) returns 422 with code `high_tier_fixed`. A `deny_list` match becomes a
High-tier candidate.

### 3.3 Field paths (`spans[].field`)

`purpose`, `email.subject`, `email.from.name`, `email.from.address`, `email.to[i].name`, `email.to[i].address`,
`email.cc[i].name`, `email.cc[i].address`, `email.body`, `email.thread[i].text`.
`start` and `end` are Unicode code point offsets into that field's **original** text, half-open `[start, end)`.
`redacted_email` has the same shape as the input. Helpers: `contracts/fields.py` (`iter_fields`, `set_field`).

### 3.4 `POST /v1/redactions/{id}/restore`

Body: `{"reply_text": "..."}` (limited to `max_request_bytes`).

1. Look up the record: 404 (never issued, or the process restarted) or 410 (expired or deleted). Deleted and
   expired ids are remembered, id only, for `max_ttl_seconds`, so 410 can be told apart from 404.
2. No mapping stored: `200` with `BLOCKED` and reason `mapping_not_retained`.
3. Otherwise `components.restore(reply_text, mapping)` decides. It finds placeholders case-insensitively
   (pattern `[A-Za-z]+_[0-9]+` in square brackets); if any is not in the mapping (exact case), the whole restore is
   `BLOCKED` with `unknown_placeholder` and the list in `unmatched_placeholders`.
4. The record is **not** consumed. The same id can be restored again until its TTL ends or it is deleted.

### 3.5 Other endpoints

- `DELETE /v1/redactions/{id}`: always `204`.
  Only an existing record creates a tombstone; restore for a never-issued id remains `404`.
  Repeated DELETE does not extend tombstone retention. DELETE drops the record's mapping,
  but session label state (keys `TYPE|<HMAC-SHA256>` under a per-process key, and counters)
  remains even when no records remain in the session, preserving labels across requests.
  The keys hold no original text.
  DELETE does not shorten the session expiry, which is extended by session requests and
  their record TTLs. The TTL sweep removes the state at or after expiry; process restart
  also loses it. Because the keys are HMACs, the state left after DELETE holds no original values.
- `GET /v1/info`: `service_version`, `contract_version`, `policy_version`, `model_version`, `prompt_versions`,
  `context_store_version`, `tiers`, `entity_types` (type and tier), `limits` (`max_request_bytes`, `timeout_ms`,
  `max_ttl_seconds`, `max_records`), `failure_behavior: "redact_all_candidates"`.
- `GET /healthz`: `{"status": "ok"}`.
- `GET /readyz`: `{"mode": "ready|degraded", "components": {"rules", "presidio", "model_detection",
  "model_assessment"}}`, each `up` or `down`.
- `GET http://127.0.0.1:9100/metrics`: Prometheus text format, separate port, local only.

## 4. Component interfaces (what teammates implement)

Shared types live in `service/vg_redactor/contracts/types.py` (read-only for component owners). Offsets are
always relative to the original field text. A function that builds a joined string internally must convert
offsets back before returning.

```python
class Segment(BaseModel):  field: str; text: str; source: Literal["purpose","header","subject","body","quoted_thread","signature"]
class Candidate(BaseModel): field: str; start: int; end: int; type: str; detectors: set[Literal["rules","presidio","model"]]; hint: str | None
class ScoredCandidate(BaseModel): candidate: Candidate; raw_score: float | None; is_private: bool | None; calibrated: float | None
class Decision(BaseModel): candidate: Candidate; tier: Tier; action: Literal["redact","retain"]; confidence: float | None; reason: str
```

Every component is a plain function with the signature below. The full "REAL VERSION MUST" checklist for each
one is in the docstring of its stub in `stubs/components.py`. **Owners are not confirmed yet** (the "Owner" column
says who it probably is).

| Function (field of `Components`) | Signature | Owner |
|---|---|---|
| `segment` | `(purpose: str, email: EmailIn) -> list[Segment]` | TBC |
| `detect_rules` | `(segments: list[Segment], ctx: ContextStore) -> list[Candidate]`. Sync, CPU-only, runs in a worker thread. An exception here means HTTP 500. | TBC |
| `detect_presidio` | `(segments: list[Segment]) -> list[Candidate]`. Sync. An exception means a degraded response. | TBC |
| `merge_candidates` | `(*lists: list[Candidate]) -> list[Candidate]`. Overlaps in one field become one span, `detectors` is the union, the higher-tier type wins. | TBC |
| `build_detection_prompt` | `(segments) -> str`. Version in `detection_prompt_version`. | TBC |
| `parse_detection` | `(raw: str, segments) -> list[Candidate]`. Raises `ModelOutputUnparseable`. | TBC |
| `build_assessment_prompt` | `(segments, candidates) -> str`. Version in `assessment_prompt_version`. | TBC |
| `parse_assessment` | `(raw: str, candidates) -> list[ScoredCandidate]`, one per input candidate, same order; unclassified ones keep `raw_score=None`. Raises `ModelOutputUnparseable`. | TBC |
| `calibrate` | `(raw: float) -> float`. Pure, monotonic, result in [0, 1]. | TBC |
| `decide` | `(scored, policy: Policy, overrides: Overrides, ctx) -> list[Decision]`. Tier x threshold on the calibrated score. Pure. | TBC |
| `decide_degraded` | `(candidates, policy) -> list[Decision]`. Redact all, `confidence=None`, `reason="degraded_redact_all"`. | TBC |
| `pseudonymize` | `(purpose: str, email: EmailIn, decisions, labels: LabelState) -> PseudonymResult`. Placeholders `[TYPE_n]`; same entity, same label within a `LabelState`. | TBC |
| `restore` | `(reply_text: str, mapping: dict[str, str]) -> RestoreOutcome`. BLOCKED if any placeholder is unknown. | TBC |
| `ContextStore` (object) | `version`, `term_list`, `allow_list`, `is_allowed(entity_type, text) -> bool`. Read-only, loaded at startup. | TBC |

`Policy` (tier table, taxonomy, thresholds) is loaded from `config/policy.yaml` by shared code
(`contracts/policy.py`); component owners use `policy.tier_of(type)` and `policy.threshold(tier, overrides)`.
The values in `policy.yaml` are provisional until reviewed (Open Questions 4 and 5).

**What Service Engineering provides:** the gateway, `ModelGateway` (the model adapter: per-call budget, queue,
failure classification, metrics), the record store, the orchestrator, and the stub components. Component owners
never call the model directly: they write prompts and parsers, and the service calls the model.

## 5. Orchestration (`pipeline/orchestrator.py`)

Order, matching the 18-step workflow diagram:

1. `segment`
2. `detect_rules`, `detect_presidio`, and model detection run **in parallel**
3. `merge_candidates`, then allow-list and override handling
4. model assessment, `calibrate`, `decide`
5. `pseudonymize`
6. create the record, write the audit log, return the response

- **Degraded path.** If a model call fails (unavailable, timeout, unparseable), or Presidio fails, the service
  uses only rule and Presidio candidates (plus the model's detection output for `recognizer_failure`), skips
  assessment and thresholds, redacts every candidate, and returns `200` with `degraded: true`.
  A rule-engine failure returns `500`.
- **Deadlines.** `timeout_ms` (default 15,000) is the end-to-end budget. Each model call may use at most
  `min(model_call_timeout_ms, remaining - degraded_reserve_ms)`, so a failed call still leaves time for the
  degraded path. If even that does not fit, the response is `504`.
- **Model concurrency.** `model_concurrency` (default 1) limits simultaneous model calls. Time spent waiting for
  a slot counts against the same budget and is reported as `vg_model_queue_wait_seconds`.
- **Capacity.** A record slot is reserved before any processing starts (full means `503`) and released if the
  request fails, so a live record is never evicted.
- **Records** (`records/store.py`): in-memory, TTL plus capacity cap (`max_records`, default 1,000), tombstones
  for 410 vs 404, per-session label state, a sweep every 10 s. A process restart loses everything. Run **one
  worker only**.

## 6. Observability

Metrics (`obs/metrics.py`) use only small fixed label sets; no label ever holds text or ids.

| Metric | Type | Labels |
|---|---|---|
| `vg_http_requests_total` | counter | route, method, status |
| `vg_pipeline_duration_seconds` | histogram | route, mode = normal / degraded / error (orchestrator only, excludes HTTP handling) |
| `vg_http_duration_seconds` | histogram | route, method, status, mode (through final response body send) |
| `vg_stage_duration_seconds` | histogram | stage (validate, segment, detect_rules, detect_presidio, detect_model, merge, assess_model, calibrate, decide, pseudonymize, audit) |
| `vg_model_calls_total` | counter | prompt, outcome = ok / unavailable / timeout / unparseable |
| `vg_model_call_duration_seconds`, `vg_model_queue_wait_seconds` | histogram | prompt |
| `vg_degraded_total` | counter | reason, stage |
| `vg_spans_total` | counter | tier, action, mode |
| `vg_records_active`, `vg_records_capacity` | gauge | none |
| `vg_records_removed_total` | counter | reason = expired / deleted |
| `vg_inflight_requests` | gauge | none |
| `vg_service_mode` | gauge | mode = ready / degraded / down |
| `vg_build_info` | gauge (=1) | service, contract, policy, model, prompt_detection, prompt_assessment, context_store |

The eight P0 dashboard panels map to these: request rate and status codes, availability
(2xx / (2xx + 5xx)), end-to-end latency split by mode, per-stage time, degraded rate and reasons, model-call
outcomes per prompt, record count and capacity, service mode and versions.

**Logs.** JSON, with an allowlist of keys; any other key is dropped, so a stray `text=` cannot leak input.
**Audit log.** One JSON line per request (category, tier, action, calibrated score, detectors, timings, versions).
Raw model scores appear only here. Original text, detected values, restored text and the mapping are never
logged anywhere.

## 7. Tests

`cd service && python -m pytest` (37 tests today):

- **Contract:** every status code, field and rule above; 422 never echoes input; restore round trip and retry;
  DELETE idempotency; session label consistency.
- **Failure injection:** model down / timeout / garbage output on each of the two prompts, a hanging model,
  Presidio failure, rule-engine failure, capacity exhausted, end-to-end timeout, record expiry, `/readyz` in
  degraded mode.
- **Leak:** canary strings sent through normal, degraded and error paths must not appear in logs, the audit
  log, `/metrics` or any error body.

After swapping in a real component these tests must still pass. Component-level tests with the labelled
emails (offset round trips, empty input, Unicode, overlaps) are the next addition.

## 8. Stack notes (Python + FastAPI)

| Limitation | Effect | Handling |
|---|---|---|
| Records live in process memory | No multi-worker deployment (records would not be shared and restore would fail randomly) | Single process. The local model is the bottleneck anyway. |
| Rules and Presidio are CPU-bound synchronous code | Threads share the GIL; a timed-out thread cannot be killed | Bounded worker threads; load tests measure the impact; move to a process pool only if needed |
| Presidio / spaCy cold start | Slow startup | Warm up at startup; `/readyz` reports readiness |
| "No outbound network" | pip packages and model files cannot be downloaded in the sandbox | Pre-package wheels and models for offline install |
| Python strings cannot be wiped | Original values may linger in memory after a record is deleted | Drop references on delete; never write to disk; we do not claim memory zeroisation |

## 9. Schedule

| Week | Delivery |
|---|---|
| W9 (10/19 to 10/25) | Gateway, records, model adapter, stubs and tests (skeleton done); orchestration first half |
| W10 (10/26 to 11/1) | Real components wired in (entry condition: components delivered by 10/30), failure injection, first latency numbers |
| W11 (11/2 to 11/8) | Dashboard (8 panels), load test, set `timeout_ms` and `degraded_reserve_ms` from data |
| W12 (11/9 to 11/15) | Leak checks, hardening, contract freeze |
| W13 (11/16 to 11/22) | README, API docs, demo script; soft freeze 11/18, hard freeze 11/22 |

## 10. Still to confirm with the team

1. **Component owners** for every row of the §4 table (not confirmed yet).
2. The `policy.overrides` structure in §3.2, with Privacy Research.
3. Placeholder behavior for the public support line: the stub redacts it as a personal phone number; the real
   decision step must keep it (the "two phone numbers, two outcomes" example in the midterm slides).
