"""In-memory request records: TTL, capacity cap, tombstones, per-session label state.

V1 retention is opt-in; V3 always retains a backend payload and binds it to a tenant.
Separate store instances isolate the contracts. Process restart loses all records.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from ..contracts.errors import CapacityExhausted, RecordGone, RecordNotFound
from ..contracts.types import LabelState


@dataclass
class Record:
    id: str
    created_at: float
    expires_at: float          # monotonic-clock seconds
    expires_at_iso: str
    mapping: dict[str, str] | None
    session_id: str | None
    tenant_id: str | None = None
    backend: str = "mapping"
    backend_version: int = 1

    @property
    def mapping_retained(self) -> bool:
        return self.mapping is not None


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
        self._tombstones: dict[str, tuple[float, str | None]] = {}  # removed time, tenant
        self._sessions: dict[str, tuple[LabelState, float]] = {}

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

    def commit(self, rid: str, mapping: dict[str, str] | None, ttl_seconds: int,
               session_id: str | None, *, tenant_id: str | None = None,
               backend: str = "mapping", backend_version: int = 1) -> Record:
        ttl = min(ttl_seconds, self.max_ttl)
        now = self._clock()
        rec = Record(id=rid, created_at=now, expires_at=now + ttl,
                     expires_at_iso=(datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat(),
                     mapping=mapping, session_id=session_id, tenant_id=tenant_id,
                     backend=backend, backend_version=backend_version)
        with self._lock:
            self._reserved.discard(rid)
            self._records[rid] = rec
            if session_id and session_id in self._sessions:
                st, exp = self._sessions[session_id]
                self._sessions[session_id] = (st, max(exp, rec.expires_at))
        return rec

    # -- lookup / delete -----------------------------------------------------------------------
    def get(self, rid: str, *, tenant_id: str | None = None) -> Record:
        with self._lock:
            self._sweep_locked()
            rec = self._records.get(rid)
            if rec:
                if tenant_id is not None and rec.tenant_id != tenant_id:
                    raise RecordNotFound()
                return rec
            if rid in self._tombstones:
                if tenant_id is not None and self._tombstones[rid][1] != tenant_id:
                    raise RecordNotFound()
                raise RecordGone()
            raise RecordNotFound()

    def delete(self, rid: str, *, tenant_id: str | None = None) -> bool:
        """Idempotent. Returns True if a live record was removed."""
        with self._lock:
            self._sweep_locked()
            rec = self._records.get(rid)
            owner = rec.tenant_id if rec else self._tombstones.get(rid, (0, None))[1]
            if tenant_id is not None and owner is not None and owner != tenant_id:
                raise RecordNotFound()
            return self._remove_locked(rid, "deleted")

    # -- sessions ------------------------------------------------------------------------------
    def label_state(self, session_id: str, ttl_seconds: int) -> LabelState:
        with self._lock:
            now = self._clock()
            st, exp = self._sessions.get(session_id, (LabelState(), 0.0))
            self._sessions[session_id] = (st, max(exp, now + min(ttl_seconds, self.max_ttl)))
            return st

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
        for sid in [s for s, (_, exp) in self._sessions.items() if exp <= now]:
            del self._sessions[sid]
        return len(expired)
