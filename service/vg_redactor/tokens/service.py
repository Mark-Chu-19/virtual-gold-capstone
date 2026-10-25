"""Authenticated tokens, exact-text rendering and all-or-nothing restoration.

Wire format: [VG:1:<m|s>:<TYPE>:<kid>:<group-handle>:<expiry>:<payload>].
Tenant identity is authenticated out of band. Group handles reveal no business identifier.
Mapping references and at-rest ciphertexts are deterministic within a tenant/group/key/type.
AES-SIV encrypts the exact original UTF-8 bytes, never a normalized entity alias.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
from collections import defaultdict
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag

from ..contracts.errors import ProblemError
from ..contracts.fields import email_to_dict, iter_fields, set_field
from ..contracts.types import Decision, PseudonymResult, RedactionRequestV2, RestoreOutcome, SpanOut
from .backends import AesSivBackend, MappingBackend, TokenBackend
from .store import MappingStore
from .wire import CANDIDATE, LEGACY, TOKEN, Mode, Parsed, Principal, packed


class TokenService:
    def __init__(self, keys: dict[str, str], active_key_id: str, store: MappingStore,
                 *, clock=time.time):
        self.keys = {}
        for kid, encoded in keys.items():
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', kid):
                raise ValueError('Invalid token key identifier')
            try:
                raw = base64.b64decode(encoded, validate=True)
            except ValueError:
                raise ValueError('Token keys must be standard base64') from None
            if len(raw) != 64:
                raise ValueError('AES-256-SIV requires a 64-byte key')
            self.keys[kid] = raw
        if keys and active_key_id not in keys:
            raise ValueError('Active token key is missing from keyring')
        self.active_key_id, self.store, self.clock = active_key_id, store, clock
        self.backends: dict[str, TokenBackend] = {'m': MappingBackend(self), 's': AesSivBackend(self)}

    @property
    def enabled(self):
        return bool(self.keys)

    def require_enabled(self):
        if not self.enabled:
            raise ProblemError(503, 'tokenization-unconfigured', 'V2 token keys are not configured')

    def scope(self, principal, group, kid):
        return self._mac(kid, 'group', principal.tenant_id, group).hex()[:32]

    def _mac(self, kid, *parts):
        # Domain-separated key derivation: the HMAC key is distinct from the SIV key.
        key = hmac.digest(self.keys[kid], b'vg-token-hmac-v1', 'sha256')
        return hmac.digest(key, packed(*parts), 'sha256')

    @staticmethod
    def _header(p, principal):
        return packed('vg-token', 1, p.mode, p.entity_type, p.kid, principal.tenant_id,
                      p.scope, p.expires)

    @staticmethod
    def _storage_group(principal, kid, scope):
        return hashlib.sha256(packed(principal.tenant_id, kid, scope)).hexdigest()

    @staticmethod
    def _mapping_aad(p, principal, reference):
        return packed('vg-mapping', 1, principal.tenant_id, p.kid, p.scope,
                      p.entity_type, reference)

    def check_group(self, principal, group):
        if '*' not in principal.groups and group not in principal.groups:
            raise ProblemError(403, 'group-forbidden', 'Group access denied')

    def _parse(self, text, principal):
        match = TOKEN.fullmatch(text)
        if not match:
            raise ValueError('Malformed token')
        mode, kind, kid, scope, expiry, payload = match.groups()
        p = Parsed(text, mode, kind, kid, scope, int(expiry), payload)
        if kid not in self.keys or p.expires <= self.clock():
            raise ValueError('Unavailable token')
        if '*' not in principal.groups and not any(
                hmac.compare_digest(scope, self.scope(principal, group, kid))
                for group in principal.groups):
            raise ValueError('Unavailable token')
        return p

    async def restore(self, text: str, principal: Principal) -> RestoreOutcome:
        self.require_enabled()
        candidates = list(dict.fromkeys(CANDIDATE.findall(text)))
        invalid = set(LEGACY.findall(text))
        originals = {}
        pending = defaultdict(list)
        for token in candidates:
            try:
                p = self._parse(token, principal)
                backend = self.backends[p.mode]
                reference = backend.reference(p, principal)
                if reference is None:
                    originals[token] = backend.decode(p, principal)
                else:
                    pending[self._storage_group(principal, p.kid, p.scope)].append((p, reference))
            except (ValueError, InvalidTag, UnicodeError):
                invalid.add(token)
        if invalid:
            return RestoreOutcome(restore_decision='BLOCKED', reason='invalid_or_unavailable_token',
                                  unmatched_placeholders=sorted(invalid))
        try:
            for group, entries in pending.items():
                values = await self.store.get(group, [reference for _, reference in entries])
                for (p, reference), value in zip(entries, values, strict=True):
                    try:
                        originals[p.text] = self.backends[p.mode].decode(p, principal, value)
                    except (ValueError, InvalidTag, UnicodeError):
                        invalid.add(p.text)
        except Exception:
            raise ProblemError(503, 'mapping-store-unavailable', 'Mapping storage unavailable') from None
        if invalid:
            return RestoreOutcome(restore_decision='BLOCKED', reason='invalid_or_unavailable_token',
                                  unmatched_placeholders=sorted(invalid))
        # One pass: plaintext resembling another token must never be recursively decrypted.
        return RestoreOutcome(restore_decision='RESTORED',
                              restored_text=CANDIDATE.sub(lambda m: originals[m.group()], text))

    def context(self, request, principal, mode, ttl):
        self.require_enabled()
        self.check_group(principal, request.group_id)
        return TokenContext(self, request, principal, mode, int(self.clock()) + ttl, ttl)

    async def delete_group(self, principal, group):
        self.require_enabled()
        self.check_group(principal, group)
        groups = [self._storage_group(principal, kid, self.scope(principal, group, kid))
                  for kid in self.keys]
        try:
            await self.store.delete(groups)
        except Exception:
            raise ProblemError(503, 'mapping-store-unavailable', 'Mapping storage unavailable') from None


@dataclass
class TokenContext:
    service: TokenService
    request: RedactionRequestV2
    principal: Principal
    mode: Mode
    expires: int
    ttl: int

    async def masked_request(self):
        """Validate existing tokens and mask them length-preservingly before all detectors."""
        req = self.request.model_copy(deep=True)
        for path, text in iter_fields(req.purpose, req.email).items():
            if CANDIDATE.search(text) or LEGACY.search(text):
                result = await self.service.restore(text, self.principal)
                if result.restore_decision == 'BLOCKED':
                    raise ProblemError(422, 'invalid-token', 'Input contains an unavailable token')
                masked = CANDIDATE.sub(lambda m: ' ' * len(m.group()), text)
                if path == 'purpose':
                    req.purpose = masked
                else:
                    set_field(req.email, path, masked)
        return req

    async def render(self, decisions: list[Decision]) -> PseudonymResult:
        svc, principal, req = self.service, self.principal, self.request
        self.expires = int(svc.clock()) + self.ttl
        kid = svc.active_key_id
        scope = svc.scope(principal, req.group_id, kid)
        fields = iter_fields(req.purpose, req.email)
        output = dict(fields)
        mapping = {}
        replacements = []
        for decision in decisions:
            c = decision.candidate
            if decision.action != 'redact':
                continue
            # Never replace any part of a pre-existing token, even if a detector spans it.
            if any(c.start < m.end() and c.end > m.start()
                   for m in CANDIDATE.finditer(fields[c.field])):
                raise ProblemError(422, 'token-overlap', 'Detected span overlaps an existing token')
            raw = fields[c.field][c.start:c.end].encode('utf-8')
            mode = 'm' if self.mode == 'mapping' else 's'
            p = Parsed('', mode, c.type, kid, scope, self.expires, '')
            encoded = svc.backends[mode].encode(p, principal, raw)
            payload = encoded.payload
            if encoded.reference is not None:
                mapping[encoded.reference] = encoded.stored_value
            token = f'[VG:1:{mode}:{c.type}:{kid}:{scope}:{self.expires}:{payload}]'
            replacements.append((c.field, c.start, c.end, token))
        # Publish all mapping entries atomically, before returning any tokens.
        if mapping:
            try:
                await svc.store.put(svc._storage_group(principal, kid, scope), mapping, self.expires)
            except Exception:
                raise ProblemError(503, 'mapping-store-unavailable', 'Mapping storage unavailable') from None
        for path, start, end, token in sorted(replacements, key=lambda r: (r[0], -r[1])):
            output[path] = output[path][:start] + token + output[path][end:]
        email = email_to_dict(req.email)
        for path, text in output.items():
            if path != 'purpose':
                set_field(email, path, text)
        spans = [SpanOut(field=d.candidate.field, start=d.candidate.start, end=d.candidate.end,
                         type=d.candidate.type, tier=d.tier, action=d.action,
                         confidence=d.confidence, detectors=sorted(d.candidate.detectors), reason=d.reason)
                 for d in decisions]
        return PseudonymResult(redacted_purpose=output['purpose'], redacted_email=email,
                               spans=spans, mapping={})
