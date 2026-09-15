from harness.types import ConfidenceResult, ConfigSpec, Query, Sample
from harness.runner import run_eval_set, run_query
from harness.sampling import generate_shared_samples


class FakeLocalModel:
    """Returns one fixed sample per generate() call, and counts calls so
    tests can assert the harness pays for k generations exactly once."""

    def __init__(self, text: str = "local answer"):
        self.text = text
        self.calls: list[tuple[str, int, float]] = []

    def generate(self, query: Query, n: int, temperature: float) -> list[Sample]:
        self.calls.append((query.id, n, temperature))
        return [Sample(text=self.text) for _ in range(n)]


class FakeCloudModel:
    def __init__(self, answer: str = "cloud answer"):
        self.answer = answer
        self.calls: list[str] = []

    def generate(self, query: Query) -> str:
        self.calls.append(query.id)
        return self.answer


class ConstantSignal:
    """Confidence signal stub: always reports the same score and answer,
    regardless of the sample batch it's handed."""

    def __init__(self, confidence: float, local_answer: str = "local answer"):
        self.confidence = confidence
        self.local_answer = local_answer

    def score(self, samples: list[Sample]) -> ConfidenceResult:
        return ConfidenceResult(confidence=self.confidence, local_answer=self.local_answer)


def exact_match(answer: str, gold: object) -> bool:
    return answer == gold


def test_generate_shared_samples_requests_exactly_k():
    model = FakeLocalModel()
    query = Query(id="q1", prompt="2+2?", gold="4")

    samples = generate_shared_samples(model, query, k=5, temperature=0.7)

    assert len(samples) == 5
    assert model.calls == [("q1", 5, 0.7)]


def test_generate_shared_samples_rejects_k_below_one():
    model = FakeLocalModel()
    query = Query(id="q1", prompt="2+2?", gold="4")

    try:
        generate_shared_samples(model, query, k=0, temperature=0.7)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_run_query_below_threshold_escalates_and_uses_cloud_answer():
    query = Query(id="q1", prompt="2+2?", gold="cloud answer")
    samples = [Sample(text="local answer")]
    config = ConfigSpec(name="A", signal=ConstantSignal(confidence=0.1), threshold=0.5)
    cloud = FakeCloudModel(answer="cloud answer")

    [result] = run_query(query, samples, [config], exact_match, cloud_model=cloud)

    assert result.escalated is True
    assert result.final_answer == "cloud answer"
    assert result.is_correct is True
    assert cloud.calls == ["q1"]


def test_run_query_above_threshold_stays_local_and_skips_cloud():
    query = Query(id="q1", prompt="2+2?", gold="local answer")
    samples = [Sample(text="local answer")]
    config = ConfigSpec(name="A", signal=ConstantSignal(confidence=0.9), threshold=0.5)
    cloud = FakeCloudModel()

    [result] = run_query(query, samples, [config], exact_match, cloud_model=cloud)

    assert result.escalated is False
    assert result.final_answer == "local answer"
    assert result.is_correct is True
    assert cloud.calls == []


def test_run_query_calls_cloud_at_most_once_even_if_every_config_escalates():
    query = Query(id="q1", prompt="2+2?", gold="cloud answer")
    samples = [Sample(text="local answer")]
    configs = [
        ConfigSpec(name="A", signal=ConstantSignal(confidence=0.1), threshold=0.5),
        ConfigSpec(name="B", signal=ConstantSignal(confidence=0.2), threshold=0.5),
        ConfigSpec(name="C", signal=ConstantSignal(confidence=0.3), threshold=0.5),
    ]
    cloud = FakeCloudModel(answer="cloud answer")

    results = run_query(query, samples, configs, exact_match, cloud_model=cloud)

    assert len(results) == 3
    assert all(r.escalated for r in results)
    assert cloud.calls == ["q1"]


def test_run_eval_set_generates_samples_once_per_query_not_once_per_config():
    queries = [Query(id="q1", prompt="p1", gold="local answer")]
    configs = [
        ConfigSpec(name="A", signal=ConstantSignal(confidence=0.9), threshold=0.5),
        ConfigSpec(name="B", signal=ConstantSignal(confidence=0.9), threshold=0.5),
        ConfigSpec(name="C", signal=ConstantSignal(confidence=0.9), threshold=0.5),
    ]
    model = FakeLocalModel()

    run = run_eval_set(queries, model, configs, exact_match, k=4, temperature=0.7)

    assert model.calls == [("q1", 4, 0.7)]
    assert set(run.results.keys()) == {"A", "B", "C"}
    assert all(len(rows) == 1 for rows in run.results.values())
