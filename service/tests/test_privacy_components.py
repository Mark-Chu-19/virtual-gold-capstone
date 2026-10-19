"""Privacy Research components: unit tests, plus the HTTP API with them swapped in."""
import shutil

import httpx
import pytest

from vg_redactor.api.app import create_app
from vg_redactor.contracts.policy import Policy
from vg_redactor.contracts.types import Candidate, Overrides, ScoredCandidate, Segment
from vg_redactor.main import build_components
from vg_redactor.obs.metrics import Metrics
from vg_redactor.privacy import (FileContextStore, decide, detect_rules, fit_table, make_calibrate,
                                 make_merge)
from vg_redactor.settings import CONFIG_DIR

from conftest import EMAIL_REQ, HEADERS

try:
    import presidio_analyzer  # noqa: F401
    HAS_PRESIDIO = True
except ImportError:
    HAS_PRESIDIO = False

POLICY = Policy.load(CONFIG_DIR / "policy.yaml")


def ctx(terms=(), allow=()):
    return FileContextStore("ctx-test", set(terms), set(allow), POLICY.high_types())


def body(text):
    return [Segment(field="email.body", text=text, source="body")]


def found(text, **kw):
    return [(text[c.start:c.end], c.type) for c in detect_rules(body(text), ctx(**kw))]


# ---- detect_rules ----------------------------------------------------------------------------
def test_rules_find_fixed_shape_items():
    got = found("Cell 412-555-0182 x4521, mail dana@acme.com, SSN 123-45-6789, "
                "card 4111 1111 1111 1111.")
    assert ("412-555-0182", "PHONE_PERSONAL") in got
    assert ("x4521", "PHONE_PERSONAL") in got
    assert ("dana@acme.com", "EMAIL_PERSONAL") in got
    assert ("123-45-6789", "GOV_ID") in got
    assert ("4111 1111 1111 1111", "CARD_NUMBER") in got


def test_card_numbers_need_a_valid_luhn_checksum():
    assert not [t for t, k in found("ref 4111 1111 1111 1112") if k == "CARD_NUMBER"]


def test_amounts():
    text = "Reserve up $1.84M; budget € 300k; USD 5,000 fee; 2.4 million dollars; 300 euros."
    assert [t for t, k in found(text) if k == "AMOUNT"] == [
        "$1.84M", "€ 300k", "USD 5,000", "2.4 million dollars", "300 euros"]
    assert found("In 2024 we hired 3 people and shipped 1,000 units.") == []


def test_term_list_is_case_insensitive_and_whole_word():
    got = found("Blue Harbor slips; blue harbor again; Harborview is fine.",
                terms={"Blue Harbor", "Harbor"})
    assert [t for t, k in got if k == "CODENAME"] == ["Blue Harbor", "blue harbor"]


def test_offsets_index_each_field():
    segs = [Segment(field="purpose", text="Call 202-555-0102", source="purpose"),
            Segment(field="email.thread[0].text", text="xx 202-555-0102", source="quoted_thread")]
    cands = detect_rules(segs, ctx())
    assert {(c.field, c.start, c.end) for c in cands} == {
        ("purpose", 5, 17), ("email.thread[0].text", 3, 15)}


# ---- names from the header -------------------------------------------------------------------
def header_and_body(body_text, **names):
    segs = [Segment(field=f, text=t, source="header") for f, t in names.items()]
    return segs + [Segment(field="email.body", text=body_text, source="body")]


def body_names(segs):
    text = next(s.text for s in segs if s.field == "email.body")
    return [text[c.start:c.end] for c in detect_rules(segs, ctx())
            if c.field == "email.body" and c.type == "PERSON"]


def test_sign_off_and_greeting_names_come_from_the_header():
    segs = header_and_body("Hi Tom,\nPlease ask Ms. Whitfield to call.\n- Dana",
                           **{"email.from.name": "Dana Whitfield", "email.to[0].name": "Tom Reyes"})
    assert body_names(segs) == ["Tom", "Whitfield", "Dana"]


def test_common_word_names_only_match_as_part_of_the_full_name():
    segs = header_and_body("Will Smith says I will call. Will?",
                           **{"email.from.name": "Will Smith"})
    assert body_names(segs) == ["Will Smith"]


def test_team_mailboxes_are_not_treated_as_people():
    segs = header_and_body("Contact Support or the Team.",
                           **{"email.to[0].name": "Support Team"})
    assert body_names(segs) == []


def test_header_names_are_matched_case_sensitively():
    segs = header_and_body("the rose garden; Rose agreed.", **{"email.cc[0].name": "Rosa Diaz"})
    assert body_names(segs) == []


# ---- merge -----------------------------------------------------------------------------------
def test_merge_keeps_the_stricter_type_and_does_not_mutate_inputs():
    a = Candidate(field="email.body", start=0, end=10, type="CITY", detectors={"presidio"})
    b = Candidate(field="email.body", start=5, end=14, type="HEALTH", detectors={"model"},
                  hint="x")
    merged = make_merge(POLICY)([a], [b])
    assert len(merged) == 1
    m = merged[0]
    assert (m.start, m.end, m.type, m.detectors, m.hint) == (0, 14, "HEALTH", {"presidio", "model"}, "x")
    assert (a.end, a.type, a.detectors) == (10, "CITY", {"presidio"})


