# Virtual Gold API contract — customer integration guide

**API:** V3 · **Service:** 3.0.0 · **Reviewed:** October 29, 2026

**Implementation baseline:** `main`, commit `1e805ab3714643a03029216469683f5751ceb3d8`

[OpenAPI 3.1 contract](openapi-v3.yaml)

This contract describes the implemented HTTP interface for redacting an email, using its
protected text in a downstream task, and restoring supported placeholders in the result.
The OpenAPI file can be imported into compatible API tools. Examples use fictional data.

## 1. Connection and authentication

Obtain the integration **base URL** and **API key** from the service operator. No hosted
customer URL or service availability SLA is defined by this repository. The local development
URL is `http://127.0.0.1:8080`; use an operator-provided HTTPS endpoint for a non-local integration.

For every `/v3/` operation, send:

```http
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

`Content-Type` is required on operations with JSON request bodies, including DELETE.
Success bodies use `application/json`; application errors use `application/problem+json`.
`X-Request-ID` is a per-call response header for support diagnostics. It is not a session ID.
No `X-Degraded` response header is provided; read the `degraded` response field.

The API key determines the tenant. Restore and delete must use a key assigned to the tenant
that created the session. A different key works only if the operator has configured the same
tenant for both keys. There is no client-selected tenant, group or user permission field.
Knowing a session ID alone does not authorize access.

## 2. Complete a task

1. Send the task purpose and original email to **POST `/v3/redaction`**.
2. Associate the returned `session_id` with that specific redacted result. Optionally store
   `expires_at` to manage expiry. Use `redacted_purpose` and the relevant `redacted_email` fields
   for the downstream task. Preserve every placeholder exactly, including capitalization.
3. Send the downstream result and the same `session_id` to **POST `/v3/restore`** before expiry.
   Consume `restored_text` only on HTTP 200.
4. Call **DELETE `/v3/redaction`** when no further restoration is needed.

One `session_id` identifies **one independent redaction**, not a multi-turn conversation.
Keep the session/result association in your own application; never combine placeholders from
different redactions. Identical labels can refer to different values in different sessions,
and the service cannot detect that mix-up.

| Method | Path | Authentication | Success |
|---|---|---|---|
| POST | `/v3/redaction` | Bearer key | 200, redacted result and session |
| POST | `/v3/restore` | Bearer key | 200, restored text |
| DELETE | `/v3/redaction` | Bearer key | 204, no body |
| GET | `/v3/info` | Bearer key | 200, configuration and limits |
| GET | `/healthz` | Public | 200, liveness |
| GET | `/readyz` | Public | 200, readiness body |

## 3. Redact an email

### Request

```http
POST /v3/redaction
```

```json
{
  "purpose": "Draft a reply",
  "email": {
    "body": "Call 202-555-0102."
  }
}
```

| Field | Required | Type and constraint |
|---|---|---|
| `purpose` | Yes | String, 1–2,000 Unicode characters; describes the requested task |
| `email` | Yes | Email object below |
| `policy` | No | Object; defaults to no request overrides |
| `email.body` | Yes | String; empty is accepted; subject to the whole-request byte limit |
| `email.subject` | No | String or null |
| `email.from` | No | Address object or null |
| `email.to`, `email.cc` | No | Arrays of address objects; default `[]` |
| `email.thread` | No | Array of thread items, at most 50; default `[]` |

An **address object** has required `address` (string, 1–320 characters) and optional `name`
(string or null). `address` is a text field; the server does not enforce RFC email-address syntax.
Use `from` as the JSON field name.

A **thread item** has required `text` (string), optional `message_id` (string or null), and
optional `source`, whose only accepted value is `"quoted_thread"` and which defaults to that value.
The service processes `purpose`, subject, names, addresses, body and `thread[].text`.
`message_id` is passed through as metadata; keep it free of sensitive content.

Unknown JSON fields are rejected at every request-model level. Do not submit `session_id`,
`request_id`, `mapping`, `tokenization`, `group_id`, `source_context`, `purpose_source`,
backend selection or a client TTL. Attachments, binary uploads and OCR have no request field.
Unicode text is accepted; supported detection quality depends on the deployed components and
the agreed input language. Do not infer multilingual coverage from JSON support.

### Optional policy overrides

For normal integration, omit `policy` and use the configured policy. Advanced clients may send:

```json
{
  "policy": {
    "overrides": {
      "thresholds": {"medium": 0.5},
      "entity_types": {"exclude": []},
      "allow_list": [],
      "deny_list": []
    }
  }
}
```

This fragment belongs inside the full redaction request. Only the `medium` threshold can be
overridden, from 0 through 1. Only `exclude` is accepted under `entity_types`; high-tier types
cannot be excluded. Allow-listing text that matches a high-tier candidate returns 422.
Lists contain exact text terms; use non-empty terms. Allow lists are normally not applied in
degraded processing. Get the current entity types and tiers from `/v3/info`.
An accepted override can change what remains visible; agree any relaxation with the operator.

### Response — HTTP 200

```json
{
  "session_id": "sid_01M60000000000000000000000",
  "redacted_email": {
    "body": "Call [PHONE_1].",
    "to": [],
    "cc": [],
    "thread": []
  },
  "redacted_purpose": "Draft a reply",
  "expires_at": "2026-10-29T17:00:00+00:00",
  "degraded": false
}
```

This is illustrative output, not a guaranteed detection result for every deployment.
The response has **five** top-level fields:

| Field | Meaning |
|---|---|
| `session_id` | Server-issued opaque `sid_<ULID>` reference; retain it with this result |
| `redacted_email` | Email structure with processed text; null optional fields are omitted and default arrays are included |
| `redacted_purpose` | Processed task purpose; use this instead of forwarding the original purpose |
| `expires_at` | UTC date-time in ISO 8601 / RFC 3339 form; do not send it back on restore |
| `degraded` | Whether conservative fallback processing was used |

`degraded: true` is still a successful, restorable result. The fallback redacts candidates
available from functioning detectors. It does not prove that all sensitive content was found;
your application should follow its agreed review/release policy. `degraded: false` also does
not constitute authorization to send content to a cloud service. No release/routing decision
is returned by this API.

Every successful redaction allocates a fresh session, even for identical input or an empty
mapping. V3 implements no `Idempotency-Key` behavior. Do not rely on that header to deduplicate
calls. Retention is mandatory and its duration is selected by the server.

## 4. Restore the downstream result

```http
POST /v3/restore
```

```json
{
  "session_id": "sid_01M60000000000000000000000",
  "text": "Please call [PHONE_1]."
}
```

Both fields are required strings. `session_id` must match
`^sid_[0-7][0-9A-HJKMNP-TV-Z]{25}$`; pass back the received ID unchanged. `text` may be empty
or contain no placeholders, but the session must still be valid and authorized.

HTTP 200:

```json
{"restored_text": "Please call 202-555-0102."}
```

Restoration replaces recognized labels such as `[PHONE_1]` using exact, case-sensitive
matching. An unknown recognized label causes 422 `unknown-placeholder`; no partial restored
text is returned. Text that does not match the placeholder grammar is left as text: a
misspelled or omitted placeholder is not reliably detectable. The server never guesses a label
or inserts an entity that the downstream system omitted. Replacement is one pass.

The restored value is the value saved in the session mapping. Within a redaction, aliases
of a header person's name may share a placeholder and restore to the full name; normalized
variants may share a mapping too. Byte-for-byte reconstruction of every original variant is
not promised. Original literal placeholders are preserved, and generated labels avoid their
reserved numbers. Never edit placeholder spelling or use a different session to resolve one.

Restoration is repeatable: it does not consume the session, renew its TTL or require the
original request, `expires_at`, backend choice or an `X-Request-ID`.

## 5. Delete restoration data

```http
DELETE /v3/redaction
Content-Type: application/json
```

```json
{"session_id": "sid_01M60000000000000000000000"}
```

Success is **204 No Content**; do not attempt to parse JSON from that response. The session
reference is in the body, not a URL parameter. Confirm that your HTTP library and gateway
forward DELETE bodies; the curl example below sends the required JSON body explicitly.

Deletion is idempotent: an unknown, expired or already deleted ID also returns 204. A known
live record or tombstone belonging to another tenant returns 404. Restores starting after
deletion fail; an already authorized restore holding a snapshot may still complete. Deletion
does not remove plaintext already returned to your application.

## 6. Limits and session lifetime

Discover actual deployment values with authenticated **GET `/v3/info`**. The shipped defaults are:

| Setting / response field | Default | Client impact |
|---|---|---|
| `limits.max_request_bytes` | 262,144 bytes (256 KiB) | Entire encoded JSON body, not just text; applies to all body-bearing calls |
| `limits.max_restored_bytes` | 1,048,576 bytes (1 MiB) | Expanded UTF-8 text, including repeated placeholders and ordinary text |
| `limits.timeout_ms` | 15,000 ms | Redaction/restoration processing budget; not a network latency SLA |
| `restoration.default_ttl_seconds` | 3,600 seconds | Fixed lifetime from record commit, after processing; restore does not extend it |
| `limits.max_ttl_seconds` | 86,400 seconds | Server retention cap; not a client-selectable TTL |
| `limits.max_records` | 1,000 | Shared capacity for stored sessions and in-progress reservations |

Expiry is fixed; a new redaction creates a different session rather than extending an existing
one. Expired/deleted authorized sessions normally return 410 on restore. After their metadata
is cleaned up, the same lookup returns 404. Unknown and foreign sessions also return 404.

**Current deployment constraint:** sessions are process-local and not durable. A service
restart loses all sessions, including when the internal AES backend is enabled. The current
service requires one worker; arbitrary routing across independent replicas is unsupported.
Arrange a deployment change with the operator before relying on restart recovery or replicas.
Backend configuration cannot be selected by clients and does not change the visible interface.

`/v3/info` also reports `service_version`, `contract_version`, component versions, `tiers`,
`entity_types`, `failure_behavior`, restoration metadata and `supported_contracts: ["v3"]`.
`GET /healthz` returns `{"status":"ok"}`. `GET /readyz` returns `mode` and component states;
both `ready` and `degraded` normally use HTTP 200, so inspect the body.

## 7. Errors and retry behavior

Application errors follow [RFC 9457 problem details](https://www.rfc-editor.org/rfc/rfc9457.html).
Branch on HTTP status and `type`, not the human-readable `title`. Example:

```json
{
  "type": "urn:vg:problem:validation-failed",
  "title": "Request failed validation",
  "status": 422,
  "violations": [{"field": "purpose", "code": "missing"}]
}
```

Required problem members are `type`, `title`, `status`; optional members include `detail` and
`violations` (`field` and `code`). There is no session ID or request ID in the error body;
read `X-Request-ID` from the response header for support. All types below use `urn:vg:problem:`.

| HTTP | Type suffix | Client action |
|---|---|---|
| 400 | `malformed-json` | Correct JSON/body; do not retry unchanged |
| 401 | `unauthorized` | Obtain or correct the Bearer key |
| 404 | `session-not-found` | Verify session/result pairing and tenant; a restart may have removed the record |
| 410 | `session-gone` | Restoration data is no longer available; retrying the same ID will not recover it |
| 413 | `payload-too-large` | Reduce encoded request size |
| 413 | `restored-text-too-large` | Reduce expanded output, including repeated labels; smaller restores can still use the session |
| 415 | `unsupported-media-type` | Send `Content-Type: application/json` |
| 422 | `validation-failed` | Fix fields/policy/Unicode using `violations`; unknown fields use `extra_forbidden` |
| 422 | `unknown-placeholder` | Correct the label or use the matching session; do not display partial restoration |
| 503 | `capacity-exhausted` | Wait for `Retry-After` (currently 5 seconds); release unneeded sessions |
| 503 | `session-id-unavailable`, `session-store-unavailable` | Retry with bounded backoff; contact the operator if persistent |
| 503 | `session-key-unavailable`, `session-payload-unavailable` | Ask the operator to restore key/payload availability; changing session IDs is not a repair |
| 504 | `deadline-exceeded` | Retry cautiously; report the request ID if persistent |
| 500 | `internal` | Retry cautiously; contact the operator with the request ID |

Recognized API validation errors reject unpaired Unicode surrogate escapes with 422 and
violation code `invalid_unicode`. Inputs are not included in problem descriptions; field paths
are included. Unknown paths or unsupported HTTP methods may use framework/gateway error
formats instead of problem JSON. Defensively handle non-JSON transport/proxy errors too.

Repeated restore and delete calls are safe with respect to session consumption. A retry of
POST `/v3/redaction` creates a new session. If a connection is lost after the server succeeds,
the client may not receive its session ID, and that record can remain until expiry. Use bounded
backoff for transient failures; there is no idempotency or session-discovery endpoint to resolve
an ambiguous redaction outcome. Client timeouts should allow the configured server budget
plus network overhead. The API declares no built-in rate-limit or 429 response contract.

## 8. Integration example

Use the following curl calls to redact, restore and delete a synthetic result. These calls
make no cloud-model request. Inspect the redaction result before proceeding: if `degraded`
is true, apply your agreed review policy. Copy the returned session ID and preserve the
actual returned placeholder spelling; the restore example assumes the illustrated `[PHONE_1]`.

```bash
export VG_BASE_URL='http://127.0.0.1:8080'  # development; replace for integration
export VG_API_KEY='<operator-issued-key>'

