import pytest

from harness.runner import run_eval_set, run_query
from harness.sampling import generate_shared_samples
from harness.types import (
    CloudPricing,
    CloudResponse,
    ConfidenceResult,
    Query,
    Sample,
    SignalVariant,
)


class FakeLocalModel:
    """Returns k identical samples per call and records calls, so tests can
    assert the harness pays for the k generations exactly once per query."""

    def __init__(self, text: str = "local answer"):
        self.text = text
        self.calls: list[tuple[str, int, float]] = []

    def generate(self, query: Query, n: int, temperature: float) -> list[Sample]:
        self.calls.append((query.id, n, temperature))
        return [Sample(text=self.text) for _ in range(n)]


class FakeCloudModel:
    def __init__(self, text: str = "cloud answer", input_tokens: int = 100, output_tokens: int = 50):
        self.response = CloudResponse(text, input_tokens, output_tokens)
        self.calls: list[str] = []

    def generate(self, query: Query) -> CloudResponse:
        self.calls.append(query.id)
        return self.response


class ConstantSignal:
    def __init__(self, confidence: float, local_answer: str = "local answer"):
        self.confidence = confidence
        self.local_answer = local_answer

    def score(self, samples: list[Sample]) -> ConfidenceResult:
        return ConfidenceResult(confidence=self.confidence, local_answer=self.local_answer)


def exact_match(answer: str, gold: object) -> bool:
    return answer == gold


def variant(name: str, confidence: float, threshold: float = 0.5) -> SignalVariant:
    return SignalVariant(name=name, signal=ConstantSignal(confidence), threshold=threshold)


def by_config(results, system_config, variant_name=None):
    [row] = [r for r in results if r.system_config == system_config and r.variant == variant_name]
    return row


def test_generate_shared_samples_requests_exactly_k():
    model = FakeLocalModel()
    samples = generate_shared_samples(model, Query("q1", "2+2?", "4"), k=5, temperature=0.7)

    assert len(samples) == 5
    assert model.calls == [("q1", 5, 0.7)]


def test_generate_shared_samples_rejects_k_below_one():
    with pytest.raises(ValueError):
        generate_shared_samples(FakeLocalModel(), Query("q1", "p", "g"), k=0, temperature=0.7)


def test_cloud_is_called_once_per_query_even_when_no_variant_escalates():
    query = Query("q1", "p", "local answer")
    cloud = FakeCloudModel()

    run_query(query, [Sample("local answer")], 0.1, [variant("A", 0.9)], exact_match, cloud)

    assert cloud.calls == ["q1"]


def test_cloud_is_called_once_per_query_when_every_variant_escalates():
    query = Query("q1", "p", "cloud answer")
    cloud = FakeCloudModel()
    variants = [variant("A", 0.1), variant("B", 0.2), variant("C", 0.3)]

    run_query(query, [Sample("local answer")], 0.1, variants, exact_match, cloud)

    assert cloud.calls == ["q1"]


def test_one_pass_yields_all_three_system_configurations():
    query = Query("q1", "p", "cloud answer")
    results = run_query(
        query, [Sample("local answer")], 0.1, [variant("A", 0.9), variant("B", 0.1)],
        exact_match, FakeCloudModel(),
    )

    assert by_config(results, "local-only").is_correct is False
    assert by_config(results, "cloud-only").is_correct is True
    assert by_config(results, "hybrid", "A").is_correct is False
    assert by_config(results, "hybrid", "B").is_correct is True
    assert len(results) == 4


def test_hybrid_escalation_uses_cloud_answer_and_below_threshold_rule():
    query = Query("q1", "p", "cloud answer")
    results = run_query(
        query, [Sample("local answer")], 0.1, [variant("A", 0.1), variant("B", 0.9)],
        exact_match, FakeCloudModel(),
    )

    escalated = by_config(results, "hybrid", "A")
    stayed_local = by_config(results, "hybrid", "B")
    assert escalated.escalated and escalated.answer == "cloud answer"
    assert not stayed_local.escalated and stayed_local.answer == "local answer"
    assert stayed_local.local_is_correct is False


def test_cloud_tokens_and_cost_only_count_where_the_path_reached_the_cloud():
    query = Query("q1", "p", "x")
    pricing = CloudPricing(input_per_mtok=3.0, output_per_mtok=15.0)
    results = run_query(
        query, [Sample("local answer")], 0.1, [variant("A", 0.1), variant("B", 0.9)],
        exact_match, FakeCloudModel(input_tokens=1_000_000, output_tokens=1_000_000), pricing,
    )

    assert by_config(results, "cloud-only").cost_usd == pytest.approx(18.0)
    assert by_config(results, "hybrid", "A").cost_usd == pytest.approx(18.0)
    assert by_config(results, "hybrid", "A").cloud_input_tokens == 1_000_000
    assert by_config(results, "hybrid", "B").cost_usd == 0.0
    assert by_config(results, "hybrid", "B").cloud_input_tokens == 0
    assert by_config(results, "local-only").cost_usd == 0.0


def test_hybrid_latency_includes_cloud_time_only_when_escalated():
    query = Query("q1", "p", "x")
    results = run_query(
        query, [Sample("local answer")], 2.0, [variant("A", 0.1), variant("B", 0.9)],
        exact_match, FakeCloudModel(),
    )

    assert by_config(results, "local-only").latency_s == 2.0
    assert by_config(results, "hybrid", "B").latency_s >= 2.0
    assert by_config(results, "hybrid", "A").latency_s >= by_config(results, "hybrid", "B").latency_s


def test_run_eval_set_generates_samples_once_per_query_not_once_per_variant():
    queries = [Query("q1", "p1", "local answer"), Query("q2", "p2", "local answer")]
    variants = [variant("A", 0.9), variant("B", 0.9), variant("C", 0.9)]
    model = FakeLocalModel()
    cloud = FakeCloudModel()

    run = run_eval_set(queries, model, variants, exact_match, k=4, temperature=0.7, cloud_model=cloud)

    assert model.calls == [("q1", 4, 0.7), ("q2", 4, 0.7)]
    assert cloud.calls == ["q1", "q2"]
    assert len(run.for_config("local-only")) == 2
    assert len(run.for_config("cloud-only")) == 2
    assert all(len(run.for_config("hybrid", v)) == 2 for v in ("A", "B", "C"))