def test_merge_keeps_fields_apart_and_sorts():
    a = Candidate(field="purpose", start=0, end=4, type="PERSON", detectors={"rules"})
    b = Candidate(field="email.body", start=0, end=4, type="PERSON", detectors={"rules"})
    assert [c.field for c in make_merge(POLICY)([a, b])] == ["email.body", "purpose"]


# ---- calibration -----------------------------------------------------------------------------
def test_identity_until_fitted():
    assert make_calibrate(None)(0.37) == 0.37


def test_fit_matches_the_proposal_example():
    scores = [0.95] * 200 + [0.8] * 100 + [0.6] * 50 + [0.2] * 150
    labels = ([True] * 140 + [False] * 60 + [True] * 50 + [False] * 50
              + [True] * 15 + [False] * 35 + [True] * 15 + [False] * 135)
    cal = make_calibrate(fit_table(scores, labels))
    assert cal(0.95) == 0.70 and cal(0.8) == 0.50 and cal(0.6) == 0.30 and cal(0.2) == 0.10


def test_fit_is_monotonic_even_when_bins_are_not():
    table = fit_table([0.2] * 10 + [0.6] * 10, [True] * 8 + [False] * 2 + [True] * 2 + [False] * 8)
    assert table["rates"] == sorted(table["rates"])
    with pytest.raises(ValueError):
        make_calibrate({"edges": [0.5, 1.0], "rates": [0.9, 0.1]})


# ---- decide ----------------------------------------------------------------------------------
def scored(type_, score, *, field="email.body", start=0, hint=None):
    c = Candidate(field=field, start=start, end=start + 3, type=type_, detectors={"model"}, hint=hint)
    return ScoredCandidate(candidate=c, raw_score=score, calibrated=score)


def decisions(*items, ov=None):
    return [(d.action, d.reason) for d in decide(list(items), POLICY, ov or Overrides(), ctx())]


def test_new_types_have_tiers():
    assert (POLICY.tier_of("DEMOGRAPHIC"), POLICY.tier_of("NETWORK_ID"), POLICY.tier_of("AMOUNT")) == (
        "high", "medium", "medium")
    assert decisions(scored("AMOUNT", 0.3), scored("AMOUNT", 0.8, start=10)) == [
        ("retain", "below_threshold"), ("redact", "meets_threshold")]


def test_tier_thresholds():
    assert decisions(scored("HEALTH", 0.25), scored("PHONE_PERSONAL", 0.15),
                     scored("PHONE_PERSONAL", 0.95)) == [
        ("redact", "meets_threshold"), ("retain", "below_threshold"), ("redact", "meets_threshold")]


def test_term_list_match_is_always_redacted():
    assert decisions(scored("CODENAME", 0.01, hint="term_list_match")) == [("redact", "term_list_match")]


def test_unknown_types_and_missing_scores_are_redacted():
    no_score = scored("PERSON", None)
    no_score.calibrated = None
    assert decisions(scored("SOMETHING_NEW", 0.01), no_score) == [
        ("redact", "cannot_classify_default_redact"), ("redact", "cannot_classify_default_redact")]


def test_low_tier_combination_counts_distinct_types_per_field():
    three_dates = [scored("DATE", 0.9, start=i * 10) for i in range(3)]
    assert {a for a, _ in decisions(*three_dates)} == {"retain"}
    mixed = [scored("CITY", 0.9), scored("ORG", 0.9, start=10), scored("AGE", 0.9, start=20)]
    assert {r for _, r in decisions(*mixed)} == {"combined_low_tier"}


def test_allow_list_and_medium_override():
    assert decisions(scored("PHONE_PERSONAL", 0.9, hint="allow_list")) == [("retain", "allow_list")]
    ov = Overrides(thresholds={"medium": 0.95})
    assert decisions(scored("PERSON", 0.9), ov=ov) == [("retain", "below_threshold")]


def test_context_store_never_allow_lists_high_tier_types():
    store = ctx(allow={"800-555-0100", "Blue Harbor"})
    assert store.is_allowed("PHONE_PERSONAL", "800-555-0100")
    assert not store.is_allowed("CODENAME", "Blue Harbor")


# ---- pseudonymize: one placeholder per header person -----------------------------------------
from vg_redactor.contracts.fields import iter_fields  # noqa: E402
from vg_redactor.contracts.types import Decision, EmailIn, LabelState  # noqa: E402
from vg_redactor.privacy import pseudonymize  # noqa: E402
from vg_redactor.stubs.components import restore  # noqa: E402


def redact_all_persons(purpose, email_dict, labels=None):
    """Redact every header-name occurrence (as detect_rules finds them) and pseudonymise."""
    email = EmailIn.model_validate(email_dict)
    segs = [Segment(field=p, text=t, source="body") for p, t in iter_fields(purpose, email).items()]
    decisions = [Decision(candidate=c, tier="medium", action="redact", confidence=0.9,
                          reason="meets_threshold")
                 for c in detect_rules(segs, ctx()) if c.type == "PERSON"]
    return pseudonymize(purpose, email, decisions, labels or LabelState())


