"""The component bundle the orchestrator is wired with.

Each field is a plain callable with the signature below. Teammates replace stubs with a callable
with the same signature; nothing else in the service changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from .policy import Policy
from .types import (Candidate, Decision, EmailIn, LabelState, Overrides, PseudonymResult,
                    RestoreOutcome, ScoredCandidate, Segment)


class ContextStore(Protocol):
    version: str
    term_list: set[str]
    allow_list: set[str]

    def is_allowed(self, entity_type: str, text: str) -> bool: ...


class ModelClient(Protocol):
    """Raw local-model call. Raises ModelUnavailable / ModelTimeout. Owned by Service Eng."""
    version: str

    async def generate(self, prompt: str, *, prompt_name: str, deadline_ms: int) -> str: ...

    async def ping(self) -> bool: ...


@dataclass
class Components:
    # ---- segmentation + detection  (stubs/components.py has the full "REAL VERSION MUST" notes)
    # segment(purpose, email): split into per-field Segments tagged by source. Never raises.
    segment: Callable[[str, EmailIn], list[Segment]]
    # detect_rules(segments, ctx): regex/checksum/term-list candidates. Sync, CPU-only, runs in a
    # worker thread. An exception here means HTTP 500 (no safe fallback).
    detect_rules: Callable[[list[Segment], ContextStore], list[Candidate]]
    # detect_presidio(segments): Presidio candidates. Sync. An exception means a degraded response.
    detect_presidio: Callable[[list[Segment]], list[Candidate]]
    # merge_candidates(*lists): union by character position, overlaps become one span.
    merge_candidates: Callable[..., list[Candidate]]
    # ---- prompts and parsing. parse_* must raise ModelOutputUnparseable on a bad model reply.
    # Two independent prompts: detection (find spans) and assessment (judge each in context).
    build_detection_prompt: Callable[[list[Segment]], str]
    parse_detection: Callable[[str, list[Segment]], list[Candidate]]
    build_assessment_prompt: Callable[[list[Segment], list[Candidate]], str]
    parse_assessment: Callable[[str, list[Candidate]], list[ScoredCandidate]]
    # calibrate(raw): pure, monotonic map from raw model score to calibrated score in [0, 1].
    calibrate: Callable[[float], float]
    # ---- decision + pseudonymisation
    # decide(...): tier x threshold on the calibrated score. Pure. "The model proposes, code decides."
    decide: Callable[[list[ScoredCandidate], Policy, Overrides, ContextStore], list[Decision]]
    # decide_degraded(...): redact every candidate, confidence None (fail-safe path).
    decide_degraded: Callable[[list[Candidate], Policy], list[Decision]]
    # pseudonymize(...): [TYPE_n] placeholders, mapping stays local, same entity = same label.
    # Reserve original literal labels and identity-map them so roundtrips cannot rewrite literals.
    pseudonymize: Callable[[str, EmailIn, list[Decision], LabelState], PseudonymResult]
    # restore(reply, mapping): exact-match placeholders; BLOCKED if any is unknown.
    restore: Callable[[str, dict[str, str]], RestoreOutcome]
    # ---- data + versions (versions are retained in audit and reported by /v3/info)
    policy: Policy
    context_store: ContextStore
    detection_prompt_version: str
    assessment_prompt_version: str