curl --fail-with-body --silent --show-error "$VG_BASE_URL/v3/redaction" \
  -H "Authorization: Bearer $VG_API_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"purpose":"Draft a reply","email":{"body":"Call 202-555-0102."}}'

# After reviewing the response, copy its session_id here.
export VG_SESSION_ID='<session_id returned by redaction>'

curl --fail-with-body --silent --show-error "$VG_BASE_URL/v3/restore" \
  -H "Authorization: Bearer $VG_API_KEY" \
  -H 'Content-Type: application/json' \
  --data "{\"session_id\":\"$VG_SESSION_ID\",\"text\":\"Please call [PHONE_1].\"}"

# Run when no further restoration is needed; success is 204 with no body.
curl --fail-with-body --silent --show-error -X DELETE "$VG_BASE_URL/v3/redaction" \
  -H "Authorization: Bearer $VG_API_KEY" \
  -H 'Content-Type: application/json' \
  --data "{\"session_id\":\"$VG_SESSION_ID\"}"
```

The base URL here is the service root; do not append `/v3` yourself. Keep credentials out of
source code and public logs. The operator must separately confirm the target deployment's
detection configuration, input-language coverage and release policy: the repository still
contains stub model prompts/parsers, and interface tests do not establish detection quality.

## 9. Version and compatibility

Only V3 is currently registered. V1/V2 token, conversation-key, Redis and idempotency documents
describe retired development interfaces and must not be used for customer integration.
This contract documents the reviewed implementation, not a promise of unimplemented endpoints,
shared storage, per-user permissions or automatic cloud routing. Confirm incompatible changes
and deployment-specific limits with the operator before upgrading clients.

The machine-readable contract uses [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0).
Use the checked-in `openapi-v3.yaml` for customer tooling: the framework-generated
`/openapi.json` currently omits the manually parsed request bodies, Bearer authentication
and application problem-response definitions. This documentation does not change that runtime route.
