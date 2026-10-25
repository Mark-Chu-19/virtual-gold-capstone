"""Atomic group mapping storage; values are encrypted before reaching this boundary."""
from __future__ import annotations

import threading
import time
from typing import Protocol

from redis.asyncio import Redis


class MappingStore(Protocol):
    shared: bool

    async def put(self, group: str, values: dict[str, str], expires_at: int) -> None: ...
    async def get(self, group: str, references: list[str]) -> list[str | None]: ...
    async def delete(self, groups: list[str]) -> None: ...
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...


class MemoryMappingStore:
    """Explicit development/test adapter. Not suitable for multiple workers."""
    shared = False

    def __init__(self):
        self._lock = threading.Lock()
        self._groups: dict[str, tuple[dict[str, str], int]] = {}

    async def put(self, group, values, expires_at):
        with self._lock:
            current, expiry = self._groups.get(group, ({}, 0))
            if expiry <= time.time():
                current = {}
            self._groups[group] = ({**current, **values}, max(expiry, expires_at))

    async def get(self, group, references):
        with self._lock:
            values, expiry = self._groups.get(group, ({}, 0))
            return [values.get(ref) if expiry > time.time() else None for ref in references]

    async def delete(self, groups):
        with self._lock:
            for group in groups:
                self._groups.pop(group, None)

    async def ping(self):
        return True

    async def close(self):
        pass


class RedisMappingStore:
    """One Redis hash per tenant/key/group; Lua atomically writes and extends expiry.

    Redis must be private and configured with persistence for restart durability. Hash-tagged
    keys make each group operation compatible with Redis Cluster. No raw text is stored.
    """
    shared = True
    _PUT = """
    local old_expiry = redis.call('EXPIRETIME', KEYS[1])
    local expiry = math.max(tonumber(ARGV[1]), old_expiry)
    for i = 2, #ARGV, 2 do
        redis.call('HSET', KEYS[1], ARGV[i], ARGV[i+1])
    end
    redis.call('EXPIREAT', KEYS[1], expiry)
    return 1
    """

    def __init__(self, url: str, *, client=None):
        self.client = client or Redis.from_url(url, decode_responses=True,
                                               socket_connect_timeout=2, socket_timeout=2)

    @staticmethod
    def _key(group):
        return 'vg:tokens:{' + group + '}'

    async def put(self, group, values, expires_at):
        if values:
            args = [expires_at]
            for ref, value in values.items():
                args.extend((ref, value))
            await self.client.eval(self._PUT, 1, self._key(group), *args)

    async def get(self, group, references):
        return await self.client.hmget(self._key(group), references) if references else []

    async def delete(self, groups):
        # Each command touches one hash slot; no cross-slot transaction is required.
        async with self.client.pipeline(transaction=False) as pipe:
            for group in groups:
                pipe.delete(self._key(group))
            await pipe.execute()

    async def ping(self):
        return bool(await self.client.ping())

    async def close(self):
        await self.client.aclose()


class IdempotencyCache:
    """Optional shared request leases and encrypted results, using the mapping store adapter."""
    _CLAIM = """
    local existing = redis.call('GET', KEYS[1])
    if existing then return existing end
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
    return ''
    """
    _SWAP = """
    if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
    if ARGV[2] == '' then
        redis.call('DEL', KEYS[1])
    else
        redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
    end
    return 1
    """

    def __init__(self, store):
        self.store = store
        self._lock = threading.Lock()
        self._values = {}

    async def claim(self, key, pending, ttl):
        if isinstance(self.store, RedisMappingStore):
            return await self.store.client.eval(self._CLAIM, 1, 'vg:idem:' + key, pending, ttl)
        with self._lock:
            value, expiry = self._values.get(key, ('', 0))
            if expiry > time.time():
                return value
            self._values[key] = pending, time.time() + ttl
            return ''

    async def swap(self, key, pending, value, ttl):
        if isinstance(self.store, RedisMappingStore):
            return bool(await self.store.client.eval(self._SWAP, 1, 'vg:idem:' + key,
                                                     pending, value, ttl))
        with self._lock:
            current, expiry = self._values.get(key, ('', 0))
            if current != pending or expiry <= time.time():
                return False
            if value:
                self._values[key] = value, time.time() + ttl
            else:
                self._values.pop(key, None)
            return True