DANA_TOM = {"from": {"name": "Dana Whitfield", "address": "d@x.test"},
            "to": [{"name": "Tom Reyes", "address": "t@x.test"}],
            "body": "Hi Tom,\nAsk Ms. Whitfield.\n- Dana",
            "thread": [{"text": "On Mon, Tom Reyes wrote: Dana, confirm?"}]}


def test_variants_of_one_person_share_a_placeholder():
    out = redact_all_persons("Draft a reply to Dana", DANA_TOM)
    e = out.redacted_email
    dana, tom = e["from"]["name"], e["to"][0]["name"]
    assert dana != tom
    assert e["body"] == f"Hi {tom},\nAsk Ms. {dana}.\n- {dana}"
    assert e["thread"][0]["text"] == f"On Mon, {tom} wrote: {dana}, confirm?"
    assert out.redacted_purpose == f"Draft a reply to {dana}"
    assert out.mapping == {dana: "Dana Whitfield", tom: "Tom Reyes"}


def test_restore_uses_the_full_name():
    out = redact_all_persons("Reply to Dana", DANA_TOM)
    ph = out.redacted_email["from"]["name"]
    assert restore(f"Hi {ph},", out.mapping).restored_text == "Hi Dana Whitfield,"


def test_shared_first_name_is_not_merged():
    email = {**DANA_TOM, "cc": [{"name": "Dana Lee", "address": "l@x.test"}],
             "body": "Dana Whitfield and Dana Lee met. Dana agreed.", "thread": []}
    out = redact_all_persons("Summarise", email)
    phs = set(out.mapping)
    assert len(phs) == 4  # Dana Whitfield, Dana Lee, Tom Reyes, and the ambiguous "Dana"
    assert "Dana" in out.mapping.values()


def test_session_reuses_the_person_label_for_a_bare_first_name():
    labels = LabelState()
    first = redact_all_persons("Reply to Dana", DANA_TOM, labels)
    dana = first.redacted_email["from"]["name"]
    later = EmailIn.model_validate({"body": "Dana called again."})
    c = Candidate(field="email.body", start=0, end=4, type="PERSON", detectors={"model"})
    out = pseudonymize("Summarise", later,
                       [Decision(candidate=c, tier="medium", action="redact", confidence=0.9,
                                 reason="meets_threshold")], labels)
    assert out.redacted_email["body"] == f"{dana} called again."


# ---- through the HTTP API --------------------------------------------------------------------
@pytest.fixture
def privacy_config(tmp_path):
    for f in ("policy.yaml", "calibration.yaml"):
        shutil.copy(CONFIG_DIR / f, tmp_path / f)
    (tmp_path / "context_store.yaml").write_text(
        'version: "ctx-test"\nterm_list: ["Blue Harbor"]\nallow_list: []\n')
    return tmp_path


async def _client(settings, model, components):
    app = create_app(settings, components, model, Metrics())
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


@pytest.mark.parametrize("use_presidio", [
    False, pytest.param(True, marks=pytest.mark.skipif(not HAS_PRESIDIO, reason="no presidio"))])
async def test_api_with_privacy_components(settings, model, privacy_config, use_presidio):
    comps = build_components(privacy_config, presidio=use_presidio)
    req = {**EMAIL_REQ, "email": {**EMAIL_REQ["email"],
           "from": {"name": "Dana Whitfield", "address": "dana@example.test"},
           "body": "Blue Harbor closes. Reserve up $1.84M. Call 202-555-0102.\n- Dana"}}
    async with await _client(settings, model, comps) as c:
        r = await c.post("/v1/redactions", json=req, headers=HEADERS)
        assert r.status_code == 200
        out = r.json()
        body_out = out["redacted_email"]["body"]
        for secret in ("Blue Harbor", "$1.84M", "202-555-0102", "Dana"):
            assert secret not in body_out
        assert "Dana" not in str(out["redacted_email"]["from"])
        assert out["context_store_version"] == "ctx-test"
        rid = out["request_id"]
        back = await c.post(f"/v1/redactions/{rid}/restore", json={"reply_text": body_out},
                            headers=HEADERS)
        # Variants of one person restore to the full name ("- Dana" -> "- Dana Whitfield").
        assert back.json()["restored_text"] == req["email"]["body"].replace(
            "- Dana", "- Dana Whitfield")


@pytest.mark.skipif(not HAS_PRESIDIO, reason="no presidio")
def test_presidio_maps_types_and_skips_uk_nhs():
    from vg_redactor.privacy import make_detect_presidio
    detect = make_detect_presidio()
    text = "Call Tom Reyes at 412-555-0182 or tom.reyes@acme.com."
    got = {(text[c.start:c.end], c.type) for c in detect(body(text))}
    assert ("412-555-0182", "PHONE_PERSONAL") in got
    assert ("tom.reyes@acme.com", "EMAIL_PERSONAL") in got
    assert all(k in POLICY.taxonomy for _, k in got)
