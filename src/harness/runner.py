"""One-pass execution flow: design doc section 4.3, translated from
pseudocode into a typed implementation.

This is scaffolding only. It knows nothing about *how* a signal scores
confidence (feat/signal-* branches supply that via `ConfidenceSignal`)
and nothing about *what counts as correct* (eval/benchmark-loaders
supplies `correctness_fn`). What it owns:

- generating the shared sample batch once per query (harness.sampling)
- calling each config's signal and applying its escalation threshold
- calling the cloud model at most once per query, even if multiple
  configs escalate
- assembling one ConfigResult per (query, config) pair
"""

from __future__ import annotations

from typing import Callable, Sequence

from harness.cloud import CloudModel, UnconfiguredCloudModel
from harness.escalation import should_escalate
from harness.local_model import LocalModel
from harness.sampling import generate_shared_samples
from harness.types import ConfigResult, ConfigSpec, HarnessRun, Query, Sample

CorrectnessFn = Callable[[str, object], bool]


def run_query(
    query: Query,
    samples: Sequence[Sample],
    configs: Sequence[ConfigSpec],
    correctness_fn: CorrectnessFn,
    cloud_model: CloudModel = UnconfiguredCloudModel(),
) -> list[ConfigResult]:
    """Score every config against one query's shared sample batch,
    escalating to the cloud at most once, and return one ConfigResult
    per config."""
    scored = {cfg.name: cfg.signal.score(list(samples)) for cfg in configs}
    escalations = {
        cfg.name: should_escalate(scored[cfg.name].confidence, cfg.threshold)
        for cfg in configs
    }

    cloud_answer: str | None = None
    if any(escalations.values()):
        cloud_answer = cloud_model.generate(query)

    results: list[ConfigResult] = []
    for cfg in configs:
        confidence_result = scored[cfg.name]
        escalated = escalations[cfg.name]
        final_answer = cloud_answer if escalated else confidence_result.local_answer
        assert final_answer is not None  # escalated implies cloud_answer was set
        results.append(
            ConfigResult(
                query_id=query.id,
                config_name=cfg.name,
                confidence=confidence_result.confidence,
                escalated=escalated,
                final_answer=final_answer,
                is_correct=correctness_fn(final_answer, query.gold),
                local_answer=confidence_result.local_answer,
                local_is_correct=correctness_fn(
                    confidence_result.local_answer, query.gold
                ),
            )
        )
    return results


def run_eval_set(
    queries: Sequence[Query],
    local_model: LocalModel,
    configs: Sequence[ConfigSpec],
    correctness_fn: CorrectnessFn,
    k: int,
    temperature: float,
    cloud_model: CloudModel = UnconfiguredCloudModel(),
) -> HarnessRun:
    run = HarnessRun()
    for query in queries:
        samples = generate_shared_samples(local_model, query, k, temperature)
        for result in run_query(query, samples, configs, correctness_fn, cloud_model):
            run.add(result)
    return run
