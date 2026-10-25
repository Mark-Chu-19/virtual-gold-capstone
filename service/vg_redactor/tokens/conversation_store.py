"""Atomic conversation creation and compare-and-swap updates; only wrapped keys are stored."""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Protocol


class ConversationStore(Protocol):
    shared: bool

    async def ensure(self, tenant: str, group: str, scope: str, value: str, retain_until: int) -> str: ...
    async def find(self, tenant: str, group: str) -> str | None: ...
    async def get(self, tenant: str, scope: str) -> str | None: ...
    async def swap(self, tenant: str, scope: str, expected: str, value: str,
                   retain_until: int) -> bool: ...


class MemoryConversationStore:
    """Development adapter. Shared only by callers using this exact store object."""
    shared = False

    def __init__(self):
        self._lock = threading.Lock()
        self._indices: dict[tuple[str, str], tuple[str, int]] = {}
        self._records: dict[tuple[str, str], tuple[str, int]] = {}

    def _get(self, tenant, scope):
        entry = self._records.get((tenant, scope))
        return entry[0] if entry and entry[1] > time.time() else None

    async def ensure(self, tenant, group, scope, value, retain_until):
        with self._lock:
            index = self._indices.get((tenant, group))
            if index and index[1] > time.time():
                result = self._get(tenant, index[0])
                if result is None:
                    raise RuntimeError('Conversation index has no key record')
                return result
            self._indices[tenant, group] = scope, retain_until
            self._records[tenant, scope] = value, retain_until
            return value

    async def find(self, tenant, group):
        with self._lock:
            index = self._indices.get((tenant, group))
            if not index or index[1] <= time.time():
                return None
            value = self._get(tenant, index[0])
            if value is None:
                raise RuntimeError('Conversation index has no key record')
            return value

    async def get(self, tenant, scope):
        with self._lock:
            return self._get(tenant, scope)

    async def swap(self, tenant, scope, expected, value, retain_until):
        with self._lock:
            if self._get(tenant, scope) != expected:
                return False
            self._records[tenant, scope] = value, retain_until
            return True


class RedisConversationStore:
    """Tenant-tagged keys keep the index/record creation in one Redis hash slot."""
    shared = True
    _ENSURE = """
    local scope = redis.call('GET', KEYS[1])
    if scope then
        local value = redis.call('GET', ARGV[4] .. scope)
        if not value then return redis.error_reply('Conversation record missing') end
        return value
    end
    redis.call('SET', KEYS[2], ARGV[2], 'EXAT', ARGV[3])
    redis.call('SET', KEYS[1], ARGV[1], 'EXAT', ARGV[3])
    return ARGV[2]
    """
    _SWAP = """
    if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
    redis.call('SET', KEYS[1], ARGV[2], 'EXAT', ARGV[3])
    return 1
    """

    def __init__(self, client):
        self.client = client

    @staticmethod
    def _prefix(tenant):
        return 'vg:conversation:{' + hashlib.sha256(tenant.encode()).hexdigest() + '}:'

    def _index(self, tenant, group):
        return self._prefix(tenant) + 'index:' + hashlib.sha256(group.encode()).hexdigest()

    async def ensure(self, tenant, group, scope, value, retain_until):
        prefix = self._prefix(tenant) + 'key:'
        return await self.client.eval(self._ENSURE, 2, self._index(tenant, group), prefix + scope,
                                      scope, value, retain_until, prefix)

    async def find(self, tenant, group):
        scope = await self.client.get(self._index(tenant, group))
        if scope is None:
            return None
        value = await self.get(tenant, scope)
        if value is None:
            raise RuntimeError('Conversation index has no key record')
        return value

    async def get(self, tenant, scope):
        return await self.client.get(self._prefix(tenant) + 'key:' + scope)

    async def swap(self, tenant, scope, expected, value, retain_until):
        return bool(await self.client.eval(self._SWAP, 1, self._prefix(tenant) + 'key:' + scope,
                                            expected, value, retain_until))
