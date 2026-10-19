"""STUB components, so the whole pipeline runs before the real ones arrive.

READ THIS FIRST (teammates replacing a stub)
--------------------------------------------
* Every function below has the exact signature declared in contracts/components.py (`Components`).
  To replace one: write your function with the SAME signature and pass it into the `Components`
  bundle in main.py. Nothing else in the service needs to change.
* Each function carries a "REAL VERSION MUST" list. Those points are the contract; what the stub
  does is only a placeholder so the API and failure paths can be tested.
* Offsets: `start`/`end` are Unicode code points, half-open [start, end), relative to the ORIGINAL
  text of the field named by `field` (e.g. "email.body"). Never offsets into a joined string.
* Never put input text, detected values or restored text in an exception message or a log line.
* Run `python -m pytest` from service/ after swapping a component; the tests must keep passing.
* Owners are not confirmed yet. See docs/api/service-interfaces-v0.4.2-en.md section 4 for the table.
"""
from __future__ import annotations

import json
import re

from ..contracts.components import Components, ContextStore
from ..contracts.errors import ModelOutputUnparseable
from ..contracts.fields import email_to_dict, iter_fields, set_field
from ..contracts.policy import Policy
from ..contracts.types import (Candidate, Decision, EmailIn, LabelState, Overrides, PseudonymResult,
                               RestoreOutcome, ScoredCandidate, Segment, SpanOut)

PLACEHOLDER_RE = re.compile(r"\[[A-Za-z]+_\d+\]")


class StubContextStore:
    """Read-only term list and allow-list, loaded once at startup (contract: static context store).

    REAL VERSION MUST: expose `version`, `term_list`, `allow_list`, `is_allowed()`; never change
    after loading (changing the store means deploying a new version); load from files supplied by
    the client. The stub keeps both lists in memory and only does exact string matching.
    """
    version = "context-stub-0"

    def __init__(self, term_list: set[str] | None = None, allow_list: set[str] | None = None):
        self.term_list = term_list or set()
        self.allow_list = allow_list or set()

    def is_allowed(self, entity_type: str, text: str) -> bool:
        return text in self.allow_list


# ---- segmentation ----------------------------------------------------------------------------
def segment(purpose: str, email: EmailIn) -> list[Segment]:
    """Split a request into text segments, one per field, each tagged with where it came from.

    REAL VERSION MUST: return every non-empty text field of the request (see
    contracts/fields.iter_fields for the field-path syntax); tag `source` as one of purpose,
    header, subject, body, quoted_thread, signature (the stub never emits `signature`; a real
    version may split the signature out of the body, but then `field` must still be a valid
    path and offsets must still index the original field text); never raise (when unsure, tag
    the text as `body`).
    """
    out = []
    for path, text in iter_fields(purpose, email).items():
        if path == "purpose":
            src = "purpose"
        elif path == "email.subject":
            src = "subject"
        elif path.startswith("email.thread"):
            src = "quoted_thread"
        elif path == "email.body":
            src = "body"
        else:
            src = "header"
        out.append(Segment(field=path, text=text, source=src))
    return out


