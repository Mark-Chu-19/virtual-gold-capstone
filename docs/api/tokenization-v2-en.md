# V2 reversible token API

V2 adds Mapping and AES-SIV backends to the existing detect/assess/decide pipeline. V1
(`/v1/redactions`, record-based restore/delete) remains compatible and process-local.
V2 restoration takes the message and authentication only: no redaction ID or mode is needed.

New tokens now use Conversation Key Manager and wire format 2. Request bodies are unchanged;
see [conversation key lifecycle and migration](conversation-keys-en.md).

## Start and configure

From `service/`, install `pip install -e '.[dev]'`. Python `cryptography` provides AES-SIV;
configured wrapping keys (KEKs) are 64 bytes for AES-256-SIV. The service creates independent
random conversation secrets and stores only their wrapped representation. No cryptographic primitives are implemented locally.
Generate a persistent development keyring once, keep it in your secret manager/environment,
and reuse it across replicas and restarts:

```bash
export VG_API_KEYS='agent-a-secret,agent-b-secret'
export VG_TOKEN_KEYS="$(python -c 'import base64,json,secrets; print(json.dumps({"k1":base64.b64encode(secrets.token_bytes(64)).decode()}))')"
export VG_ACTIVE_TOKEN_KEY_ID=k1
```

Do not generate a fresh key on every restart: that makes old tokens unrecoverable. Never
commit keys, API credentials, original customer text or experiment outputs to Git.
V2 returns 503 until keys are configured; v1 can still run without them. Invalid configured
keys fail startup. This is AES-SIV (RFC 5297), not AES-GCM-SIV.

Each unconfigured API key gets its own isolated tenant (its SHA256 digest). To let distinct
agent keys collaborate, supply `VG_API_IDENTITIES` JSON keyed by the SHA256 digest of each
accepted API key:

```json
{
  "<sha256-of-agent-a-key>": {"tenant_id": "customer-a", "groups": ["workflow1"]},
  "<sha256-of-agent-b-key>": {"tenant_id": "customer-a", "groups": ["workflow1"]}
}
```

Only keys in `VG_API_KEYS` authenticate. Identity configuration does not add credentials.
`groups: ["*"]` authorizes every group in that tenant; explicit lists restrict group access.
Authorization is checked on redaction, restoration and group mapping deletion. Tokens never
supply the trusted tenant identity. Avoid reassigning an existing tenant ID to another customer.

The default mapping store is memory for development/tests only. For independent processes,
hosts, restart durability and cross-instance idempotency, use private Redis >= 7:

```bash
docker compose -f infra/compose.yaml up -d
export VG_TOKEN_STORE=redis
export VG_REDIS_URL=redis://127.0.0.1:6379/0
VG_COMPONENTS=stub python -m vg_redactor.main
```

The included Redis compose file enables AOF and `noeviction` on a loopback port with a named
volume. Production requires private networking, authentication/TLS, capacity management and
backups appropriate to the deployment. Failover durability depends on Redis configuration;
this API does not claim synchronous replication guarantees. Mapping writes and expiry extension
are atomic per group; existing mappings are not evicted by the application.

Replicas use the same Redis, keyring, identity configuration and policy. Configure `VG_HOST`,
`VG_PORT`, `VG_METRICS_PORT` for each instance (defaults `127.0.0.1`, 8080, 9100). Only v2 is
safe for arbitrary replica routing; v1 record routes still require their original process.
`/readyz` reports mapping store failure as degraded and reports unconfigured tokenization.

## Redact

```http
POST /v2/redactions
Authorization: Bearer <agent-key>
Idempotency-Key: workflow1-message1
Content-Type: application/json

{
  "purpose": "Draft a short reply",
  "email": {"body": "Call 202-555-0102"},
  "group_id": "workflow1",
  "tokenization": {"mode": "aes_siv", "ttl_seconds": 3600},
  "include": ["service_info"]
}
```

- `tokenization.mode`: `mapping` or `aes_siv`; absent uses `tokenization.default_mode` in
  `config/service.yaml` (initially mapping). There is no silent fallback between backends.
- `group_id`: existing conversation/workflow/task identifier, `[A-Za-z0-9_-]{1,64}`;
  defaults to `default`, scoped to the authenticated tenant. Integration code should supply
  the natural business ID, not require users to maintain a new redaction ID list.
- TTL: 1 through `max_ttl_seconds`; otherwise the configured default (capped at the maximum).
- `policy` and email field structure are shared with v1. V2 does not accept v1 `mapping`,
  `session_id` or ignored `source_context` fields. Unknown fields fail validation. Protected
  addresses may expand to 4,096 characters; purpose may expand to 32,768 characters while
  retaining the 2,000-character limit on its non-token text. Plain addresses remain capped at 320.
- `include: ["service_info"]` optionally inlines `/v1/info`; the independent info route remains.
- Optional `Idempotency-Key`: 1–128 letters, digits, hyphens or underscores. Same tenant/key
  and input returns the same tokens, expiry and outcome, with a new tracing request ID and
  `Idempotency-Replayed: true`. Different input returns 409. An in-progress duplicate returns
  409 with `Retry-After: 1`; retry the same key. Failed requests release their bounded lease.
  Redis is required for cross-instance leases/results. Cached response bodies are encrypted.
  Both modes require the shared conversation key store; AES-SIV still needs no original-value mapping.

The response includes `redacted_email`, `redacted_purpose`, `spans`, normal/degraded metadata,
versions, a tracing `request_id`, and:

