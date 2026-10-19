"""Shared data types (contract 0.4.2). Components depend on this module only.

All offsets are Unicode code points, half-open [start, end), relative to the ORIGINAL text of
the field named by `field` (see FieldPath syntax in service-interfaces-v0.4.2-en.md section 3.3).
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


class MappingOptions(Strict):
    retain: bool = False
    ttl_seconds: int | None = Field(default=None, ge=1)


class Overrides(Strict):
    thresholds: dict[str, float] = Field(default_factory=dict)
    entity_types: dict[str, list[str]] = Field(default_factory=dict)
    allow_list: list[str] = Field(default_factory=list)
    deny_list: list[str] = Field(default_factory=list)


class PolicyOptions(Strict):
    overrides: Overrides = Field(default_factory=Overrides)


class RedactionRequest(Strict):
    purpose: str = Field(min_length=1, max_length=2000)
    purpose_source: str | None = None
    email: EmailIn
    source_context: dict | None = None  # reserved, ignored in 0.4
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    mapping: MappingOptions = Field(default_factory=MappingOptions)
    policy: PolicyOptions = Field(default_factory=PolicyOptions)


class RestoreRequest(Strict):
    reply_text: str


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
    """Per-session placeholder numbering so one entity keeps one label across requests."""
    labels: dict[str, str] = Field(default_factory=dict)  # entity key -> placeholder
    counters: dict[str, int] = Field(default_factory=dict)  # placeholder type -> last number


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


class RecordInfo(BaseModel):
    expires_at: str
    mapping_retained: bool


class RedactionResponse(BaseModel):
    request_id: str
    degraded: bool
    degraded_reason: DegradedReason | None = None
    degraded_stage: DegradedStage | None = None
    redacted_email: dict
    redacted_purpose: str
    spans: list[SpanOut]
    record: RecordInfo
    policy_version: str
    model_version: str
    prompt_versions: dict[str, str]
    context_store_version: str
