"""Shared data types (contract 0.4.2). Components depend on this module only.

All offsets are Unicode code points, half-open [start, end), relative to the ORIGINAL text of
the field named by `field` (see FieldPath syntax in service-interfaces-v0.4.2-en.md section 3.3).
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    # Legacy V1 only: this client-provided session_id shares label numbering across calls.
    # V3 instead issues its own per-redaction session_id and accepts no client session state.
    purpose: str = Field(min_length=1, max_length=2000)
    purpose_source: str | None = None
    email: EmailIn
    source_context: dict | None = None  # reserved, ignored in 0.4
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    mapping: MappingOptions = Field(default_factory=MappingOptions)
    policy: PolicyOptions = Field(default_factory=PolicyOptions)


class RestoreRequest(Strict):
    reply_text: str


class TokenizationOptions(Strict):
    mode: Literal["mapping", "aes_siv"] | None = None
    ttl_seconds: int | None = Field(default=None, ge=1)


class EmailAddressV2(EmailAddress):
    # An encrypted 320-character address can exceed the original address field limit.
    address: str = Field(min_length=1, max_length=4096)

    @field_validator("address")
    @classmethod
    def address_or_token(cls, value):
        if len(value) > 320 and not value.startswith("[VG:"):
            raise ValueError("Address exceeds plaintext limit")
        return value


class EmailInV2(EmailIn):
    from_: EmailAddressV2 | None = Field(default=None, alias="from")
    to: list[EmailAddressV2] = Field(default_factory=list)
    cc: list[EmailAddressV2] = Field(default_factory=list)


class RedactionRequestV2(Strict):
    purpose: str = Field(min_length=1, max_length=32768)
    purpose_source: str | None = None
    email: EmailInV2
    group_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    tokenization: TokenizationOptions = Field(default_factory=TokenizationOptions)
    policy: PolicyOptions = Field(default_factory=PolicyOptions)
    include: list[Literal["service_info"]] = Field(default_factory=list, max_length=1)

    @field_validator("purpose")
    @classmethod
    def purpose_or_tokens(cls, value):
        # Existing tokens may expand a valid purpose beyond its original plaintext limit.
        if len(re.sub(r"\[VG[^\]]*\]", "", value)) > 2000:
            raise ValueError("Purpose exceeds plaintext limit")
        return value


class RestoreRequestV2(Strict):
    text: str


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
    record: RecordInfo | None = None
    policy_version: str
    model_version: str
    prompt_versions: dict[str, str]
    context_store_version: str
