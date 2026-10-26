"""Authenticated tokens, exact-text rendering and all-or-nothing restoration.

New tokens use independent conversation keys and opaque random handles (format 2).
Legacy format-1 tokens keep their original master-key/expiry semantics for migration.
Tenant identity is authenticated out of band. Exact UTF-8 bytes are restored, never aliases.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag

from ..contracts.errors import ProblemError
from ..contracts.fields import email_to_dict, iter_fields, set_field
from ..contracts.types import Decision, PseudonymResult, RedactionRequestV2, RestoreOutcome, SpanOut
from .backends import AesSivBackend, MappingBackend, TokenBackend
from .store import MappingStore
from .conversations import ConversationKey, ConversationKeyManager, UnavailableConversation
from .wire import CANDIDATE, LEGACY, TOKEN, TOKEN_V2, Mode, Parsed, Principal, packed


class TokenService:
    def __init__(self, keys: dict[str, str], active_key_id: str, store: MappingStore,
                 *, clock=time.time, conversation_max_lifetime_seconds=86400,
                 conversation_tombstone_seconds=86400):
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
        self.conversations = ConversationKeyManager(self.keys, active_key_id, store.conversations,
            max_lifetime_seconds=conversation_max_lifetime_seconds,
            tombstone_seconds=conversation_tombstone_seconds, clock=lambda: self.clock())
        self.backends: dict[str, TokenBackend] = {'m': MappingBackend(self), 's': AesSivBackend(self)}

    @property
    def enabled(self):
        return bool(self.keys)

    def require_enabled(self):
        if not self.enabled:
            raise ProblemError(503, 'tokenization-unconfigured', 'V2 token keys are not configured')

    def scope(self, principal, group, kid):
        return self._mac(kid, 'group', principal.tenant_id, group).hex()[:32]

    def _mac(self, kid, *parts, material=None):
        # Domain-separated key derivation: the HMAC key is distinct from the SIV key.
        key = (material.derive('reference-hmac', 32) if material else
               hmac.digest(self.keys[kid], b'vg-token-hmac-v1', 'sha256'))
        return hmac.digest(key, packed(*parts), 'sha256')

    def encryption_key(self, parsed, material=None):
        if parsed.format_version == 1:
            return self.keys[parsed.kid]
        if material is None or material.scope != parsed.scope or material.version != parsed.kid:
            raise ValueError('Conversation key required')
        return material.derive('mapping-aes-siv' if parsed.mode == 'm' else 'token-aes-siv', 64)

    @staticmethod
    def _header(p, principal):
        if p.format_version == 2:
            return packed('vg-token', 2, p.mode, p.entity_type, principal.tenant_id, p.scope, p.kid)
        return packed('vg-token', 1, p.mode, p.entity_type, p.kid, principal.tenant_id,
                      p.scope, p.expires)

    @staticmethod
    def _storage_group(principal, kid, scope):
        return hashlib.sha256(packed(principal.tenant_id, kid, scope)).hexdigest()

    @staticmethod
    def _mapping_aad(p, principal, reference):
        return packed('vg-mapping', p.format_version, principal.tenant_id, p.kid, p.scope,
                      p.entity_type, reference)

    def storage_group(self, principal, parsed):
        kid = parsed.kid if parsed.format_version == 1 else 'conversation-' + parsed.kid
        return self._storage_group(principal, kid, parsed.scope)

    def check_group(self, principal, group):
        if '*' not in principal.groups and group not in principal.groups:
            raise ProblemError(403, 'group-forbidden', 'Group access denied')

    def _parse(self, text, principal):
        match = TOKEN_V2.fullmatch(text)
        if match:
            mode, kind, scope, version, payload = match.groups()
            return Parsed(text, mode, kind, version, scope, 0, payload, format_version=2)
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
        materials = {}
        for token in candidates:
            try:
                p = self._parse(token, principal)
                material = None
                if p.format_version == 2:
                    identity = (p.scope, p.kid)
                    if identity not in materials:
                        materials[identity] = await self.conversations.load(principal, p.scope, p.kid)
                    material = materials[identity]
                backend = self.backends[p.mode]
                reference = backend.reference(p, principal, material)
                if reference is None:
                    originals[token] = backend.decode(p, principal, material=material)
                else:
                    pending[self.storage_group(principal, p)].append((p, reference, material))
            except (ValueError, InvalidTag, UnicodeError):
                invalid.add(token)
        if invalid:
            return RestoreOutcome(restore_decision='BLOCKED', reason='invalid_or_unavailable_token',
                                  unmatched_placeholders=sorted(invalid))
        try:
            for group, entries in pending.items():
                values = await self.store.get(group, [reference for _, reference, _ in entries])
                for (p, reference, material), value in zip(entries, values, strict=True):
                    try:
                        originals[p.text] = self.backends[p.mode].decode(
                            p, principal, value, material, verified_reference=reference)
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
        return TokenContext(self, request, principal, mode, ttl)

    async def delete_group(self, principal, group):
        self.require_enabled()
        self.check_group(principal, group)
        scope = await self.conversations.scope_for_group(principal, group)
        await self._delete_mappings(principal, group, scope)

    async def _delete_mappings(self, principal, group, scope):
        groups = [self._storage_group(principal, kid, self.scope(principal, group, kid))
                  for kid in self.keys]
        if scope:
            groups.append(self._storage_group(principal, 'conversation-1', scope))
        try:
            await self.store.delete(groups)
        except Exception:
            raise ProblemError(503, 'mapping-store-unavailable', 'Mapping storage unavailable') from None

    async def close_conversation(self, principal, group):
        self.require_enabled()
        self.check_group(principal, group)
        scope = await self.conversations.close(principal, group)
        await self._delete_mappings(principal, group, scope)

    async def validate_cached(self, body, principal):
        # A replay must not bypass closure/expiry of any conversation represented in its tokens.
        from ..contracts.types import EmailInV2
        texts = iter_fields(body['redacted_purpose'],
                            EmailInV2.model_validate(body['redacted_email'])).values()
        for text in texts:
            if CANDIDATE.search(text):
                result = await self.restore(text, principal)
                if result.restore_decision == 'BLOCKED':
                    raise ProblemError(409, 'cached-token-unavailable', 'Cached tokens are unavailable')


@dataclass
class TokenContext:
    service: TokenService
    request: RedactionRequestV2
    principal: Principal
    mode: Mode
    ttl: int
    key: ConversationKey | None = field(default=None, repr=False)

    @property
    def expires(self):
        if self.key is None:
            raise RuntimeError('Conversation has not been prepared')
        return self.key.expires_at

    async def check_available(self):
        self.key = await self.service.conversations.check_available(
            self.principal, self.request.group_id, self.ttl)
        if self.key is not None:
            await self._retain_mappings()

    async def prepare(self):
        if self.key is None:
            self.key = await self.service.conversations.get_or_create(
                self.principal, self.request.group_id, self.ttl)
        else:
            try:
                self.key = await self.service.conversations.load(
                    self.principal, self.key.scope, self.key.version, ttl=self.ttl)
            except UnavailableConversation:
                raise ProblemError(410, 'conversation-unavailable', 'Conversation expired or closed') from None
        await self._retain_mappings()

    async def _retain_mappings(self):
        try:
            await self.service.store.touch(self.service._storage_group(
                self.principal, 'conversation-' + self.key.version, self.key.scope), self.expires)
        except Exception:
            raise ProblemError(503, 'mapping-store-unavailable', 'Mapping storage unavailable') from None

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
        await self.prepare()
        kid, scope = self.key.version, self.key.scope
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
            p = Parsed('', mode, c.type, kid, scope, 0, '', format_version=2)
            encoded = svc.backends[mode].encode(p, principal, raw, self.key)
            payload = encoded.payload
            if encoded.reference is not None:
                mapping[encoded.reference] = encoded.stored_value
            token = f'[VG:2:{mode}:{c.type}:{scope}:{kid}:{payload}]'
            replacements.append((c.field, c.start, c.end, token))
        # Publish atomically and reconcile concurrent deadline extensions. Rewrite rather
        # than just touch: a delayed first write may already have expired at its old deadline.
        for _ in range(16):
            published_expiry = self.expires
            if mapping:
                try:
                    await svc.store.put(svc._storage_group(principal, 'conversation-' + kid, scope),
                                        mapping, published_expiry)
                except Exception:
                    raise ProblemError(503, 'mapping-store-unavailable', 'Mapping storage unavailable') from None
            # Closure during storage work must not issue tokens, including after a retry.
            try:
                self.key = await svc.conversations.load(principal, scope, kid)
            except UnavailableConversation:
                raise ProblemError(410, 'conversation-unavailable', 'Conversation expired or closed') from None
            if not mapping:
                await self._retain_mappings()
                break
            if self.expires == published_expiry:
                break
        else:
            raise ProblemError(503, 'conversation-busy', 'Conversation deadline update contention')
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
