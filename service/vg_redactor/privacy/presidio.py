"""Presidio detection (`detect_presidio`). Privacy Research.

Presidio's score is a detection confidence ("looks like a phone number"), not a probability of
being private, so it is not passed on; the model's assessment supplies the score.
Needs the `privacy` extra: `pip install -e ".[privacy]"` and `python -m spacy download en_core_web_lg`.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from ..contracts.types import Candidate, Segment
from .rules import AGE_RE

# Presidio entity -> our taxonomy (config/policy.yaml). None = ignored.
ENTITY_MAP: dict[str, str | None] = {
    "PERSON": "PERSON",
    "PHONE_NUMBER": "PHONE_PERSONAL",
    "EMAIL_ADDRESS": "EMAIL_PERSONAL",
    "LOCATION": "CITY",
    "DATE_TIME": "DATE",
    "US_SSN": "GOV_ID", "US_PASSPORT": "GOV_ID", "US_DRIVER_LICENSE": "GOV_ID",
    "US_ITIN": "GOV_ID", "MEDICAL_LICENSE": "GOV_ID",
    "CREDIT_CARD": "CARD_NUMBER",
    "IBAN_CODE": "ACCOUNT_NUMBER", "US_BANK_NUMBER": "ACCOUNT_NUMBER", "CRYPTO": "ACCOUNT_NUMBER",
    "IP_ADDRESS": "NETWORK_ID", "MAC_ADDRESS": "NETWORK_ID",
    "NRP": "DEMOGRAPHIC",   # nationality, religious or political group
    "URL": None,            # mostly public links; also fires inside email addresses
    "UK_NHS": None,         # its checksum matches US phone numbers such as 412-555-0182
}
MIN_SCORE = 0.3  # Presidio's own cut-off, kept low because recall matters most

# ---- false positives seen on email text ------------------------------------------------------
# spaCy tags a capitalised word at the start of a sentence as a name ("Reach me on my cell",
# "Email john@acme.com"). Dropped only when it is one word, starts a sentence and is on this
# list; names from the header are found by the rules regardless.
SENTENCE_START_WORDS = {
    "reach", "ping", "call", "email", "text", "send", "loop", "sync", "check", "follow", "let",
    "please", "thanks", "hi", "hello", "hey", "dear", "regards", "cheers", "confirm", "review",
    "forward", "attach", "attached", "see", "note", "update", "schedule", "book", "meet", "ask",
    "tell", "chat", "circle", "flag", "remind", "hope", "kindly", "sorry", "congrats", "welcome",
    "best", "sincerely", "fyi", "re", "fw", "fwd", "per", "noted", "agreed", "approved", "sure"}
_SENTENCE_END = re.compile(r"(?:^|[.!?:;\n•*>-])[ \t]*$")
# spaCy tags fiscal periods as places ("Sync with Kim on Q3").
_PERIOD = re.compile(r"(?:Q[1-4]|H[12]|FY\s?\d{2,4})", re.IGNORECASE)
# The US driver's licence recogniser matches any short letter-digit token ("x4521", "Q3", "B7")
# at 0.3 and maps to GOV_ID (High). Keep it only with context ("license") or a licence length.
_LICENSE_MIN_SCORE, _LICENSE_MIN_LEN = 0.4, 7


def _keep(entity: str, score: float, text: str, span: str, start: int) -> bool:
    if entity == "US_DRIVER_LICENSE":
        return score >= _LICENSE_MIN_SCORE or len(span) >= _LICENSE_MIN_LEN
    if entity == "PERSON":
        return not (span.lower() in SENTENCE_START_WORDS
                    and _SENTENCE_END.search(text, 0, start) is not None)
    if entity == "LOCATION":
        return not _PERIOD.fullmatch(span)
    return True


# spaCy files long digit strings under DATE at 0.85 ("verify your 92535170542762962231"), which
# would drop an account number to the Low tier. Seven or more bare digits that do not read as a
# YYYYMMDD date are treated as an account number (High) instead.
_YYYYMMDD = re.compile(r"(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])")


def _our_type(entity: str, span: str) -> str | None:
    if entity == "DATE_TIME":
        if AGE_RE.fullmatch(span):
            return "AGE"  # spaCy files "age 42" and "42 years old" under DATE
        if span.isdigit() and len(span) >= 7 and not _YYYYMMDD.fullmatch(span):
            return "ACCOUNT_NUMBER"
    return ENTITY_MAP[entity]


def make_detect_presidio(analyzer: Any | None = None, language: str = "en"
                         ) -> Callable[[list[Segment]], list[Candidate]]:
    """Build `detect_presidio` with one AnalyzerEngine, loaded once at startup."""
    if analyzer is None:
        from presidio_analyzer import AnalyzerEngine
        analyzer = AnalyzerEngine()
    supported = set(analyzer.get_supported_entities(language))
    entities = sorted(e for e, t in ENTITY_MAP.items() if t is not None and e in supported)

    def detect_presidio(segments: list[Segment]) -> list[Candidate]:
        out: list[Candidate] = []
        for seg in segments:
            for r in analyzer.analyze(text=seg.text, language=language, entities=entities,
                                      score_threshold=MIN_SCORE):
                span = seg.text[r.start:r.end]
                if _keep(r.entity_type, r.score, seg.text, span, r.start):
                    out.append(Candidate(field=seg.field, start=r.start, end=r.end,
                                         type=_our_type(r.entity_type, span),
                                         detectors={"presidio"}))
        return out

    return detect_presidio
