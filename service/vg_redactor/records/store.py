"""Tenant-bound in-memory V3 records: capacity reservations, TTL and tombstones.

Records always retain a restoration payload. Restarting the process loses all records.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Callable

from ..contracts.errors import CapacityExhausted, RecordGone, RecordNotFound


@dataclass
class Record:
    session_id: str
    created_at: float
    expires_at: float          # monotonic-clock seconds
    expires_at_iso: str
    mapping: dict[str, str] | None
    tenant_id: str
    backend: str = "mapping"
    backend_version: int = 1


class RecordStore:
    def __init__(self, max_records: int, max_ttl_seconds: int,
                 clock: Callable[[], float] = time.monotonic,
                 on_remove: Callable[[str], None] | None = None):
        self.max_records, self.max_ttl = max_records, max_ttl_seconds
        self._clock = clock
        self._on_remove = on_remove or (lambda reason: None)
        self._lock = threading.Lock()
        self._records: dict[str, Record] = {}
        self._reserved: set[str] = set()
        self._tombstones: dict[str, tuple[float, str]] = {}  # removed time, tenant

    # -- capacity ------------------------------------------------------------------------------
    def reserve(self, rid: str) -> bool:
        """Atomically claim a new ID; False on collision, 503 when capacity is full."""
        with self._lock:
            self._sweep_locked()
            if rid in self._records or rid in self._reserved or rid in self._tombstones:
                return False
            if len(self._records) + len(self._reserved) >= self.max_records:
                raise CapacityExhausted()
            self._reserved.add(rid)
            return True

    def release(self, rid: str) -> None:
        with self._lock:
            self._reserved.discard(rid)

    def commit(self, rid: str, mapping: dict[str, str], ttl_seconds: int,
               *, tenant_id: str,
               backend: str = "mapping", backend_version: int = 1) -> Record:
        ttl = min(ttl_seconds, self.max_ttl)
        now = self._clock()
        rec = Record(session_id=rid, created_at=now, expires_at=now + ttl,
                     expires_at_iso=(datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat(),
                     mapping=mapping, tenant_id=tenant_id,
                     backend=backend, backend_version=backend_version)
        with self._lock:
            self._reserved.discard(rid)
            self._records[rid] = rec
        return rec

    # -- lookup / delete -----------------------------------------------------------------------
    def get(self, rid: str, *, tenant_id: str, snapshot: bool = False) -> Record:
        """Authorize atomically; snapshots retain the immutable payload for in-flight restores."""
        with self._lock:
            self._sweep_locked()
            rec = self._records.get(rid)
            if rec:
                if rec.tenant_id != tenant_id:
                    raise RecordNotFound()
                return replace(rec) if snapshot else rec
            if rid in self._tombstones:
                if self._tombstones[rid][1] != tenant_id:
                    raise RecordNotFound()
                raise RecordGone()
            raise RecordNotFound()

    def delete(self, rid: str, *, tenant_id: str) -> bool:
        """Idempotent. Returns True if a live record was removed."""
        with self._lock:
            self._sweep_locked()
            rec = self._records.get(rid)
            owner = rec.tenant_id if rec else self._tombstones.get(rid, (0, None))[1]
            if owner is not None and owner != tenant_id:
                raise RecordNotFound()
            return self._remove_locked(rid, "deleted")

    # -- housekeeping --------------------------------------------------------------------------
    def sweep(self) -> int:
        with self._lock:
            return self._sweep_locked()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"active": len(self._records), "reserved": len(self._reserved),
                    "capacity": self.max_records}

    def _remove_locked(self, rid: str, reason: str) -> bool:
        rec = self._records.pop(rid, None)
        if rec is not None:
            self._tombstones[rid] = (self._clock(), rec.tenant_id)
            rec.mapping = None  # drop the reference to original values
            self._on_remove(reason)
        return rec is not None

    def _sweep_locked(self) -> int:
        now = self._clock()
        expired = [r for r, rec in self._records.items() if rec.expires_at <= now]
        for rid in expired:
            self._remove_locked(rid, "expired")
        for rid in [r for r, (t, _) in self._tombstones.items() if now - t > self.max_ttl]:
            del self._tombstones[rid]
        return len(expired)
