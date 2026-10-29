"""Presidio detection (`detect_presidio`). Privacy Research.

Presidio's score is a detection confidence ("looks like a phone number"), not a probability of
being private, so it is not passed on; the model's assessment supplies the score.
Needs the `privacy` extra: `pip install -e ".[privacy]"` and `python -m spacy download en_core_web_lg`.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from ..contracts.types import Candidate, Segment
from .rules import contact_type

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
# spaCy tags fiscal periods as places ("Sync with Kim on Q3").
_PERIOD = re.compile(r"(?:Q[1-4]|H[12]|FY\s?\d{2,4})", re.IGNORECASE)
# The US driver's licence recogniser matches any short letter-digit token ("x4521", "Q3", "B7")
# at 0.3 and maps to GOV_ID (High). Keep it only with context ("license") or a licence length.
_LICENSE_MIN_SCORE, _LICENSE_MIN_LEN = 0.4, 7


def _keep(entity: str, score: float, span: str) -> bool:
    if entity == "US_DRIVER_LICENSE":
        return score >= _LICENSE_MIN_SCORE or len(span) >= _LICENSE_MIN_LEN
    if entity == "LOCATION":
        return not _PERIOD.fullmatch(span)
    if entity == "DATE_TIME":
        # "Friday", "next week", "the quarter" identify no one; a date of birth has digits.
        return any(ch.isdigit() for ch in span)
    return True




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
                if _keep(r.entity_type, r.score, span):
                    out.append(Candidate(field=seg.field, start=r.start, end=r.end,
                                         type=contact_type(ENTITY_MAP[r.entity_type], span),
                                         detectors={"presidio"}))
        return out

    return detect_presidio
