"""Shared helper: remove reply quote markers ("> ") before detection. Privacy Research.

A quoted reply puts "> " at the start of every line, which breaks values that wrap across lines
("410-555-\\n> 0171") and adds noise for spaCy. Detectors run on the text without the markers;
offsets are then mapped back, so candidates still index the original field text. A helper, not
a component: `segment()` keeps its contract.
"""
from __future__ import annotations

import re

from ..contracts.types import Candidate, Segment

_MARKER = re.compile(r"^[ \t]*(?:>[ \t]?)+", re.MULTILINE)


def unquote(segments: list[Segment]) -> tuple[list[Segment], dict[str, list[int]]]:
    """Segments without quote markers, and for each changed field a map from every position in
    the new text (plus its end) to the position in the original text."""
    out, maps = [], {}
    for seg in segments:
        if not _MARKER.search(seg.text):
            out.append(seg)
            continue
        keep, pos = [], 0
        for m in _MARKER.finditer(seg.text):
            keep.extend(range(pos, m.start()))
            pos = m.end()
        keep.extend(range(pos, len(seg.text)))
        maps[seg.field] = keep + [len(seg.text)]
        out.append(seg.model_copy(update={"text": "".join(seg.text[i] for i in keep)}))
    return out, maps


def requote(candidates: list[Candidate], maps: dict[str, list[int]]) -> list[Candidate]:
    """Map candidate offsets from unquoted text back to the original field text."""
    out = []
    for c in candidates:
        m = maps.get(c.field)
        out.append(c if m is None else
                   c.model_copy(update={"start": m[c.start], "end": m[c.end - 1] + 1}))
    return out
