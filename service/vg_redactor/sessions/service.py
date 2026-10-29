"""Tenant-bound V3 records using the shared pipeline, record store and exact-match restore.

`session_id` identifies one redaction, not a conversation. Backend/version is recorded
per result so changing deployment defaults cannot change how older results restore.
"""
from __future__ import annotations

from dataclasses import dataclass

from cryptography.exceptions import InvalidTag

from ..contracts.components import Components
from ..contracts.errors import ProblemError, RecordGone, RecordNotFound
from ..contracts.types import LabelState, RedactionRequestV3
from ..records.store import Record, RecordStore
from ..tokens.wire import Principal
from .backends import RestorationBackend
from .identifiers import SessionIdGenerator


class SessionService:
    def __init__(self, records: RecordStore, components: Components,
                 ids: SessionIdGenerator, backends: dict[str, RestorationBackend],
                 backend: str, ttl_seconds: int):
        self.records, self.components, self.ids = records, components, ids
        self.backends, self.backend, self.ttl_seconds = backends, backend, ttl_seconds

    def begin(self, req: RedactionRequestV3, principal: Principal):
        # Bound retries avoid an infinite loop if an injected generator is broken.
        for _ in range(8):
            sid = self.ids.new_id()
            if self.records.reserve(sid):
                return SessionContext(self, req, principal, sid, self.backend)
        raise ProblemError(503, "session-id-unavailable", "Could not allocate a session identifier")

    def _get(self, sid, principal):
        try:
            return self.records.get(sid, tenant_id=principal.tenant_id)
        except RecordNotFound:
            raise ProblemError(404, "session-not-found", "Session not found") from None
        except RecordGone:
            raise ProblemError(410, "session-gone", "Session expired or was deleted") from None

    def restore(self, sid: str, text: str, principal: Principal) -> str:
        record = self._get(sid, principal)
        if record.mapping is None or record.backend_version != 1 or record.backend not in self.backends:
            raise ProblemError(503, "session-payload-unavailable", "Session payload unavailable")
        try:
            mapping = self.backends[record.backend].decode(record.mapping, principal.tenant_id, sid)
        except (InvalidTag, ValueError, KeyError, TypeError):
            raise ProblemError(503, "session-payload-unavailable", "Session payload unavailable") from None
        result = self.components.restore(text, mapping)
        if result.restore_decision != "RESTORED":
            raise ProblemError(422, "unknown-placeholder", "Text contains an unknown placeholder")
        return result.restored_text

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

    async def render(self, decisions):
        """Pipeline rendering hook, also used by V2; no detection logic is duplicated."""
        svc, req = self.service, self.request
        out = svc.components.pseudonymize(req.purpose, req.email, decisions, LabelState())
        payload = svc.backends[self.mode].encode(out.mapping, self.principal.tenant_id, self.session_id)
        try:
            self.record = svc.records.commit(self.session_id, payload, svc.ttl_seconds, None,
                                             tenant_id=self.principal.tenant_id, backend=self.mode)
        except Exception:
            raise ProblemError(503, "session-store-unavailable", "Session storage unavailable") from None
        return out

    def abort(self):
        self.service.records.release(self.session_id)
        if self.record is not None:
            self.service.records.delete(self.session_id, tenant_id=self.principal.tenant_id)