```json
{"tokenization":{"mode":"aes_siv","expires_at":1800000000,"format_version":2,"mapping_retained":false}}
```

`expires_at` is the conversation expiry snapshot in Unix seconds. Activity may extend it up to
the configured hard lifetime; it is not a per-token immutable deadline. V2 creates no v1 record
and does not reserve its `max_records` capacity. Span offsets remain Unicode code-point offsets
into the original request fields, even when input already contains protected tokens.

## Token format and exact restoration

```text
[VG:2:m:PHONE_PERSONAL:<random-conversation-handle>:1:<reference>.<signature>]
[VG:2:s:PHONE_PERSONAL:<random-conversation-handle>:1:<base64url-siv-ciphertext>]
```

Format, backend, entity type, conversation handle, DEK version and trusted tenant are
cryptographically bound. The handle is random, not the raw conversation identifier. Master
key IDs and expiry are kept in the conversation record instead of the token. Equal values
within a fixed context reveal equality; AES-SIV also reveals plaintext byte length. These are
pseudonymization, not anonymization. The model never receives keys or plaintext mappings.

Mapping references use exact original text and are stable within tenant/conversation/type/DEK.
Values are AES-SIV encrypted before Redis receives them. A single group write publishes all
of a request's mappings before a successful response. A shorter subsequent TTL does not shorten
older mappings' retention. An AES-SIV request also extends existing mapping retention. The conversation expiry and
status are checked during restoration.

AES-SIV encrypts exact UTF-8 bytes under the conversation-derived key. Fixed associated data
binds format, mode, entity type, tenant, conversation and DEK version, so repeated requests with
the same value/type retain identical tokens even when the conversation TTL is extended. Neither
backend normalizes case or expands names: `Dana`, `DANA` and `Dana Whitfield` restore exactly.
Cross-request alias learning/entity resolution is not provided by encryption.

Token strings are longer than v1's `[PHONE_1]`; compare actual model token counts rather than
assuming mapping is always shorter than AES-SIV. No truncation or fuzzy ciphertext repair is used.

```http
POST /v2/restorations
Authorization: Bearer <agent-key>
Content-Type: application/json

{"text":"Call [VG:2:...]"}
```

Success: `restore_decision: RESTORED`, `restored_text`, empty `unmatched_placeholders`.
Failure: `restore_decision: BLOCKED`, `reason: invalid_or_unavailable_token`, and unmatched
candidates, with no partial plaintext. Unknown, malformed, tampered, expired, deleted and
unauthorized tokens share this outcome. Storage failure is 503. Token-free text is returned
unchanged. Unsupported old `[PHONE_1]` tokens are blocked by v2; use the v1 record-based route
for them. Restoration is one pass, so decrypted strings resembling tokens are never recursively
interpreted. Repeated restoration does not consume mappings.

When re-redacting a mixed message, valid existing tokens from either backend are authorized and
masked length-preservingly before all detectors/model prompts. Only new sensitive spans receive
new tokens. Unavailable input tokens cause 422; a detected span crossing an existing token also
causes 422 rather than corrupting it. `[VG...]` is a reserved token namespace.

## Deletion, rotation and failure boundaries

`DELETE /v2/groups/{group_id}/mappings` is authenticated and idempotent (204); it removes that
group's Mapping data across all configured key IDs. This explicitly does NOT revoke AES-SIV
tokens or already returned plaintext. Concurrent new redaction after deletion can create new
mappings; use the conversation-close endpoint to stop new writes for that conversation.
Cached idempotency responses are revalidated before replay; revoked embedded tokens cause 409.
Use a new key for a new workflow operation. `DELETE /v2/groups/{group_id}` additionally closes the
conversation and removes its wrapped secret. New format-2 tokens from both backends are then
blocked, and new redactions (including cached retries) return 410. See the lifecycle document.

Neither backend currently exposes single-token revocation. Stateless AES-SIV cannot implement
individual immediate revocation without additional state. Expiry is checked by the service,
not cryptographic erasure: someone holding an old key can decrypt retained ciphertext offline.
Wrapping-key rotation lazily rewraps active conversation secrets without changing tokens. Retain
old KEKs until every relevant record has been rewrapped. Legacy format-1 tokens/caches may still
require old keys; do not remove them just because the default mode was changed.

Storage failure returns 503 before a successful token response. New AES-SIV tokens also require
conversation key storage, so Redis outage prevents their generation/restoration. A crashed writer may leave encrypted mappings until TTL; no successful
response is issued before commit. Optional idempotency leases expire after the request deadline
plus a grace period; they are not an exactly-once guarantee across arbitrary process pauses.
Audit logs record the backend and decision metadata, never original values/tokens/keys.
Metrics add `vg_token_redactions_total{backend,mode}` and `vg_token_restorations_total{decision}`.

## Verification and model experiment

```bash
python -m pytest tests -q
VG_EVAL_API_KEY='<agent-key>' python scripts/evaluate_tokens.py \
  --model llama3:8b --hops 3 --output /tmp/token-evaluation.jsonl
```

The model experiment uses bundled synthetic messages and a local Ollama endpoint. Both backends
receive the same copy/reply tasks at temperature zero, including successive handoffs. Output
records contain model name/config, preservation counts,
unexpected tokens, exact-copy status, restore result, model token counts and latency. Review
reply quality and entity-reference correctness manually; successful decryption alone does not
prove the model retained every required entity. These are reproducible evaluation tools, not a
claim that AES-SIV model quality has already passed validation. Existing notebooks are independent.
