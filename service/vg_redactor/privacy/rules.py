"""Rule-based detection (`detect_rules`). Privacy Research.

Covers patterns with a fixed shape and what Presidio cannot know:
phone numbers and extensions, email addresses, SSN-shaped IDs, card numbers (Luhn-checked),
money amounts, US postal addresses, ages, the client's term list (project code names, deal names,
counterparties), every occurrence of the names given in the from / to / cc header fields, and
the name under a sign-off ("Thanks,\nJordan").
"""
from __future__ import annotations

import re

from ..contracts.components import ContextStore
from ..contracts.types import Candidate, Segment
from .names import clean_person_name, name_parts

_SCALE = r"(?:k|K|m|M|mm|MM|bn|B|thousand|million|billion)"
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"

# US postal addresses. Home or office cannot be told from the text, so every match is
# ADDRESS_HOME (Medium) and the model's score decides; a publicly listed office address scores low
# and is kept (the model's own label for it is ADDRESS_PUBLIC, Public tier).
_STATES = ("AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|"
           "NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY")
_SUFFIX = (r"Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|"
           r"Terrace|Ter|Circle|Cir|Parkway|Pkwy|Highway|Hwy|Square|Sq")
_WORD = r"(?:[A-Z][a-zA-Z.'-]*|\d+(?:st|nd|rd|th))"
_UNIT = r"(?:,?\s*(?:Apt|Apartment|Suite|Ste|Unit|Floor|Fl|#)\.?\s*#?[A-Za-z0-9-]+)?"
_CITY_STATE_ZIP = rf"[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+){{0,2}},?\s+(?:{_STATES})\s+\d{{5}}(?:-\d{{4}})?\b"
_ADDRESS = (rf"\b\d{{1,6}}(?:\s+{_WORD}){{1,4}}\s+(?:{_SUFFIX})\b\.?{_UNIT}(?:,\s*{_CITY_STATE_ZIP})?"
            rf"|\bP\.?\s?O\.?\s?Box\s+\d+\b(?:,\s*{_CITY_STATE_ZIP})?"
            rf"|\b{_CITY_STATE_ZIP}")
AGE_RE = re.compile(r"\b(?:aged?\s+\d{1,3}|\d{1,3}[- ]years?[- ]old|\d{1,3}-year-old)\b",
                    re.IGNORECASE)

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PHONE_PERSONAL", re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")),
    # Extensions: "ext. 204", "extension 204", or a bare lower-case "x4521" that starts a word.
    # The bare form must not follow a hyphen or bracket, so codes ("US-EN-6403-X501") and user
    # agents ("(X11; Linux") are not taken for extensions.
    ("PHONE_PERSONAL", re.compile(r"(?i:\b(?:ext\.?|extension)\s?\d{2,5}\b)|(?<![^\s,;:])x\d{2,5}\b")),
    ("EMAIL_PERSONAL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]*\w")),
    ("GOV_ID", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    # Card numbers start with 2-6 (Mastercard 2-series, Amex 3, Visa 4, Mastercard 5, Discover 6),
    # so order and ticket numbers that pass Luhn by chance are not taken for cards.
    ("CARD_NUMBER", re.compile(r"(?<!\d)[2-6](?:[ -]?\d){12,15}(?!\d)")),
    # AMOUNT is Medium: "$20 lunch" and an unreleased reserve look alike, so the model's
    # contextual score decides.
    ("AMOUNT", re.compile(
        rf"[$€£¥]\s?(?:{_NUM})(?:\s?{_SCALE}\b)?"
        rf"|\b(?:USD|EUR|GBP|CNY)\s?(?:{_NUM})(?:\s?{_SCALE}\b)?"
        rf"|\b(?:{_NUM})\s?(?:million|billion|thousand)\b(?:\s(?:dollars|euros|pounds))?"
        rf"|\b(?:{_NUM})\s(?:dollars|euros|pounds)\b")),
    ("ADDRESS_HOME", re.compile(_ADDRESS)),
    ("AGE", AGE_RE),
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


# ---- the name under a sign-off -----------------------------------------------------------------
# Finds "Thanks,\nJordan" and "Best, Alex" when the header carries no name (forwarded mail,
# a mailbox address only). Presidio misses a lone name on its own line.
_SIGNOFF = re.compile(
    r"(?:^|(?<=[.!?]))[ \t>-]*"
    r"(?i:thanks|thank you|many thanks|best|best regards|regards|kind regards|warm regards|"
    r"warmly|cheers|sincerely|yours|cordially|talk soon)[ \t]*[,!.]?[ \t]*(?:\n[ \t>]*|[ \t]+)"
    r"(?P<name>[A-Z][a-zA-Z'’-]+(?:[ \t]+[A-Z][a-zA-Z'’.-]*){0,2})[ \t]*$",
    re.MULTILINE)


def _signoff_candidates(segments: list[Segment]) -> list[Candidate]:
    return [Candidate(field=seg.field, start=m.start("name"), end=m.end("name"), type="PERSON",
                      detectors={"rules"}, hint="signoff_name")
            for seg in segments for m in _SIGNOFF.finditer(seg.text)
            if clean_person_name(m.group("name"))]  # drops "Best,\nThe Finance Team"


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
    return out + _header_name_candidates(segments) + _signoff_candidates(segments)


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
