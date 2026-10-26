"""Pluggable token encoding; parsing, authorization and text replacement stay in the service."""
from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESSIV

from .wire import Parsed, Principal, b64, unb64


@dataclass(frozen=True)
class Encoded:
    payload: str
    reference: str | None = None
    stored_value: str | None = None


class TokenBackend(Protocol):
    def encode(self, parsed: Parsed, principal: Principal, raw: bytes, material=None) -> Encoded: ...
    def reference(self, parsed: Parsed, principal: Principal, material=None) -> str | None: ...
    def decode(self, parsed: Parsed, principal: Principal, stored_value: str | None = None,
               material=None, *, verified_reference: str | None = None) -> str: ...


class AesSivBackend:
    def __init__(self, service):
        self.service = service

    def encode(self, parsed, principal, raw, material=None):
        svc = self.service
        return Encoded(b64(AESSIV(svc.encryption_key(parsed, material)).encrypt(
            raw, [svc._header(parsed, principal)])))

    def reference(self, parsed, principal, material=None):
        return None

    def decode(self, parsed, principal, stored_value=None, material=None, *, verified_reference=None):
        svc = self.service
        return AESSIV(svc.encryption_key(parsed, material)).decrypt(
            unb64(parsed.payload), [svc._header(parsed, principal)]).decode('utf-8')


class MappingBackend:
    def __init__(self, service):
        self.service = service

    def encode(self, parsed, principal, raw, material=None):
        svc = self.service
        reference = b64(svc._mac(parsed.kid, 'reference', principal.tenant_id, parsed.scope,
                                 parsed.entity_type, b64(raw), material=material)[:24])
        signature = b64(svc._mac(parsed.kid, 'mapping-token',
                                  b64(svc._header(parsed, principal)), reference, material=material)[:16])
        value = b64(AESSIV(svc.encryption_key(parsed, material)).encrypt(
            raw, [svc._mapping_aad(parsed, principal, reference)]))
        return Encoded(reference + '.' + signature, reference, value)

    def reference(self, parsed, principal, material=None):
        svc = self.service
        reference, signature = parsed.payload.split('.')
        if len(unb64(reference)) != 24:
            raise ValueError('Invalid reference')
        expected = b64(svc._mac(parsed.kid, 'mapping-token',
                                b64(svc._header(parsed, principal)), reference, material=material)[:16])
        if not hmac.compare_digest(signature, expected):
            raise ValueError('Invalid signature')
        return reference

    def decode(self, parsed, principal, stored_value=None, material=None, *, verified_reference=None):
        if stored_value is None:
            raise ValueError('Mapping missing')
        svc = self.service
        # Restore already authenticates references before querying storage. Standalone calls
        # still verify the token unless an authenticated reference is explicitly supplied.
        reference = (verified_reference if verified_reference is not None else
                     self.reference(parsed, principal, material))
        return AESSIV(svc.encryption_key(parsed, material)).decrypt(
            unb64(stored_value), [svc._mapping_aad(parsed, principal, reference)]).decode('utf-8')
