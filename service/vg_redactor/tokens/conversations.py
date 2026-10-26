"""Conversation Key Manager: random per-conversation secrets wrapped by the configured KEK.

Secrets are never cached across requests. HKDF separates SIV and reference-signing keys.
Opaque conversation handles and DEK versions are independent of wrapping-key rotation.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from dataclasses import dataclass, field

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..contracts.errors import ProblemError
from .conversation_store import ConversationStore
from .wire import Principal, b64, packed, unb64


class UnavailableConversation(ValueError):
    """Unknown, expired, closed, or unauthorized. Never expose which in restore responses."""


@dataclass(frozen=True)
class ConversationKey:
    scope: str
    version: str
    tenant_id: str
    group_id: str = field(repr=False)
    expires_at: int
    seed: bytes = field(repr=False)

    def derive(self, usage: str, length: int) -> bytes:
        return HKDF(algorithm=hashes.SHA256(), length=length, salt=None,
                    info=packed('vg-conversation-v2', usage, self.tenant_id,
                                self.scope, self.version)).derive(self.seed)


def serialize(record):
    return json.dumps(record, sort_keys=True, separators=(',', ':'))


class ConversationKeyManager:
    def __init__(self, keys: dict[str, bytes], active_key_id: str, store: ConversationStore,
                 *, max_lifetime_seconds=86400, tombstone_seconds=86400, clock=time.time):
        self.keys, self.active_key_id, self.store = keys, active_key_id, store
        self.max_lifetime = max_lifetime_seconds
        self.tombstone_seconds = tombstone_seconds
        self.clock = clock

    @staticmethod
    def _aad(tenant, record):
        return packed('vg-wrapped-conversation', 1, tenant, record['scope'], record['version'],
                      record['created_at'], record['max_expires_at'], record['kek_id'])

    def _candidate(self, principal, group, ttl, *, closed=False):
        now = int(self.clock())
        record = {'scope': secrets.token_hex(16), 'version': '1', 'created_at': now,
                  'max_expires_at': now + self.max_lifetime,
                  'expires_at': now + min(ttl, self.max_lifetime),
                  'status': 'closed' if closed else 'active',
                  'kek_id': None, 'wrapped_key': None}
        if not closed:
            record['kek_id'] = self.active_key_id
            secret = packed(group, b64(secrets.token_bytes(32)))
            record['wrapped_key'] = b64(AESSIV(self.keys[self.active_key_id]).encrypt(
                secret, [self._aad(principal.tenant_id, record)]))
        return record

    def _retain_until(self, record):
        return record['max_expires_at'] + self.tombstone_seconds

    async def _io(self, method, *args):
        try:
            return await method(*args)
        except Exception:
            raise ProblemError(503, 'conversation-store-unavailable',
                               'Conversation key storage unavailable') from None

    @staticmethod
    def _record(raw):
        try:
            record = json.loads(raw)
            if (not isinstance(record, dict)
                    or not re.fullmatch(r'[a-f0-9]{32}', record['scope'])
                    or not re.fullmatch(r'[1-9][0-9]{0,8}', record['version'])
                    or record['status'] not in {'active', 'closed', 'expired'}
                    or not all(type(record[k]) is int for k in
                               ('created_at', 'expires_at', 'max_expires_at'))
                    or not record['created_at'] < record['expires_at'] <= record['max_expires_at']
                    or 'kek_id' not in record or 'wrapped_key' not in record):
                raise ValueError('Invalid conversation key record')
            return record
        except (ValueError, KeyError, TypeError):
            raise ProblemError(503, 'conversation-key-unavailable', 'Invalid conversation key record') from None

    def _active(self, record):
        if (record['status'] != 'active' or record['expires_at'] <= self.clock()
                or record['max_expires_at'] <= self.clock()):
            raise UnavailableConversation()

    def _unwrap(self, principal, record):
        try:
            original = AESSIV(self.keys[record['kek_id']]).decrypt(
                unb64(record['wrapped_key']), [self._aad(principal.tenant_id, record)])
            group, seed = json.loads(original)
            seed = unb64(seed)
            if not isinstance(group, str) or len(seed) != 32:
                raise ValueError('Invalid wrapped conversation key')
        except Exception:
            raise ProblemError(503, 'conversation-key-unavailable',
                               'Conversation key could not be unwrapped') from None
        if '*' not in principal.groups and group not in principal.groups:
            raise UnavailableConversation()
        return group, seed

    async def _open(self, principal, raw, *, ttl=None):
        for _ in range(16):
            if raw is None:
                raise UnavailableConversation()
            record = self._record(raw)
            if (record['status'] == 'active' and (record['expires_at'] <= self.clock()
                    or record['max_expires_at'] <= self.clock())):
                expired = {**record, 'status': 'expired', 'wrapped_key': None, 'kek_id': None}
                if not await self._io(self.store.swap, principal.tenant_id, record['scope'], raw,
                                      serialize(expired), self._retain_until(expired)):
                    raw = await self._io(self.store.get, principal.tenant_id, record['scope'])
                    continue
                raise UnavailableConversation()
            self._active(record)
            group, seed = self._unwrap(principal, record)
            updated = dict(record)
            if ttl is not None:
                updated['expires_at'] = min(record['max_expires_at'],
                    max(record['expires_at'], int(self.clock()) + ttl))
            if record['kek_id'] != self.active_key_id:
                updated['kek_id'] = self.active_key_id
                updated['wrapped_key'] = b64(AESSIV(self.keys[self.active_key_id]).encrypt(
                    packed(group, b64(seed)), [self._aad(principal.tenant_id, updated)]))
            if updated == record or await self._io(self.store.swap, principal.tenant_id,
                    record['scope'], raw, serialize(updated), self._retain_until(updated)):
                return ConversationKey(record['scope'], record['version'], principal.tenant_id,
                                       group, updated['expires_at'], seed)
            raw = await self._io(self.store.get, principal.tenant_id, record['scope'])
        raise ProblemError(503, 'conversation-busy', 'Conversation key update contention')

    async def get_or_create(self, principal: Principal, group: str, ttl: int) -> ConversationKey:
        if '*' not in principal.groups and group not in principal.groups:
            raise ProblemError(403, 'group-forbidden', 'Group access denied')
        # Read first to avoid generating and wrapping a losing random key on every request.
        raw = await self._io(self.store.find, principal.tenant_id, group)
        if raw is None:
            candidate = self._candidate(principal, group, ttl)
            raw = await self._io(self.store.ensure, principal.tenant_id, group, candidate['scope'],
                                 serialize(candidate), self._retain_until(candidate))
        return await self._open_group(principal, group, raw, ttl=ttl)

    async def check_available(self, principal, group, ttl):
        """Renew an existing active group, but defer creation until token issuance."""
        if '*' not in principal.groups and group not in principal.groups:
            raise ProblemError(403, 'group-forbidden', 'Group access denied')
        raw = await self._io(self.store.find, principal.tenant_id, group)
        if raw is not None:
            return await self._open_group(principal, group, raw, ttl=ttl)
        return None

    async def _open_group(self, principal, group, raw, *, ttl=None):
        try:
            key = await self._open(principal, raw, ttl=ttl)
            if key.group_id != group:
                raise ProblemError(503, 'conversation-key-unavailable', 'Conversation index mismatch')
            return key
        except UnavailableConversation:
            raise ProblemError(410, 'conversation-unavailable',
                               'Conversation is expired or closed; use a new group_id') from None

    async def load(self, principal: Principal, scope: str, version: str, *, ttl=None) -> ConversationKey:
        raw = await self._io(self.store.get, principal.tenant_id, scope)
        key = await self._open(principal, raw, ttl=ttl)
        if key.version != version or key.scope != scope:
            raise UnavailableConversation()
        return key

    async def rewrap(self, principal, group):
        """Maintenance entry point: rewrap one active group without extending its lifetime."""
        if '*' not in principal.groups and group not in principal.groups:
            raise ProblemError(403, 'group-forbidden', 'Group access denied')
        raw = await self._io(self.store.find, principal.tenant_id, group)
        key = await self._open(principal, raw)
        if key.group_id != group:
            raise ProblemError(503, 'conversation-key-unavailable', 'Conversation index mismatch')

    async def scope_for_group(self, principal, group):
        raw = await self._io(self.store.find, principal.tenant_id, group)
        return self._record(raw)['scope'] if raw else None

    async def close(self, principal, group):
        if '*' not in principal.groups and group not in principal.groups:
            raise ProblemError(403, 'group-forbidden', 'Group access denied')
        candidate = self._candidate(principal, group, 1, closed=True)
        raw = await self._io(self.store.ensure, principal.tenant_id, group, candidate['scope'],
                             serialize(candidate), self._retain_until(candidate))
        for _ in range(16):
            record = self._record(raw)
            if record['status'] == 'closed':
                return record['scope']
            updated = {**record, 'status': 'closed', 'wrapped_key': None, 'kek_id': None}
            if await self._io(self.store.swap, principal.tenant_id, record['scope'], raw,
                              serialize(updated), self._retain_until(updated)):
                return record['scope']
            raw = await self._io(self.store.get, principal.tenant_id, record['scope'])
            if raw is None:
                raise ProblemError(503, 'conversation-key-unavailable', 'Conversation key record missing')
        raise ProblemError(503, 'conversation-busy', 'Conversation key update contention')