# ---- rules / presidio ------------------------------------------------------------------------
_RULES = [
    ("PHONE_PERSONAL", re.compile(r"(?<!\d)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?!\d)")),
    ("EMAIL_PERSONAL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("GOV_ID", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    ("CARD_NUMBER", re.compile(r"(?<!\d)(?:\d[ -]?){13,16}(?!\d)")),
]


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def detect_rules(segments: list[Segment], ctx: ContextStore) -> list[Candidate]:
    """Rule-based candidate detection (regexes with checksum validation, plus term-list matches).

    REAL VERSION MUST: return Candidates with detectors={"rules"}; validate checksums where a
    checksum exists (for example Luhn for card numbers); turn every ContextStore term-list match
    into a candidate with type of a High-tier entity and hint="term_list_match"; be synchronous and
    side-effect free (the service runs it in a worker thread); raise only on a real internal
    failure, because an exception here ends the request with HTTP 500 (there is no safe fallback
    below the rule engine). The stub covers phone, email, SSN-like and card numbers only.
    """
    cands: list[Candidate] = []
    for seg in segments:
        for etype, rx in _RULES:
            for m in rx.finditer(seg.text):
                if etype == "CARD_NUMBER" and not _luhn(re.sub(r"\D", "", m.group())):
                    continue
                cands.append(Candidate(field=seg.field, start=m.start(), end=m.end(), type=etype,
                                       detectors={"rules"}))
        for term in ctx.term_list:
            for m in re.finditer(re.escape(term), seg.text):
                cands.append(Candidate(field=seg.field, start=m.start(), end=m.end(),
                                       type="CODENAME", detectors={"rules"}, hint="term_list_match"))
    return cands


def detect_presidio(segments: list[Segment]) -> list[Candidate]:
    """Candidate detection with Presidio (rules plus NER).

    REAL VERSION MUST: return Candidates with detectors={"presidio"}, mapped to the entity types in
    config/policy.yaml (`taxonomy`); load models once at import or startup, not per call; be
    synchronous (the service runs it in a worker thread). If it raises, the service does NOT fail:
    it returns a degraded response (degraded_reason="recognizer_failure"). The stub returns [].
    """
    return []  # stub: the real Presidio configuration comes from the privacy-research owner


def merge_candidates(*lists: list[Candidate]) -> list[Candidate]:
    """Union the candidate lists from rules, Presidio and the model by character position.

    REAL VERSION MUST: treat overlapping spans in the same field as one span covering both, with
    `detectors` equal to the union of the sources; if the merged spans disagree on `type`, keep
    the type with the higher tier (use the Policy for that); keep `hint` when any source set it;
    return candidates sorted by (field, start); never mutate its inputs. Called with several
    lists (`merge_candidates(rules_and_presidio, model_candidates)`) and with one list.
    """
    """Merge by character position; overlapping spans in one field become one (union of detectors)."""
    items = sorted((c for lst in lists for c in lst), key=lambda c: (c.field, c.start, -c.end))
    merged: list[Candidate] = []
    for c in items:
        last = merged[-1] if merged else None
        if last and last.field == c.field and c.start < last.end:
            last.end = max(last.end, c.end)
            last.detectors |= c.detectors
            last.hint = last.hint or c.hint
        else:
            merged.append(c.model_copy(deep=True))
    return merged


# ---- prompts (stub model protocol: candidates travel as JSON inside the prompt) --------------
def build_detection_prompt(segments: list[Segment]) -> str:
    """Build the DETECTION prompt (model call 1: find sensitive spans in the text).

    REAL VERSION MUST: return the full prompt string for the local model; version it by setting
    `Components.detection_prompt_version`; keep it independent of the assessment prompt (the two
    are tuned separately). The stub uses a toy JSON protocol that only StubModelClient understands.
    """
    return "DETECT\n" + json.dumps([s.model_dump() for s in segments])


def parse_detection(raw: str, segments: list[Segment]) -> list[Candidate]:
    """Parse the raw model reply of the detection prompt into Candidates.

    REAL VERSION MUST: return Candidates with detectors={"model"} and offsets converted back to the
    original field text; raise ModelOutputUnparseable (contracts/errors.py) when the reply cannot
    be parsed or has invalid offsets; never include the reply text in the exception. The service
    turns that exception into a degraded response (degraded_reason="model_output_unparseable").
    """
    try:
        items = json.loads(raw)
        return [Candidate(field=i["field"], start=i["start"], end=i["end"], type=i["type"],
                          detectors={"model"}) for i in items]
    except Exception as e:  # noqa: BLE001
        raise ModelOutputUnparseable() from e


def build_assessment_prompt(segments: list[Segment], cands: list[Candidate]) -> str:
    """Build the ASSESSMENT prompt (model call 2: judge each merged candidate in its context).

    REAL VERSION MUST: give the model the surrounding text and the candidate list, and ask for
    "is it private in this context?" plus a raw score per candidate; version it through
    `Components.assessment_prompt_version`. The stub uses a toy JSON protocol (see above).
    """
    return "ASSESS\n" + json.dumps([c.model_dump(mode="json") for c in cands])


def parse_assessment(raw: str, cands: list[Candidate]) -> list[ScoredCandidate]:
    """Parse the raw assessment reply into ScoredCandidates, one per input candidate, same order.

    REAL VERSION MUST: set `raw_score` to the model's UNCALIBRATED score in [0, 1] and `is_private`
    from the reply; for a candidate the model did not classify leave both as None (the decision
    step then redacts it by default, reason "cannot_classify_default_redact"); raise
    ModelOutputUnparseable when the reply as a whole cannot be parsed. Do not calibrate here.
    """
    try:
        by_idx = {i["i"]: i for i in json.loads(raw)}
        return [ScoredCandidate(candidate=c, raw_score=by_idx[i]["score"] if i in by_idx else None,
                                is_private=by_idx[i]["private"] if i in by_idx else None)
                for i, c in enumerate(cands)]
    except Exception as e:  # noqa: BLE001
        raise ModelOutputUnparseable() from e


def calibrate(raw: float) -> float:
    """Map a raw model score to a calibrated score (fitted on labelled emails).

    REAL VERSION MUST: be a pure function of the raw score, monotonic, return a value in [0, 1],
    and be fitted offline on held-out labelled data; keep the fitted table in a versioned file.
    The stub just multiplies by 0.75 so tests can see that calibration ran.
    """
    return round(raw * 0.75, 3)  # stub: the real calibration table is fitted on labelled emails


# ---- decision --------------------------------------------------------------------------------
def decide(scored: list[ScoredCandidate], policy: Policy, overrides: Overrides,
           ctx: ContextStore) -> list[Decision]:
    """Turn scored candidates into redact/retain decisions (tier x threshold). The model never
    decides alone: this function is where "code decides".

    REAL VERSION MUST: look up each candidate's tier with `policy.tier_of(type)`; compare the
    CALIBRATED score (`ScoredCandidate.calibrated`) with `policy.threshold(tier, overrides.thresholds)`
    and redact when score >= threshold (High and Medium tiers); retain Low-tier items when isolated
    and redact them when several together could identify a person; treat Public-tier items as
    retained unless the model is not confident they are public; redact when `calibrated` is None
    (cannot classify); retain candidates whose `hint` is "allow_list" (the service already
    marked them; it never marks High-tier candidates); never read `overrides.thresholds` for High
    (the gateway rejects that with HTTP 422). `Decision.reason` must be one of the stable codes
    in the contract (for example below_threshold, isolated_low_tier, allow_list) and must never
    contain private text. Pure function: no I/O, no logging of values.
    """
    low_count = sum(1 for s in scored if policy.tier_of(s.candidate.type) == "low")
    out = []
    for s in scored:
        c = s.candidate
        tier = policy.tier_of(c.type)
        score = s.calibrated
        if score is None:
            out.append(Decision(candidate=c, tier=tier, action="redact", confidence=None,
                                reason="cannot_classify_default_redact"))
            continue
        if c.hint == "allow_list":  # the orchestrator marks allow-listed candidates
            out.append(Decision(candidate=c, tier=tier, action="retain", confidence=score, reason="allow_list"))
        elif tier == "low":
            combined = low_count >= policy.low_tier_combine_count
            out.append(Decision(candidate=c, tier=tier, action="redact" if combined else "retain",
                                confidence=score, reason="combined_low_tier" if combined else "isolated_low_tier"))
        else:
            thr = policy.threshold(tier, overrides.thresholds)
            hit = score >= thr
            out.append(Decision(candidate=c, tier=tier, action="redact" if hit else "retain",
                                confidence=score, reason="meets_threshold" if hit else "below_threshold"))
    return out


def decide_degraded(cands: list[Candidate], policy: Policy) -> list[Decision]:
    """Decisions for the degraded path (model unusable): redact EVERY candidate, skip thresholds.

    REAL VERSION MUST: return one Decision per candidate with action="redact", confidence=None,
    reason="degraded_redact_all", tier from `policy.tier_of(type)`. This is the fail-safe rule;
    it should rarely need to change.
    """
    return [Decision(candidate=c, tier=policy.tier_of(c.type), action="redact", confidence=None,
                     reason="degraded_redact_all") for c in cands]


# ---- pseudonymisation / restore --------------------------------------------------------------
def _ph_type(entity_type: str) -> str:
    return entity_type.split("_")[0]


def pseudonymize(purpose: str, email: EmailIn, decisions: list[Decision],
                 labels: LabelState) -> PseudonymResult:
    """Replace the redacted spans with placeholders and build the placeholder -> original mapping.

    REAL VERSION MUST: replace only decisions with action="redact"; compute replacements from the
    ORIGINAL field text so earlier replacements do not shift later offsets (the stub applies them
    right to left); use placeholders shaped like "[TYPE_n]" (letters, underscore, digits; the
    restore step relies on this shape); give the same real-world entity the same placeholder
    within one `LabelState` (it is shared across requests of one session and stays inside the
    service); return `spans` for EVERY decision (retained ones too), never containing the
    original value; return `redacted_email` in the same shape as the input email (see
    contracts/fields.set_field). The mapping must never be logged.
    """
    fields = iter_fields(purpose, email)
    mapping: dict[str, str] = {}
    spans: list[SpanOut] = []
    placeholder_for: dict[int, str] = {}
    ordered = sorted(decisions, key=lambda d: (d.candidate.field, d.candidate.start))
    for d in ordered:  # numbering in document order
        c = d.candidate
        if d.action == "redact":
            original = fields[c.field][c.start:c.end]
            key = f"{_ph_type(c.type)}|{original.strip().lower()}"
            ph = labels.labels.get(key)
            if ph is None:
                t = _ph_type(c.type)
                labels.counters[t] = labels.counters.get(t, 0) + 1
                ph = f"[{t}_{labels.counters[t]}]"
                labels.labels[key] = ph
            mapping[ph] = original
            placeholder_for[id(d)] = ph
        spans.append(SpanOut(field=c.field, start=c.start, end=c.end, type=c.type, tier=d.tier,
                             action=d.action, confidence=d.confidence,
                             detectors=sorted(c.detectors), reason=d.reason))
    out_fields = dict(fields)
    for d in sorted(ordered, key=lambda d: (d.candidate.field, -d.candidate.start)):
        if d.action == "redact":
            c = d.candidate
            t = out_fields[c.field]
            out_fields[c.field] = t[:c.start] + placeholder_for[id(d)] + t[c.end:]
    email_dict = email_to_dict(email)
    for path, text in out_fields.items():
        if path != "purpose":
            set_field(email_dict, path, text)
    return PseudonymResult(redacted_purpose=out_fields["purpose"], redacted_email=email_dict,
                           spans=spans, mapping=mapping)


def restore(reply_text: str, mapping: dict[str, str]) -> RestoreOutcome:
    """Put original values back into a cloud reply, using one redaction's mapping.

    REAL VERSION MUST: find placeholders case-insensitively with the pattern [A-Za-z]+_[0-9]+ inside
    square brackets; if ANY placeholder is not in `mapping` (unknown, malformed or with changed
    case), restore nothing and return BLOCKED with reason "unknown_placeholder" and the sorted
    list in `unmatched_placeholders`; otherwise return RESTORED with `restored_text`. It does
    NOT consume anything and may be called repeatedly. It never guesses a missing placeholder.
    """
    unmatched = sorted({p for p in re.findall(r"\[[A-Za-z]+_\d+\]", reply_text, flags=re.I)
                        if p not in mapping})
    if unmatched:
        return RestoreOutcome(restore_decision="BLOCKED", unmatched_placeholders=unmatched,
                              reason="unknown_placeholder")
    text = PLACEHOLDER_RE.sub(lambda m: mapping[m.group(0)], reply_text)
    return RestoreOutcome(restore_decision="RESTORED", restored_text=text)


def build_stub_components(policy: Policy, context_store: ContextStore | None = None) -> Components:
    return Components(
        segment=segment, detect_rules=detect_rules, detect_presidio=detect_presidio,
        merge_candidates=merge_candidates, build_detection_prompt=build_detection_prompt,
        parse_detection=parse_detection, build_assessment_prompt=build_assessment_prompt,
        parse_assessment=parse_assessment, calibrate=calibrate, decide=decide,
        decide_degraded=decide_degraded, pseudonymize=pseudonymize, restore=restore,
        policy=policy, context_store=context_store or StubContextStore(),
        detection_prompt_version="detect-stub-0", assessment_prompt_version="assess-stub-0")
