"""Optional Idempotency-Key support. Cached response bodies are encrypted at rest."""
from __future__ import annotations

import hashlib
import json
import re

from cryptography.hazmat.primitives.ciphers.aead import AESSIV

from ..contracts.errors import ProblemError
from .store import IdempotencyCache
from .wire import b64, unb64, packed


class Idempotency:
    def __init__(self, tokens):
        self.tokens = tokens
        self.cache = IdempotencyCache(tokens.store)

    async def begin(self, key, principal, request, mode, owner, lease):
        if key is None:
            return None, None
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', key):
            raise ProblemError(422, 'invalid-idempotency-key', 'Invalid Idempotency-Key')
        cache_key = hashlib.sha256(packed(principal.tenant_id, key)).hexdigest()
        # Recheck group permission and token configuration before this method is called.
        fingerprint = hashlib.sha256(packed(request.model_dump(mode='json'), mode)).hexdigest()
        pending = json.dumps({'fingerprint': fingerprint, 'owner': owner}, sort_keys=True)
        try:
            existing = await self.cache.claim(cache_key, pending, lease)
            if not existing:
                return (cache_key, pending), None
            item = json.loads(existing)
            if item['fingerprint'] != fingerprint:
                raise ProblemError(409, 'idempotency-conflict', 'Idempotency-Key has different input')
            if 'body' not in item:
                raise ProblemError(409, 'request-in-progress', 'Request is already in progress',
                                   headers={'Retry-After': '1'})
            body = AESSIV(self.tokens.keys[item['kid']]).decrypt(
                unb64(item['body']), [packed('vg-idempotency', cache_key, fingerprint)])
            result = json.loads(body)
            if result['tokenization']['expires_at'] <= self.tokens.clock():
                raise ProblemError(409, 'idempotency-expired', 'Cached tokens have expired')
            return None, result
        except ProblemError:
            raise
        except Exception:
            raise ProblemError(503, 'idempotency-unavailable', 'Idempotency storage unavailable') from None

    async def finish(self, ticket, body, ttl):
        if ticket is None:
            return
        key, pending = ticket
        item = json.loads(pending)
        kid = self.tokens.active_key_id
        encrypted = AESSIV(self.tokens.keys[kid]).encrypt(
            json.dumps(body, separators=(',', ':')).encode(),
            [packed('vg-idempotency', key, item['fingerprint'])])
        value = json.dumps({'fingerprint': item['fingerprint'], 'kid': kid, 'body': b64(encrypted)})
        try:
            if not await self.cache.swap(key, pending, value, ttl):
                raise RuntimeError('Lease lost')
        except Exception:
            raise ProblemError(503, 'idempotency-unavailable', 'Idempotency result was not committed') from None

    async def abandon(self, ticket):
        if ticket is not None:
            try:
                await self.cache.swap(*ticket, '', 1)
            except Exception:
                pass  # The bounded lease expires; never replace the original processing error.
