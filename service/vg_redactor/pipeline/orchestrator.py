"""Wires the components into the 18-step workflow (see architecture diagrams).

Order: segment -> [rules || presidio || model detection] -> merge -> model assessment ->
calibrate -> decide -> pseudonymise -> record + audit. Any model failure (or Presidio failure)
switches to the degraded path: redact every rule/Presidio candidate and flag the response.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from ..contracts.components import Components
from ..contracts.errors import (DeadlineExceeded, ModelCallError,
                                RecognizerError, RuleEngineError, high_tier_fixed)
from ..contracts.types import Candidate, Decision, RedactionRequestV3, RedactionResponseV3
from ..model.client import ModelGateway
from ..obs.audit import AuditLog
from ..obs.metrics import Metrics
from ..sessions.service import SessionContext
from ..settings import Settings
from .deadline import Deadline
from .degrade import Degraded


@dataclass
class Orchestrator:
    components: Components
    model: ModelGateway
    metrics: Metrics
    audit: AuditLog
    settings: Settings

    # ------------------------------------------------------------------------------------------
    async def redact(self, req: RedactionRequestV3, rid: str, *,
                     session_context: SessionContext) -> RedactionResponseV3:
        """Process one redaction; rid tracks HTTP audit, session_context owns retention."""
        s, c, m = self.settings, self.components, self.metrics
        deadline = session_context.deadline or Deadline(s.timeout_ms)
        session_context.deadline = deadline
        timings: dict[str, float] = {}
        t0 = time.perf_counter()
        mode = "error"
        try:
            deadline.check()
            async with asyncio.timeout(deadline.remaining_ms() / 1000):
                resp, result_mode = await self._run(req, rid, deadline, timings, session_context)
                deadline.check()
                mode = result_mode
        except TimeoutError:
            raise DeadlineExceeded() from None
        finally:
            m.pipeline_duration.labels("redactions", mode).observe(time.perf_counter() - t0)
        return resp

    # ------------------------------------------------------------------------------------------
    async def _run(self, req, rid, deadline, timings, session_context: SessionContext) -> tuple[RedactionResponseV3, str]:
        s, c, m = self.settings, self.components, self.metrics
        ov = req.policy.overrides

        with m.stage("segment", timings):
            segs = c.segment(req.purpose, req.email)

        async def run_rules():
            with m.stage("detect_rules", timings):
                try:
                    result = await asyncio.to_thread(c.detect_rules, segs, c.context_store)
                    m.component_up.labels("rules").set(1)
                    return result
                except Exception as e:  # noqa: BLE001
                    m.component_up.labels("rules").set(0)
                    raise RuleEngineError() from e

        async def run_presidio():
            with m.stage("detect_presidio", timings):
                try:
                    result = await asyncio.to_thread(c.detect_presidio, segs)
                    m.component_up.labels("presidio").set(1)
                    return result
                except Exception as e:  # noqa: BLE001
                    m.component_up.labels("presidio").set(0)
                    raise RecognizerError() from e

        async def run_model_detection():
            with m.stage("detect_model", timings):
                return await self.model.call("detection", c.build_detection_prompt(segs), deadline,
                                             parse=lambda raw: c.parse_detection(raw, segs))

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
                    scored = await self.model.call("assessment", c.build_assessment_prompt(segs, cands),
                                                   deadline, parse=lambda raw: c.parse_assessment(raw, cands))
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
            session_context.degraded = (degraded.reason, degraded.stage)

        with m.stage("pseudonymize", timings):
            out = await session_context.render(decisions)
        mode = "degraded" if degraded else "normal"
        for sp in out.spans:
            m.spans.labels(sp.tier, sp.action, mode).inc()
        with m.stage("audit", timings):
            await asyncio.to_thread(self._audit, rid, out, degraded, timings, raw_scores,
                                    session_context.mode)
        deadline.check()

        return RedactionResponseV3(
            session_id=session_context.session_id,
            redacted_email=out.redacted_email, redacted_purpose=out.redacted_purpose,
            expires_at=session_context.record.expires_at_iso, degraded=degraded is not None), mode

    # ------------------------------------------------------------------------------------------
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

    def _audit(self, rid, out, degraded, timings, raw_scores, backend):
        self.audit.write({
            "request_id": rid, "ts": time.time(), "degraded": degraded is not None,
            "restoration_backend": backend,
            "degraded_reason": degraded.reason if degraded else None,
            "degraded_stage": degraded.stage if degraded else None,
            "spans": [{"type": sp.type, "tier": sp.tier, "action": sp.action,
                       "confidence": sp.confidence, "detectors": sp.detectors,
                       "reason": sp.reason} for sp in out.spans],
            "raw_scores": raw_scores,  # raw model scores appear only in the audit log
            "timings_ms": dict(timings),
            "versions": {"policy": self.components.policy.version, "model": self.model.version,
                         "detection_prompt": self.components.detection_prompt_version,
                         "assessment_prompt": self.components.assessment_prompt_version,
                         "context_store": self.components.context_store.version}})
