"""FieldPath helpers: flatten a request into {path: text} and write redacted text back."""
from __future__ import annotations

import re

from .types import EmailIn

_IDX = re.compile(r"^(\w+)\[(\d+)\]$")


def iter_fields(purpose: str, email: EmailIn) -> dict[str, str]:
    """Every redactable text field, in a stable order."""
    out: dict[str, str] = {"purpose": purpose}
    if email.subject:
        out["email.subject"] = email.subject
    if email.from_:
        if email.from_.name:
            out["email.from.name"] = email.from_.name
        out["email.from.address"] = email.from_.address
    for key in ("to", "cc"):
        for i, a in enumerate(getattr(email, key)):
            if a.name:
                out[f"email.{key}[{i}].name"] = a.name
            out[f"email.{key}[{i}].address"] = a.address
    out["email.body"] = email.body
    for i, t in enumerate(email.thread):
        out[f"email.thread[{i}].text"] = t.text
    return out


def email_to_dict(email: EmailIn) -> dict:
    return email.model_dump(by_alias=True, exclude_none=True)


def set_field(email_dict: dict | EmailIn, path: str, value: str) -> None:
    """Write into an email dict or an already validated model, preserving original offsets."""
    def get(obj, key):
        return obj[key] if isinstance(obj, dict) else getattr(obj, "from_" if key == "from" else key)

    parts = path.split(".")[1:]  # drop the leading "email"
    cur = email_dict
    for part in parts[:-1]:
        m = _IDX.match(part)
        cur = get(cur, m.group(1))[int(m.group(2))] if m else get(cur, part)
    last = parts[-1]
    m = _IDX.match(last)
    if m:
        get(cur, m.group(1))[int(m.group(2))] = value
    elif isinstance(cur, dict):
        cur[last] = value
    else:
        setattr(cur, "from_" if last == "from" else last, value)
