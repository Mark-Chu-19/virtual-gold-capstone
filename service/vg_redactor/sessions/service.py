"""Tenant-bound V3 records using the shared pipeline, record store and exact-match restore.

`session_id` identifies one redaction, not a conversation. Backend/version is recorded
per result so changing deployment defaults cannot change how older results restore.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag

from ..contracts.components import Components
from ..contracts.errors import ProblemError, RecordGone, RecordNotFound
from ..contracts.placeholders import PLACEHOLDER_RE
from ..contracts.types import LabelState, RedactionRequestV3
from ..pipeline.deadline import Deadline
from ..records.store import Record, RecordStore
from ..auth import Principal
from .backends import RestorationBackend
from .identifiers import SessionIdGenerator


class SessionService:
    def __init__(self, records: RecordStore, components: Components,
                 ids: SessionIdGenerator, backends: dict[str, RestorationBackend],
                 backend: str, ttl_seconds: int, max_restored_bytes: int = 1048576):
        self.records, self.components, self.ids = records, components, ids
        self.backends, self.backend, self.ttl_seconds = backends, backend, ttl_seconds
        self.max_restored_bytes = max_restored_bytes

    def begin(self, req: RedactionRequestV3, principal: Principal):
        # Bound retries avoid an infinite loop if an injected generator is broken.
        for _ in range(8):
            sid = self.ids.new_id()
            if self.records.reserve(sid):
                return SessionContext(self, req, principal, sid, self.backend)
        raise ProblemError(503, "session-id-unavailable", "Could not allocate a session identifier")

    def _get(self, sid, principal):
        try:
            return self.records.get(sid, tenant_id=principal.tenant_id, snapshot=True)
        except RecordNotFound:
            raise ProblemError(404, "session-not-found", "Session not found") from None
        except RecordGone:
            raise ProblemError(410, "session-gone", "Session expired or was deleted") from None

    def restore(self, sid: str, text: str, principal: Principal) -> str:
        record = self._get(sid, principal)
        # Keep one snapshot if an in-flight restore overlaps a deletion on another thread.
        payload = record.mapping
        if payload is None or record.backend_version != 1 or record.backend not in self.backends:
            raise ProblemError(503, "session-payload-unavailable", "Session payload unavailable")
        try:
            mapping = self.backends[record.backend].decode(payload, principal.tenant_id, sid)
        except (InvalidTag, ValueError, KeyError, TypeError):
            raise ProblemError(503, "session-payload-unavailable", "Session payload unavailable") from None
        self._check_restored_size(text, mapping)
        result = self.components.restore(text, mapping)
        if result.restore_decision != "RESTORED":
            raise ProblemError(422, "unknown-placeholder", "Text contains an unknown placeholder")
        return result.restored_text

    def _check_restored_size(self, text: str, mapping: dict[str, str]) -> None:
        """Count UTF-8 output bytes before replacement, without allocating expanded text."""
        size, end = 0, 0
        value_sizes: dict[str, int] = {}
        for match in PLACEHOLDER_RE.finditer(text):
            token = match.group()
            if token not in value_sizes:
                value_sizes[token] = len(mapping.get(token, token).encode("utf8"))
            size += len(text[end:match.start()].encode("utf8")) + value_sizes[token]
            if size > self.max_restored_bytes:
                raise ProblemError(413, "restored-text-too-large", "Restored text exceeds output limit")
            end = match.end()
        if size + len(text[end:].encode("utf8")) > self.max_restored_bytes:
            raise ProblemError(413, "restored-text-too-large", "Restored text exceeds output limit")

    def delete(self, sid, principal):
        try:
            self.records.delete(sid, tenant_id=principal.tenant_id)
        except RecordNotFound:
            raise ProblemError(404, "session-not-found", "Session not found") from None


@dataclass
class SessionContext:
    service: SessionService
    request: RedactionRequestV3
    principal: Principal
    session_id: str
    mode: str
    record: Record | None = None
    deadline: Deadline | None = None

    async def render(self, decisions):
        """Prepare in a worker; only the request task may publish a result before its deadline."""
        if self.deadline:
            self.deadline.check()
        out, payload = await asyncio.to_thread(self._prepare, decisions)
        if self.deadline:
            self.deadline.check()
        svc = self.service
        try:
            self.record = svc.records.commit(self.session_id, payload, svc.ttl_seconds,
                                             tenant_id=self.principal.tenant_id, backend=self.mode)
        except Exception:
            raise ProblemError(503, "session-store-unavailable", "Session storage unavailable") from None
        if self.deadline:
            self.deadline.check()
        return out

    def _prepare(self, decisions):
        """Pure preparation: a cancelled worker must never write or resurrect a record."""
        svc, req = self.service, self.request
        out = svc.components.pseudonymize(req.purpose, req.email, decisions, LabelState())
        payload = svc.backends[self.mode].encode(out.mapping, self.principal.tenant_id, self.session_id)
        return out, payload

    def abort(self):
        self.service.records.release(self.session_id)
        if self.record is not None:
            self.service.records.delete(self.session_id, tenant_id=self.principal.tenant_id)
