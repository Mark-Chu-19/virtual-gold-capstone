"""Canonical v2 wire encoding and authenticated token metadata."""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Literal

Mode = Literal['mapping', 'aes_siv']
CANDIDATE = re.compile(r'(?:\[VG[^\]\r\n]*(?:\]|(?=\r|\n|$))|(?<![\w\[])VG:[^\s\]]+\]?)', re.I)
TOKEN = re.compile(r'\[VG:1:([ms]):([A-Z_]+):([A-Za-z0-9_-]{1,32}):([a-f0-9]{32}):([1-9][0-9]{0,11}):([A-Za-z0-9_.-]+)\]')
TOKEN_V2 = re.compile(r'\[VG:2:([ms]):([A-Z_]+):([a-f0-9]{32}):([1-9][0-9]{0,8}):([A-Za-z0-9_.-]+)\]')
LEGACY = re.compile(r'\[[A-Za-z]+_\d+\]')


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def unb64(value: str) -> bytes:
    data = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    if b64(data) != value:
        raise ValueError('Noncanonical encoding')
    return data


def packed(*parts) -> bytes:
    return json.dumps(parts, ensure_ascii=True, separators=(',', ':')).encode()


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    groups: tuple[str, ...] = ('*',)


@dataclass(frozen=True)
class Parsed:
    text: str
    mode: str
    entity_type: str
    kid: str
    scope: str
    expires: int
    payload: str
    format_version: int = 1
