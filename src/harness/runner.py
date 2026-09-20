"""One-pass execution flow: design doc §4.3.

Scaffolding only. It knows nothing about *how* a signal scores confidence
(feat/signal-* branches supply `ConfidenceSignal`s) or *what counts as
correct* (eval/benchmark-loaders supplies `correctness_fn`). It owns:

- generating the shared k-sample batch once per query
- calling the cloud once per query, unconditionally, and reusing the answer
- producing local-only, cloud-only and one hybrid record per signal variant
  from that single pass, with wall-clock latency and cloud cost
"""

from __future__ import annotations

import time
from typing import Callable, Sequence

from harness.cloud import CloudModel, UnconfiguredCloudModel
from harness.escalation import should_escalate
from harness.local_model import LocalModel
from harness.sampling import generate_shared_samples
from harness.types import (
    CloudPricing,
    HarnessRun,
    Query,
    QueryResult,
    Sample,
    SignalVariant,
)

CorrectnessFn = Callable[[str, object], bool]


def _cost(pricing: CloudPricing | None, input_tokens: int, output_tokens: int) -> float | None:
    return pricing.cost(input_tokens, output_tokens) if pricing else None


def run_query(
    query: Query,
    samples: Sequence[Sample],
    local_latency_s: float,
    variants: Sequence[SignalVariant],
    correctness_fn: CorrectnessFn,
    cloud_model: CloudModel = UnconfiguredCloudModel(),
    pricing: CloudPricing | None = None,
) -> list[QueryResult]:
    """Return the local-only record, the cloud-only record, and one hybrid
    record per variant for one query. The cloud is called exactly once."""
    cloud_start = time.perf_counter()
    cloud = cloud_model.generate(query)
    cloud_latency_s = time.perf_counter() - cloud_start
    cloud_cost = _cost(pricing, cloud.input_tokens, cloud.output_tokens)

    local_text = samples[0].text
    local_correct = correctness_fn(local_text, query.gold)

    results = [
        QueryResult(
            query_id=query.id,
            system_config="local-only",
            variant=None,
            answer=local_text,
            is_correct=local_correct,
            local_answer=local_text,
            local_is_correct=local_correct,
            confidence=None,
            escalated=False,
            latency_s=local_latency_s,
            cloud_input_tokens=0,
            cloud_output_tokens=0,
            cost_usd=_cost(pricing, 0, 0),
        ),
        QueryResult(
            query_id=query.id,
            system_config="cloud-only",
            variant=None,
            answer=cloud.text,
            is_correct=correctness_fn(cloud.text, query.gold),
            local_answer=None,
            local_is_correct=None,
            confidence=None,
            escalated=True,
            latency_s=cloud_latency_s,
            cloud_input_tokens=cloud.input_tokens,
            cloud_output_tokens=cloud.output_tokens,
            cost_usd=cloud_cost,
        ),
    ]

    for variant in variants:
        score_start = time.perf_counter()
        scored = variant.signal.score(list(samples))
        score_latency_s = time.perf_counter() - score_start
        escalated = should_escalate(scored.confidence, variant.threshold)
        answer = cloud.text if escalated else scored.local_answer
        results.append(
            QueryResult(
                query_id=query.id,
                system_config="hybrid",
                variant=variant.name,
                answer=answer,
                is_correct=correctness_fn(answer, query.gold),
                local_answer=scored.local_answer,
                local_is_correct=correctness_fn(scored.local_answer, query.gold),
                confidence=scored.confidence,
                escalated=escalated,
                latency_s=local_latency_s
                + score_latency_s
                + (cloud_latency_s if escalated else 0.0),
                cloud_input_tokens=cloud.input_tokens if escalated else 0,
                cloud_output_tokens=cloud.output_tokens if escalated else 0,
                cost_usd=cloud_cost if escalated else _cost(pricing, 0, 0),
            )
        )
    return results


def run_eval_set(
    queries: Sequence[Query],
    local_model: LocalModel,
    variants: Sequence[SignalVariant],
    correctness_fn: CorrectnessFn,
    k: int,
    temperature: float,
    cloud_model: CloudModel = UnconfiguredCloudModel(),
    pricing: CloudPricing | None = None,
) -> HarnessRun:
    run = HarnessRun()
    for query in queries:
        local_start = time.perf_counter()
        samples = generate_shared_samples(local_model, query, k, temperature)
        local_latency_s = time.perf_counter() - local_start
        run.results.extend(
            run_query(
                query,
                samples,
                local_latency_s,
                variants,
                correctness_fn,
                cloud_model,
                pricing,
            )
        )
    return run
