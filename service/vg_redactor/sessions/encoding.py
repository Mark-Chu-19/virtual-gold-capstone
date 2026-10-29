"""Canonical encoding for authenticated session payloads."""
import base64
import json


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def unb64(value: str) -> bytes:
    data = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    if b64(data) != value:
        raise ValueError('Noncanonical encoding')
    return data


def packed(*parts) -> bytes:
    return json.dumps(parts, ensure_ascii=True, separators=(',', ':')).encode()
