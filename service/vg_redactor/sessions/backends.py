"""Plaintext or AES-SIV-encrypted V3 mapping payloads with identical placeholders."""
from __future__ import annotations

import base64
import hmac
import re
import json
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESSIV

from ..contracts.errors import ProblemError
from .encoding import b64, packed, unb64


def decode_keyring(keys: dict[str, str], active_key_id: str) -> dict[str, bytes]:
    """Validate configured AES-256-SIV keys once at startup; never include secrets in errors."""
    decoded = {}
    for kid, encoded in keys.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", kid):
            raise ValueError("Invalid session key identifier")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except ValueError:
            raise ValueError("Session keys must be standard base64") from None
        if len(raw) != 64:
            raise ValueError("AES-256-SIV requires a 64-byte key")
        decoded[kid] = raw
    if decoded and active_key_id not in decoded:
        raise ValueError("Active session key is missing from keyring")
    return decoded


class RestorationBackend(Protocol):
    def encode(self, mapping: dict[str, str], tenant: str, session_id: str) -> dict[str, str]: ...
    def decode(self, payload: dict[str, str], tenant: str, session_id: str) -> dict[str, str]: ...


class MappingBackend:
    def encode(self, mapping, tenant, session_id):
        return dict(mapping)

    def decode(self, payload, tenant, session_id):
        return dict(payload)


class AesMappingBackend:
    def __init__(self, keys: dict[str, bytes], active_key_id: str):
        self.keys, self.active_key_id = keys, active_key_id

    def _cipher(self, kid):
        if kid not in self.keys:
            raise ProblemError(503, "session-key-unavailable", "Session encryption key unavailable")
        # Derive a purpose-specific key for authenticated V3 mapping payloads.
        key = hmac.digest(self.keys[kid], b"vg-v3-mapping-aes-siv-v1", "sha512")
        return AESSIV(key)

    @staticmethod
    def _aad(tenant, session_id, kid):
        return [packed("vg-v3-mapping", 1, tenant, session_id, kid)]

    def encode(self, mapping, tenant, session_id):
        kid = self.active_key_id
        raw = json.dumps(mapping, ensure_ascii=False, separators=(",", ":")).encode()
        ciphertext = self._cipher(kid).encrypt(raw, self._aad(tenant, session_id, kid))
        return {"key_id": kid, "ciphertext": b64(ciphertext)}

    def decode(self, payload, tenant, session_id):
        kid = payload["key_id"]
        raw = self._cipher(kid).decrypt(unb64(payload["ciphertext"]),
                                        self._aad(tenant, session_id, kid))
        mapping = json.loads(raw)
        if not isinstance(mapping, dict) or any(
                not isinstance(k, str) or not isinstance(v, str) for k, v in mapping.items()):
            raise ValueError("Invalid session payload")
        return mapping
