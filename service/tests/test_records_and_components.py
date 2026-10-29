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
    s.reserve("a"); s.commit("a", {"[X_1]": "v"}, 10, tenant_id="tenant")
    s.reserve("b"); s.commit("b", {}, 50, tenant_id="tenant")
    with pytest.raises(CapacityExhausted):
        s.reserve("c")
    s.release("c")
    clk.t = 11
    with pytest.raises(RecordGone):
        s.get("a", tenant_id="tenant")
    assert removed == ["expired"]
    s.reserve("c")                                  # slot freed by expiry
    assert s.delete("b", tenant_id="tenant") is True and s.delete("b", tenant_id="tenant") is False
    with pytest.raises(RecordGone):
        s.get("b", tenant_id="tenant")
    with pytest.raises(RecordNotFound):
        s.get("zzz", tenant_id="tenant")
    clk.t = 500                                     # tombstones are bounded by max_ttl
    s.sweep()
    with pytest.raises(RecordNotFound):
        s.get("b", tenant_id="tenant")


def test_delete_unknown_id_does_not_create_tombstones():
    removed = []
    store = RecordStore(1, 100, on_remove=removed.append)
    for rid in ("unknown-a", "unknown-b", "unknown-c"):
        assert store.delete(rid, tenant_id="tenant") is False
        with pytest.raises(RecordNotFound):
            store.get(rid, tenant_id="tenant")
    assert store._tombstones == {}
    assert removed == []


def test_repeated_delete_does_not_extend_tombstone_retention():
    clk = Clock(); removed = []
    store = RecordStore(1, 100, clock=clk, on_remove=removed.append)
    store.reserve("a")
    rec = store.commit("a", {"[X_1]": "value"}, 100, tenant_id="tenant")
    assert store.delete("a", tenant_id="tenant") is True
    assert rec.mapping is None
    clk.t = 90
    assert store.delete("a", tenant_id="tenant") is False
    with pytest.raises(RecordGone):
        store.get("a", tenant_id="tenant")
    clk.t = 101
    with pytest.raises(RecordNotFound):
        store.get("a", tenant_id="tenant")
    assert removed == ["deleted"]


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
