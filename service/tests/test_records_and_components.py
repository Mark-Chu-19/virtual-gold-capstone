import pytest

from vg_redactor.contracts.errors import CapacityExhausted, RecordGone, RecordNotFound
from vg_redactor.contracts.types import Candidate, EmailIn
from vg_redactor.records.store import RecordStore
from vg_redactor.stubs.components import merge_candidates, segment, pseudonymize
from vg_redactor.contracts.types import Decision, LabelState


class Clock:
    t = 0.0
    def __call__(self): return self.t


def test_store_ttl_capacity_tombstones():
    clk = Clock(); removed = []
    s = RecordStore(2, 100, clock=clk, on_remove=removed.append)
    s.reserve("a"); s.commit("a", {"[X_1]": "v"}, 10, None)
    s.reserve("b"); s.commit("b", None, 50, None)
    with pytest.raises(CapacityExhausted):
        s.reserve("c")
    s.release("c")
    clk.t = 11
    with pytest.raises(RecordGone):
        s.get("a")
    assert removed == ["expired"]
    s.reserve("c")                                  # slot freed by expiry
    assert s.delete("b") is True and s.delete("b") is False
    with pytest.raises(RecordGone):
        s.get("b")
    with pytest.raises(RecordNotFound):
        s.get("zzz")
    clk.t = 500                                     # tombstones are bounded by max_ttl
    s.sweep()
    with pytest.raises(RecordNotFound):
        s.get("b")


def test_delete_unknown_id_does_not_create_tombstones():
    removed = []
    store = RecordStore(1, 100, on_remove=removed.append)
    for rid in ("unknown-a", "unknown-b", "unknown-c"):
        assert store.delete(rid) is False
        with pytest.raises(RecordNotFound):
            store.get(rid)
    assert store._tombstones == {}
    assert removed == []


def test_repeated_delete_does_not_extend_tombstone_retention():
    clk = Clock(); removed = []
    store = RecordStore(1, 100, clock=clk, on_remove=removed.append)
    store.reserve("a")
    rec = store.commit("a", {"[X_1]": "value"}, 100, None)
    assert store.delete("a") is True
    assert rec.mapping is None
    clk.t = 90
    assert store.delete("a") is False
    with pytest.raises(RecordGone):
        store.get("a")
    clk.t = 101
    with pytest.raises(RecordNotFound):
        store.get("a")
    assert removed == ["deleted"]


def test_session_state_survives_delete_until_latest_record_ttl():
    clk = Clock()
    store = RecordStore(2, 100, clock=clk)
    state = store.label_state("session", 10)
    state.labels["PERSON|example"] = "[PERSON_1]"
    state.counters["PERSON"] = 1
    for rid, ttl in (("a", 10), ("b", 50)):
        store.reserve(rid)
        store.commit(rid, {"[PERSON_1]": "Example"}, ttl, "session")
    assert store.delete("a") is True
    assert store.delete("b") is True
    clk.t = 11
    store.sweep()
    assert store._sessions["session"][0] is state
    assert state.labels == {"PERSON|example": "[PERSON_1]"}
    clk.t = 50
    store.sweep()
    assert "session" not in store._sessions
    fresh = store.label_state("session", 10)
    assert fresh.labels == {} and fresh.counters == {}


def test_merge_unions_overlaps():
    a = Candidate(field="f", start=0, end=5, type="PERSON", detectors={"rules"})
    b = Candidate(field="f", start=3, end=9, type="PERSON", detectors={"model"})
    c = Candidate(field="f", start=20, end=22, type="CITY", detectors={"presidio"})
    out = merge_candidates([a], [b, c])
    assert [(x.start, x.end, sorted(x.detectors)) for x in out] == [(0, 9, ["model", "rules"]),
                                                                    (20, 22, ["presidio"])]


def test_pseudonymize_offsets_on_unicode_and_multiple_spans():
    email = EmailIn(body="Héllo 😀 call 202-555-0102 or 202-555-0102 later", from_=None)
    body = email.body
    s1 = body.index("202"); s2 = body.rindex("202")
    ds = [Decision(candidate=Candidate(field="email.body", start=i, end=i + 12, type="PHONE_PERSONAL",
                                       detectors={"rules"}), tier="medium", action="redact",
                   confidence=0.9, reason="meets_threshold") for i in (s1, s2)]
    out = pseudonymize("p", email, ds, LabelState())
    assert out.redacted_email["body"] == "Héllo 😀 call [PHONE_1] or [PHONE_1] later"
    assert out.mapping == {"[PHONE_1]": "202-555-0102"}


def test_segment_tags_sources():
    email = EmailIn(body="b", subject="s", thread=[{"text": "t"}])
    srcs = {sg.field: sg.source for sg in segment("p", email)}
    assert srcs == {"purpose": "purpose", "email.subject": "subject", "email.body": "body",
                    "email.thread[0].text": "quoted_thread"}


async def test_stub_model_fault_file(tmp_path):
    import pytest as _pytest
    from vg_redactor.contracts.errors import ModelTimeout, ModelUnavailable
    from vg_redactor.model.client import StubModelClient
    f = tmp_path / "fault"
    m = StubModelClient(str(f))
    assert await m.ping() and await m.generate("DETECT\n[]", prompt_name="detection", deadline_ms=100) == "[]"
    f.write_text("down")
    assert not await m.ping()
    with _pytest.raises(ModelUnavailable):
        await m.generate("DETECT\n[]", prompt_name="detection", deadline_ms=100)
    f.write_text("timeout")
    with _pytest.raises(ModelTimeout):
        await m.generate("DETECT\n[]", prompt_name="detection", deadline_ms=100)
    f.write_text("garbage")
    assert (await m.generate("DETECT\n[]", prompt_name="detection", deadline_ms=100)).startswith("<<")
    f.unlink()
    assert await m.ping()
