"""Shared placeholder grammar, literal preservation and collision-free allocation."""
from __future__ import annotations

import re
from collections.abc import Iterable

from .types import LabelState

PLACEHOLDER_RE = re.compile(r"\[[A-Za-z]+_\d+\]")


def literal_placeholders(texts: Iterable[str], labels: LabelState) -> dict[str, str]:
    """Reserve labels already in the original text and retain exact identity mappings."""
    literals = {match.group() for text in texts for match in PLACEHOLDER_RE.finditer(text)}
    labels.reserved.update(token.upper() for token in literals)
    return {token: token for token in literals}


def next_placeholder(kind: str, labels: LabelState) -> str:
    number = labels.counters.get(kind, 0) + 1
    while f"[{kind}_{number}]" in labels.reserved:
        number += 1
    labels.counters[kind] = number
    return f"[{kind}_{number}]"
