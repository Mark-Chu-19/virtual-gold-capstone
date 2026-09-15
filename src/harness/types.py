"""Shared data structures for the confidence-scoring harness.

See docs/confidence-harness-design-en.md section 4 for the design this
implements: one shared sampling pass per query, three confidence-signal
configurations (A/B/C) derived from that same pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Query:
    """One evaluation item. `gold` is whatever `correctness()` needs to
    compare against — a string for exact-match, a letter for multiple
    choice, a label for yes/no tasks, etc."""

    id: str
    prompt: str
    gold: Any


@dataclass(frozen=True)
class Sample:
    """One generation from the local model. `token_logprobs` and
    `hidden_state` are optional because not every signal needs them —
    token-probability confidence needs `token_logprobs`, a Semantic
    Entropy Probe needs `hidden_state`, self-consistency needs neither."""

    text: str
    token_logprobs: list[float] | None = None
    hidden_state: Any | None = None


@dataclass(frozen=True)
class ConfidenceResult:
    """What a confidence signal reports for one query: a score used to
    decide escalation, and the answer this config would give if it did
    *not* escalate (sample #1's text for A/B, the majority-vote answer
    for a self-consistency-style C)."""

    confidence: float
    local_answer: str


class ConfidenceSignal(Protocol):
    """Interface each signal branch (feat/signal-token-logprob,
    feat/signal-sep-probe, feat/signal-sampling-ensemble) implements.

    `samples` is always the full shared batch; a signal that only needs
    sample #1 (Config A, B) simply ignores the rest.
    """

    def score(self, samples: list[Sample]) -> ConfidenceResult: ...


@dataclass(frozen=True)
class ConfigSpec:
    """One of the three configurations (A/B/C) from design doc section 4.1."""

    name: str
    signal: ConfidenceSignal
    threshold: float


@dataclass(frozen=True)
class ConfigResult:
    """One row of the eventual 3x6 result table (design doc section 4.2),
    minus the metrics that get aggregated across many queries — this is
    the per-query record eval/calibration-metrics will consume."""

    query_id: str
    config_name: str
    confidence: float
    escalated: bool
    final_answer: str
    is_correct: bool
    local_answer: str
    local_is_correct: bool


@dataclass
class HarnessRun:
    """Accumulated per-query results for one evaluation set, one row list
    per configuration name."""

    results: dict[str, list[ConfigResult]] = field(default_factory=dict)

    def add(self, result: ConfigResult) -> None:
        self.results.setdefault(result.config_name, []).append(result)
