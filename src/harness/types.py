"""Shared data structures for the confidence-scoring harness.

Vocabulary follows docs/confidence-harness-design-en.md: architecture §7's
three *system configurations* (local-only, hybrid, cloud-only) come out of
one sampling pass; A/B/C are *signal variants* that only exist inside the
hybrid configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

SystemConfig = Literal["local-only", "cloud-only", "hybrid"]


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
class CloudResponse:
    """Cloud answer plus the token usage needed to price it."""

    text: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
# TODO(cloud provider, todo/TODO.md A6): no default rates; supply the chosen provider's prices.
class CloudPricing:
    """Dollars per million tokens, used to turn token usage into cost per query."""

    input_per_mtok: float
    output_per_mtok: float

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_per_mtok + output_tokens * self.output_per_mtok
        ) / 1_000_000


@dataclass(frozen=True)
class ConfidenceResult:
    """What a signal variant reports for one query: a score used to decide
    escalation, and the answer the variant gives if it does *not* escalate
    (sample #1's text for A/B, the majority-vote answer for a
    self-consistency-style C)."""

    confidence: float
    local_answer: str


class ConfidenceSignal(Protocol):
    """Interface each signal branch (feat/signal-token-logprob,
    feat/signal-sep-probe, feat/signal-sampling-ensemble) implements.

    `samples` is always the full shared batch; a signal that only needs
    sample #1 (variants A, B) simply ignores the rest.
    """

    def score(self, samples: list[Sample]) -> ConfidenceResult: ...


@dataclass(frozen=True)
class SignalVariant:
    """One of the hybrid configuration's confidence signals (A/B/C)."""

    name: str
    signal: ConfidenceSignal
    threshold: float


@dataclass(frozen=True)
class QueryResult:
    """Per-query record for one system configuration (and, for hybrid, one
    signal variant). eval/calibration-metrics aggregates these into the
    §7 system metrics and the per-variant confidence metrics.

    Latency is wall-clock seconds for this configuration's path: local
    generation, plus signal scoring and the cloud call where the path
    includes them. Cloud tokens and `cost_usd` are zero when the path
    never reached the cloud.
    """

    query_id: str
    system_config: SystemConfig
    variant: str | None
    answer: str
    is_correct: bool
    local_answer: str | None
    local_is_correct: bool | None
    confidence: float | None
    escalated: bool
    latency_s: float
    cloud_input_tokens: int
    cloud_output_tokens: int
    cost_usd: float | None


@dataclass
class HarnessRun:
    """Every per-query record from one evaluation set."""

    results: list[QueryResult] = field(default_factory=list)

    def for_config(
        self, system_config: SystemConfig, variant: str | None = None
    ) -> list[QueryResult]:
        return [
            r
            for r in self.results
            if r.system_config == system_config and r.variant == variant
        ]
