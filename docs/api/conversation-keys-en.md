# Conversation Key Manager

V2 now issues format-2 tokens using independent random conversation secrets. Redaction and
restoration request bodies are unchanged. `group_id` identifies the conversation within the
API key's tenant; provide the existing business conversation ID. Omitting it still uses
`default`, so omitted IDs share one conversation within that tenant.

## Keys and storage

- First use generates a random 256-bit conversation secret and a random opaque handle.
- `VG_TOKEN_KEYS` is now also the wrapping-key (KEK) ring. Its 64-byte AES-SIV keys wrap the
  conversation secret and business group identifier. No plaintext DEK is persisted.
- HKDF-SHA256 derives separate AES-256-SIV token, mapping, reference-HMAC and idempotency keys.
- Shared Redis stores the encrypted key records, group index, lifecycle and optional mappings.
  Atomic creation picks one winner across replicas; CAS updates prevent TTL/rotation/close races.
- Plaintext conversation secrets are request-local; there is no cross-request key cache.
  Memory storage is development-only. Independent replicas must share Redis and configuration.
- Both backends require key records, including AES-SIV without mapping or idempotency. Redis
  failure returns 503; no worker-local fallback key is created. Persist Redis and back it up.

New tokens contain a random handle and DEK version, not the wrapping key ID or expiry:

```text
[VG:2:s:PHONE_PERSONAL:<conversation-handle>:1:<ciphertext>]
[VG:2:m:PHONE_PERSONAL:<conversation-handle>:1:<reference>.<signature>]
```

Tenant, handle, DEK version, mode and entity type are cryptographically bound. AAD is fixed,
so the exact same value and type in one conversation produce the same token across requests.
Different conversations have independent random secrets. Full tokens remain self-routing:
restoration needs only `text` and authentication, not a group ID or redaction ID.
Mapping still uses AES-SIV for encrypted storage; AES-GCM and very short placeholders are
separate future work. There is no automatic alias learning or active-conversation DEK rotation.

## Lifetime

`tokenization.ttl_seconds` now extends the conversation's idle deadline. A shorter request cannot
shorten it. Extension is bounded by the fixed maximum lifetime from initial creation:

```yaml
tokenization:
  conversation_max_lifetime_seconds: 86400
  conversation_tombstone_seconds: 86400
```

For a new group, creation is deferred until detection and assessment finish and token issuance
starts, so model processing does not consume the first idle TTL. Existing active groups are
renewed before processing, including their mapping retention. Closed or expired groups still
fail before processing. Mapping publication reconciles concurrent extensions before returning.

The response's `expires_at` is a snapshot of that shared deadline and may be extended later.
It applies to the conversation, not to immutable individual tokens. AES-SIV activity also
extends existing mapping retention so mixed-backend conversations remain recoverable.
Replicas must use synchronized clocks. The maximum lifetime is not reset by activity.

Expired or closed conversations reject new redaction with 410; restoration returns HTTP 200
with `BLOCKED`. Use a new business group ID to start another conversation. No expired key is
silently regenerated. On observing expiry, the manager clears its wrapped secret with CAS.
Closed/expired metadata is retained until creation + maximum lifetime + tombstone duration;
Redis TTL then removes it. Do not reuse old business conversation IDs after metadata is purged.
The development adapter enforces expiry on access rather than providing background erasure.

## Close versus delete mappings

```http
DELETE /v2/groups/{group_id}           # close conversation, 204; authenticated and idempotent
DELETE /v2/groups/{group_id}/mappings  # remove mappings only, 204; existing behavior
```

Closing removes the wrapped secret and clears Mapping data. It blocks both format-2 backends
and new redactions, including retries that would otherwise replay a cached response. Closing
an unused ID creates a tombstone. A partially failed cleanup can be retried; closure remains
in effect even if the later mapping deletion fails. Already returned plaintext and in-flight
operations that loaded a key before closure cannot be recalled.

New idempotency results are encrypted under a conversation-derived key. Replay reloads the key
and revalidates embedded tokens, including tokens from other conversations. Close logically
invalidates cached responses; encrypted cache blobs are physically removed at their TTL.
Deleting mappings alone leaves AES-SIV and the conversation key available. A cached result
containing a deleted mapping is rejected with 409 rather than returning revoked tokens.

## Rotation and compatibility

Distribute a keyring containing old and new KEKs to every replica first, then change the active
KEK consistently. Access lazily rewraps active conversation records using CAS. The secret, DEK
version, token strings and original expiry remain unchanged. An internal maintenance method,
`ConversationKeyManager.rewrap(principal, group)`, rewraps a known active group without extending
its TTL. Retire old KEKs only after all relevant records have been migrated and old-format
objects no longer need them. Mixed deployments must retain both KEKs until rollout completes.

Format-1 `[VG:1:...]` tokens retain their original KEK/expiry behavior and restore alongside
format-2 tokens. They cannot retroactively gain independent conversation keys. Existing v1
record-based APIs are also unchanged. Group mapping deletion covers old mappings; conversation
closure cannot revoke old stateless format-1 AES-SIV ciphertext. Retain the old KEK through
its token lifetime or handle legacy retirement explicitly. Old idempotency caches remain readable.

Expiry/closure are service-side controls, not erasure of backups or ciphertext already copied
with its key. This release provides no single-token revocation or live KMS integration.

## Verification

Run `python -m pytest tests -q` from `service/`. Tests cover distributed creation races, independent
keys, stable tokens, idle/hard expiry, closure versus refresh, cache bypass, wrapping corruption,
KEK rotation, restart recovery, storage failure, and frozen legacy vectors. Redis tests use a
Lua-capable simulator; production persistence/failover and real-model token preservation remain
separate deployment/evaluation checks. The existing HTML briefing and notebooks are unchanged.
