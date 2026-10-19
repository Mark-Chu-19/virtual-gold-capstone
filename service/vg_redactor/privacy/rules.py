"""Rule-based detection (`detect_rules`). Privacy Research.

Covers patterns with a fixed shape and what Presidio cannot know:
phone numbers and extensions, email addresses, SSN-shaped IDs, card numbers (Luhn-checked),
money amounts, the client's term list (project code names, deal names, counterparties), and
every occurrence of the names given in the from / to / cc header fields.
"""
from __future__ import annotations

import re

from ..contracts.components import ContextStore
from ..contracts.types import Candidate, Segment
from .names import clean_person_name, name_parts

_SCALE = r"(?:k|K|m|M|mm|MM|bn|B|thousand|million|billion)"
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PHONE_PERSONAL", re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")),
    ("PHONE_PERSONAL", re.compile(r"\b(?:ext\.?|extension|x)\s?\d{2,5}\b", re.IGNORECASE)),
    ("EMAIL_PERSONAL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]*\w")),
    ("GOV_ID", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    ("CARD_NUMBER", re.compile(r"(?<!\d)(?:\d[ -]?){12,15}\d(?!\d)")),
    # AMOUNT is deliberately not in the tier table: decide() redacts unknown types by default
    # until the client decides how amounts should be tiered.
    ("AMOUNT", re.compile(
        rf"[$€£¥]\s?(?:{_NUM})(?:\s?{_SCALE}\b)?"
        rf"|\b(?:USD|EUR|GBP|CNY)\s?(?:{_NUM})(?:\s?{_SCALE}\b)?"
        rf"|\b(?:{_NUM})\s?(?:million|billion|thousand)\b(?:\s(?:dollars|euros|pounds))?"
        rf"|\b(?:{_NUM})\s(?:dollars|euros|pounds)\b")),
]

TERM_TYPE = "CODENAME"  # High tier in config/policy.yaml

# ---- names from the header -----------------------------------------------------------------
# The sender's and recipients' names are known from the header, so every place they appear
# (sign-off, greeting, quoted thread) can be found without relying on NER. Presidio misses a
# lone sign-off such as "- Dana" because it has no surrounding sentence. Name rules: names.py.
HEADER_NAME_FIELD = re.compile(r"^email\.(?:from|to\[\d+\]|cc\[\d+\])\.name$")


def header_names(segments: list[Segment]) -> set[str]:
    """Full names and their capitalised parts from the from / to / cc name fields."""
    names: set[str] = set()
    for seg in segments:
        full = clean_person_name(seg.text) if HEADER_NAME_FIELD.match(seg.field) else None
        if full:
            names |= {full} | name_parts(full)
    return names


def _header_name_candidates(segments: list[Segment]) -> list[Candidate]:
    names = header_names(segments)
    if not names:
        return []
    alts = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    rx = re.compile(rf"(?<!\w)(?:{alts})(?!\w)")  # case-sensitive: names are capitalised
    return [Candidate(field=seg.field, start=m.start(), end=m.end(), type="PERSON",
                      detectors={"rules"}, hint="header_name")
            for seg in segments for m in rx.finditer(seg.text)]


def luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def _term_pattern(terms: set[str]) -> re.Pattern[str] | None:
    if not terms:
        return None
    alts = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{alts})(?!\w)", re.IGNORECASE)


def detect_rules(segments: list[Segment], ctx: ContextStore) -> list[Candidate]:
    """Sync, CPU-only, no side effects. Offsets index each segment's original field text."""
    terms = _term_pattern(ctx.term_list)
    out: list[Candidate] = []
    for seg in segments:
        for etype, rx in PATTERNS:
            for m in rx.finditer(seg.text):
                if etype == "CARD_NUMBER" and not luhn_ok(re.sub(r"\D", "", m.group())):
                    continue
                out.append(Candidate(field=seg.field, start=m.start(), end=m.end(), type=etype,
                                     detectors={"rules"}))
        if terms:
            for m in terms.finditer(seg.text):
                out.append(Candidate(field=seg.field, start=m.start(), end=m.end(), type=TERM_TYPE,
                                     detectors={"rules"}, hint="term_list_match"))
    return out + _header_name_candidates(segments)


# ---- confidential markers -------------------------------------------------------------------
# Ready but NOT wired in: raising every span inside a marked paragraph to the High threshold
# needs the decision step to see passage positions, which the 0.4.2 `decide` signature does not
# carry. See privacy/README.md, "Contract requests".
MARKERS = ("strictly confidential", "confidential", "board only", "board-only", "do not forward",
           "don't forward", "not for distribution", "internal only", "privileged",
           "attorney-client", "under NDA", "embargoed")
_MARKER_RE = _term_pattern(set(MARKERS))
_PARA_BREAK = re.compile(r"\n\s*\n")


def marked_passages(segments: list[Segment]) -> list[tuple[str, int, int]]:
    """(field, start, end) of every blank-line-separated paragraph containing a marker."""
    out = []
    for seg in segments:
        start = 0
        for brk in [*_PARA_BREAK.finditer(seg.text), None]:
            end = brk.start() if brk else len(seg.text)
            if _MARKER_RE and _MARKER_RE.search(seg.text, start, end):
                out.append((seg.field, start, end))
            if brk:
                start = brk.end()
    return out
