"""Wires the components into the 18-step workflow (see architecture diagrams).

Order: segment -> [rules || presidio || model detection] -> merge -> model assessment ->
calibrate -> decide -> pseudonymise -> record + audit. Any model failure (or Presidio failure)
switches to the degraded path: redact every rule/Presidio candidate and flag the response.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from ..contracts.components import Components
from ..contracts.errors import (DeadlineExceeded, ModelCallError, ModelOutputUnparseable,
                                RecognizerError, RuleEngineError, high_tier_fixed)
from ..contracts.fields import iter_fields
from ..contracts.types import (Candidate, Decision, LabelState, RedactionRequest, RedactionResponse,
                               RecordInfo, RedactionRequestV2, RedactionRequestV3, ScoredCandidate)
from ..model.client import ModelGateway
from ..obs.audit import AuditLog
from ..obs.metrics import Metrics
from ..records.store import RecordStore
from ..settings import Settings
from .deadline import Deadline
from .degrade import Degraded


@dataclass
class Orchestrator:
    components: Components
    model: ModelGateway
    records: RecordStore
    metrics: Metrics
    audit: AuditLog
    settings: Settings
    mode_probe: dict = field(default_factory=dict)

    # ------------------------------------------------------------------------------------------
    async def redact(self, req: RedactionRequest | RedactionRequestV2 | RedactionRequestV3,
                     rid: str, *, token_context=None) -> RedactionResponse:
        """V1 reserves legacy records; V2/V3 use the shared rendering hook for their own storage.

        rid always identifies the HTTP call for audit; V3 business session IDs are separate.
        """
        s, c, m = self.settings, self.components, self.metrics
        deadline = Deadline(s.timeout_ms)
        timings: dict[str, float] = {}
        t0 = time.perf_counter()
        try:
            async with asyncio.timeout(s.timeout_ms / 1000):
                resp, mode = await self._run(req, rid, deadline, timings, token_context)
        except TimeoutError:
            self.records.release(rid)
            raise DeadlineExceeded() from None
        except BaseException:
            self.records.release(rid)
            raise
        m.request_duration.labels("redactions", mode).observe(time.perf_counter() - t0)
        return resp

    # ------------------------------------------------------------------------------------------
    async def _run(self, req, rid, deadline, timings, token_context=None) -> tuple[RedactionResponse, str]:
        s, c, m = self.settings, self.components, self.metrics
        ov = req.policy.overrides
        loop = asyncio.get_running_loop()

        with m.stage("segment", timings):
            segs = c.segment(req.purpose, req.email)

        async def run_rules():
            with m.stage("detect_rules", timings):
                try:
                    return await asyncio.to_thread(c.detect_rules, segs, c.context_store)
                except Exception as e:  # noqa: BLE001
                    raise RuleEngineError() from e

        async def run_presidio():
            with m.stage("detect_presidio", timings):
                try:
                    return await asyncio.to_thread(c.detect_presidio, segs)
                except Exception as e:  # noqa: BLE001
                    raise RecognizerError() from e

        async def run_model_detection():
            with m.stage("detect_model", timings):
                raw = await self.model.call("detection", c.build_detection_prompt(segs), deadline)
                try:
                    return c.parse_detection(raw, segs)
                except ModelOutputUnparseable:
                    self.model.note_unparseable("detection")
                    raise

        r_rules, r_pres, r_model = await asyncio.gather(
            run_rules(), run_presidio(), run_model_detection(), return_exceptions=True)

        if isinstance(r_rules, BaseException):
            raise r_rules  # no safe fallback below the rule engine -> 500
        degraded: Degraded | None = None
        rules_pres: list[Candidate] = list(r_rules)
        if isinstance(r_pres, BaseException):
            if not isinstance(r_pres, RecognizerError):
                raise r_pres
            degraded = Degraded("recognizer_failure", "detection")
        else:
            rules_pres += r_pres
        model_cands: list[Candidate] = []
        if isinstance(r_model, BaseException):
            if not isinstance(r_model, ModelCallError):
                raise r_model
            degraded = degraded or Degraded(r_model.reason, "detection")  # type: ignore[arg-type]
        else:
            model_cands = r_model

        with m.stage("merge", timings):
            # Degraded: model output is discarded (Open Question 15), except for recognizer_failure
            # where the model's detections are kept because only the recognizer is missing.
            use_model = degraded is None or degraded.reason == "recognizer_failure"
            cands = c.merge_candidates(rules_pres, model_cands if use_model else [])
            cands = self._apply_allow_list(cands, segs, ov, degraded)

        decisions: list[Decision]
        raw_scores: list[dict] = []
        if degraded is None:
            try:
                with m.stage("assess_model", timings):
                    raw = await self.model.call("assessment",
                                                c.build_assessment_prompt(segs, cands), deadline)
                    try:
                        scored = c.parse_assessment(raw, cands)
                    except ModelOutputUnparseable:
                        self.model.note_unparseable("assessment")
                        raise
                raw_scores = [{"type": sc.candidate.type, "raw": sc.raw_score} for sc in scored]
                with m.stage("calibrate", timings):
                    for sc in scored:
                        sc.calibrated = c.calibrate(sc.raw_score) if sc.raw_score is not None else None
                with m.stage("decide", timings):
                    decisions = c.decide(scored, c.policy, ov, c.context_store)
            except ModelCallError as e:
                degraded = Degraded(e.reason, "assessment")  # type: ignore[arg-type]
        if degraded is not None:
            with m.stage("decide", timings):
                base = cands if degraded.reason == "recognizer_failure" else self._rules_only(cands)
                decisions = c.decide_degraded(base, c.policy)
            m.degraded.labels(degraded.reason, degraded.stage).inc()

        with m.stage("pseudonymize", timings):
            if token_context is not None:
                out = await token_context.render(decisions)
                rec = None
            else:
                labels = (self.records.label_state(req.session_id, self._ttl(req))
                          if req.session_id else LabelState())
                out = c.pseudonymize(req.purpose, req.email, decisions, labels)
                rec = self.records.commit(rid, out.mapping if req.mapping.retain else None,
                                          self._ttl(req), req.session_id)
        mode = "degraded" if degraded else "normal"
        for sp in out.spans:
            m.spans.labels(sp.tier, sp.action, mode).inc()
        with m.stage("audit", timings):
            self._audit(rid, out, degraded, timings, raw_scores,
                        token_context.mode if token_context else "legacy")

        return RedactionResponse(
            request_id=rid, degraded=degraded is not None,
            degraded_reason=degraded.reason if degraded else None,
            degraded_stage=degraded.stage if degraded else None,
            redacted_email=out.redacted_email, redacted_purpose=out.redacted_purpose,
            spans=out.spans, record=RecordInfo(expires_at=rec.expires_at_iso,
                                               mapping_retained=rec.mapping_retained) if rec else None,
            policy_version=c.policy.version, model_version=self.model.version,
            prompt_versions={"detection": c.detection_prompt_version,
                             "assessment": c.assessment_prompt_version},
            context_store_version=c.context_store.version), mode

    # ------------------------------------------------------------------------------------------
    def _ttl(self, req: RedactionRequest) -> int:
        return min(req.mapping.ttl_seconds or self.settings.default_ttl_seconds,
                   self.settings.max_ttl_seconds)

    @staticmethod
    def _rules_only(cands: list[Candidate]) -> list[Candidate]:
        """Degraded candidate set: rule and Presidio detections only."""
        out = []
        for cd in cands:
            keep = cd.detectors & {"rules", "presidio"}
            if keep:
                out.append(cd.model_copy(update={"detectors": keep}))
        return out

    def _apply_allow_list(self, cands, segs, ov, degraded):
        """Mark allow-listed candidates (not in degraded mode unless configured) and refuse
        overrides that touch High-tier candidates."""
        policy, ctx = self.components.policy, self.components.context_store
        text = {sg.field: sg.text for sg in segs}
        apply_ctx = degraded is None or self.settings.allow_list_in_degraded
        out = []
        for cd in cands:
            value = text[cd.field][cd.start:cd.end]
            tier = policy.tier_of(cd.type)
            if value in ov.allow_list:
                if tier == "high":
                    raise high_tier_fixed("policy.overrides.allow_list")
                cd = cd.model_copy(update={"hint": "allow_list"})
            elif apply_ctx and ctx.is_allowed(cd.type, value):
                cd = cd.model_copy(update={"hint": "allow_list"})
            if cd.type in ov.entity_types.get("exclude", []):
                continue
            out.append(cd)
        for term in ov.deny_list:  # deny-list matches become High-tier candidates
            for sg in segs:
                start = 0
                while (i := sg.text.find(term, start)) != -1:
                    out.append(Candidate(field=sg.field, start=i, end=i + len(term),
                                         type="BUSINESS_CONFIDENTIAL", detectors={"rules"},
                                         hint="deny_list"))
                    start = i + len(term)
        return self.components.merge_candidates(out)

    def _audit(self, rid, out, degraded, timings, raw_scores, token_backend="legacy"):
        self.audit.write({
            "request_id": rid, "ts": time.time(), "degraded": degraded is not None,
            "token_backend": token_backend,
            "degraded_reason": degraded.reason if degraded else None,
            "degraded_stage": degraded.stage if degraded else None,
            "spans": [{"type": sp.type, "tier": sp.tier, "action": sp.action,
                       "confidence": sp.confidence, "detectors": sp.detectors,
                       "reason": sp.reason} for sp in out.spans],
            "raw_scores": raw_scores,  # raw model scores appear only in the audit log
            "timings_ms": timings,
            "versions": {"policy": self.components.policy.version, "model": self.model.version,
                         "detection_prompt": self.components.detection_prompt_version,
                         "assessment_prompt": self.components.assessment_prompt_version,
                         "context_store": self.components.context_store.version}})
