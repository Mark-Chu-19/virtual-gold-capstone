# V3 redaction and restoration API

For customer integration, use the [customer contract and curl examples](customer-contract-v3-en.md)
and [OpenAPI specification](openapi-v3.yaml).
This page provides implementation and deployment details.

V3 is the first customer-facing contract. V1/V2 routes and their dedicated implementations
have been removed. A server-issued `session_id` identifies one redaction and its restoration
payload; it does not represent a multi-turn conversation. Each redaction starts fresh label state.

## Authentication and client state

All endpoints except `/healthz` and `/readyz` require `Authorization: Bearer <API_KEY>`.
Accepted keys come from `VG_API_KEYS`. Without an identity mapping, each key's SHA256 digest
defines its isolated tenant. `VG_API_IDENTITIES` maps accepted key digests to `{tenant_id}`
when multiple keys should share a tenant. Knowing a session ID alone never authorizes access.
There are no additional per-user/group permissions.

Clients only need to retain `session_id`. They do not need to return `expires_at` or retain
`X-Request-ID`, which is a per-call diagnostic header, not a restoration handle.

## POST `/v3/redaction`

```json
{
  "purpose": "Draft a reply",
  "email": {"body": "Call 202-555-0102."}
}
```

`purpose` (1–2,000 characters) and `email.body` are required. Email also supports subject,
from, to, cc and quoted thread items. Optional `policy.overrides` keeps the existing policy
constraints: high-tier protection cannot be relaxed. Unknown fields are rejected with 422.
Client session/request IDs, context, mapping retention and backend-selection fields are not accepted.

Success, HTTP 200, has exactly these five top-level fields:

```json
{
  "session_id": "sid_01M60000000000000000000000",
  "redacted_email": {"body": "Call [PHONE_1].", "to": [], "cc": [], "thread": []},
  "redacted_purpose": "Draft a reply",
  "expires_at": "2026-10-28T16:00:00+00:00",
  "degraded": false
}
```

IDs are `sid_<ULID>`, independent of input text. Storage reserves IDs atomically, retries
collisions up to eight times and never replaces an existing result. Repeated independent
redactions produce different IDs; V3 has no idempotency cache. Empty mappings also get records.
Retention is mandatory; TTL uses `default_ttl_seconds`, capped by `max_ttl_seconds`.
`degraded=true` reports conservative fallback processing, which remains restorable.
Spans, detailed fallback reasons, versions, mappings and backend details stay out of this response.

## POST `/v3/restore`

```json
{
  "session_id": "sid_01M60000000000000000000000",
  "text": "Please call [PHONE_1]."
}
```

Success, HTTP 200:

```json
{"restored_text": "Please call 202-555-0102."}
```

Restoration exact-matches placeholders and is all-or-nothing. Unknown placeholders cause 422
without partial plaintext. Labels already present literally in the original purpose/email are
identity-mapped and restored unchanged; new generated labels skip their numbers (including case
variants). Thus an original `[PHONE_1]` cannot accidentally become a newly detected phone number.
Calls do not consume records or extend TTL. Do not mix placeholders
from different redactions: short labels do not encode provenance, so equal labels from another
record cannot be identified as foreign.

Before replacement, the server counts the expanded UTF-8 text bytes, including repeated labels
and literal text. `max_restored_bytes` defaults to 1,048,576 bytes (1 MiB). Exceeding it returns
413 `restored-text-too-large` before allocating the expanded string; no partial output is returned.
The session remains usable for smaller restores. `/v3/info` includes this limit.

## DELETE `/v3/redaction`

Like restore, the session reference is in the JSON body:

```json
{"session_id": "sid_01M60000000000000000000000"}
```

Success is 204 with no body. Repeated deletion and deletion of unknown IDs also return 204.
Existing records/tombstones owned by another tenant return 404. An already authorized in-flight
restore may finish using its payload snapshot; restores starting after deletion return 410.

## Errors

Errors use `application/problem+json` with `type`, `title` and `status`. Validation errors
also include `violations` containing field paths and codes, never input values. Request IDs
are only returned in `X-Request-ID`. Every problem type starts with `urn:vg:problem:`.

| Condition | HTTP | Type suffix |
|---|---|---|
| Missing/invalid API key | 401 | unauthorized |
| Unsupported content type | 415 | unsupported-media-type |
| Malformed JSON | 400 | malformed-json |
| Oversized payload | 413 | payload-too-large |
| Expanded restored text exceeds its byte limit | 413 | restored-text-too-large |
| Invalid/missing parameters, invalid Unicode, unknown fields or invalid policy | 422 | validation-failed |
| Unknown placeholder | 422 | unknown-placeholder |
| Missing or foreign session | 404 | session-not-found |
| Authorized session expired/deleted | 410 | session-gone |
| Capacity exhausted | 503 | capacity-exhausted, with Retry-After |
| ID allocation retries exhausted | 503 | session-id-unavailable |
| Record write failure | 503 | session-store-unavailable |
| Encryption key unavailable | 503 | session-key-unavailable |
| Invalid payload/unsupported backend version | 503 | session-payload-unavailable |
| Redaction/restoration deadline exceeded | 504 | deadline-exceeded |
| Other internal failure | 500 | internal |

Tombstones retain removal time and tenant only, not plaintext, for `max_ttl_seconds` after
removal. Once cleared, lookups return 404. Foreign tenants never receive 410. Failed redactions
do not return a session ID, and reservations or committed records are cleaned up, including
response-serialization failure. Unpaired surrogate escapes in JSON strings or keys are rejected
with 422 `validation-failed`, violation code `invalid_unicode`, before records are reserved.

Placeholder rendering, encryption, audit I/O and JSON response encoding run in worker threads.
The request deadline covers preparation and serialization; explicit deadline checks guard record
commit and successful responses. Timed-out preparation may finish in its worker, but cannot
publish a record. `session_created` logs include both session_id and the per-call request ID;
input text and mapping values remain excluded by the log allowlist.

## Information, health and readiness

- `GET /v3/info`: authenticated; service/contract and component versions, tiers, entity types,
  limits, failure behavior, restoration backend/store/default TTL, and `supported_contracts: ["v3"]`.
- `GET /healthz`: public; `{"status":"ok"}`.
- `GET /readyz`: public; `{mode, components}` reporting model, session store and restoration status.

The service version is `3.0.0`, contract `v3`. Retired V1/V2 paths return 404 to authenticated calls.

## Internal backends and deployment

`v3.backend` defaults to `mapping`, storing the original placeholder-to-text dictionary.
It cannot be overridden by requests. `aes_siv` instead encrypts the entire mapping, preserving
the same short placeholders; it still requires a stored payload and is not stateless.

AES uses `VG_SESSION_KEYS`, a JSON object of key IDs to standard-base64-encoded 64-byte keys.
`v3.active_key_id` defaults to `k1`, overridden by `VG_ACTIVE_SESSION_KEY_ID`. Configured keys
are validated at startup, and AES cannot start without a keyring. Never commit keys.
Each mapping uses a purpose-specific derived key, authenticated against tenant, session ID,
key ID and format version. Each record stores its backend/version; encrypted payloads also
store key ID. Restoration uses the record's backend, not the current default. Keep old keys
until their records expire. Enabling AES or exposing client choice is a later deployment decision.

Records use a single in-memory store with `max_records` capacity. Run one worker; restarting
loses records and old IDs return 404, including in AES mode. Redis, conversation keys and token
idempotency configuration are no longer used. Multi-instance operation needs a future shared-store adapter.
