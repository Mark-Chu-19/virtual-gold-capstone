"""V3 API and shared component data types. Components depend on this module only.

All offsets are Unicode code points, half-open [start, end), relative to the ORIGINAL text of
the field named by `field`; offsets are used internally for detection, rendering and audit.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FieldPath = str
Tier = Literal["high", "medium", "low", "public"]
Detector = Literal["rules", "presidio", "model"]
Action = Literal["redact", "retain"]
SegmentSource = Literal["purpose", "header", "subject", "body", "quoted_thread", "signature"]
DegradedReason = Literal["model_unavailable", "model_timeout", "model_output_unparseable",
                         "recognizer_failure"]
DegradedStage = Literal["detection", "assessment"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ---- request ---------------------------------------------------------------------------------
class EmailAddress(Strict):
    name: str | None = None
    address: str = Field(min_length=1, max_length=320)


class ThreadItem(Strict):
    message_id: str | None = None
    source: Literal["quoted_thread"] = "quoted_thread"
    text: str


class EmailIn(Strict):
    subject: str | None = None
    from_: EmailAddress | None = Field(default=None, alias="from")
    to: list[EmailAddress] = Field(default_factory=list)
    cc: list[EmailAddress] = Field(default_factory=list)
    body: str
    thread: list[ThreadItem] = Field(default_factory=list, max_length=50)


class Overrides(Strict):
    thresholds: dict[str, float] = Field(default_factory=dict)
    entity_types: dict[str, list[str]] = Field(default_factory=dict)
    allow_list: list[str] = Field(default_factory=list)
    deny_list: list[str] = Field(default_factory=list)


class PolicyOptions(Strict):
    overrides: Overrides = Field(default_factory=Overrides)


SESSION_ID_PATTERN = r"^sid_[0-7][0-9A-HJKMNP-TV-Z]{25}$"


class RedactionRequestV3(Strict):
    """One independent redaction; retention and backend choice belong to the server."""
    purpose: str = Field(min_length=1, max_length=2000)
    email: EmailIn
    policy: PolicyOptions = Field(default_factory=PolicyOptions)


class SessionRequestV3(Strict):
    """JSON session reference shared by V3 delete and restore requests."""
    session_id: str = Field(pattern=SESSION_ID_PATTERN)


class RestoreRequestV3(SessionRequestV3):
    text: str


class RedactionResponseV3(Strict):
    session_id: str
    redacted_email: dict
    redacted_purpose: str
    expires_at: str
    degraded: bool


class RestoreResponseV3(Strict):
    restored_text: str


# ---- component data --------------------------------------------------------------------------
class Segment(BaseModel):
    field: FieldPath
    text: str
    source: SegmentSource


class Candidate(BaseModel):
    field: FieldPath
    start: int
    end: int
    type: str
    detectors: set[Detector]
    hint: str | None = None  # e.g. term_list_match, allow_list


class ScoredCandidate(BaseModel):
    candidate: Candidate
    raw_score: float | None = None  # None = the model could not classify it
    is_private: bool | None = None
    calibrated: float | None = None  # filled by calibration; not returned to callers


class Decision(BaseModel):
    candidate: Candidate
    tier: Tier
    action: Action
    confidence: float | None
    reason: str  # stable code, never private text


class LabelState(BaseModel):
    """Per-redaction placeholder numbering so repeated entities keep one label within a request."""
    labels: dict[str, str] = Field(default_factory=dict)  # entity key -> placeholder
    counters: dict[str, int] = Field(default_factory=dict)  # placeholder type -> last number
    reserved: set[str] = Field(default_factory=set)  # original literal labels, canonical uppercase


# ---- response --------------------------------------------------------------------------------
class SpanOut(BaseModel):
    field: FieldPath
    start: int
    end: int
    type: str
    tier: Tier
    action: Action
    confidence: float | None
    detectors: list[Detector]
    reason: str


class PseudonymResult(BaseModel):
    redacted_purpose: str
    redacted_email: dict
    spans: list[SpanOut]
    mapping: dict[str, str]  # placeholder -> original; stays local


class RestoreOutcome(BaseModel):
    restore_decision: Literal["RESTORED", "BLOCKED"]
    restored_text: str | None = None
    unmatched_placeholders: list[str] = Field(default_factory=list)
    reason: str | None = None
