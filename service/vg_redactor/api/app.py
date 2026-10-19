"""FastAPI gateway: auth, validation, problem+json, request ids, routes (contract 0.4.2)."""
from __future__ import annotations

import asyncio
import hmac
import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from ulid import ULID

from ..contracts.components import Components, ModelClient
from ..contracts.errors import (ProblemError, RecordNotFound, validation_failed)
from ..contracts.types import RedactionRequest, RestoreRequest
from ..model.client import ModelGateway, StubModelClient
from ..obs.audit import AuditLog
from ..obs.logging import log_event
from ..obs.metrics import Metrics
from ..pipeline.orchestrator import Orchestrator
from ..records.store import RecordStore
from ..settings import Settings, hash_key
from .problems import problem_response, violations_from_pydantic

PUBLIC = {"/healthz", "/readyz"}


def new_request_id() -> str:
    return "req_" + str(ULID())


def create_app(settings: Settings, components: Components, model_client: ModelClient | None = None,
               metrics: Metrics | None = None) -> FastAPI:
    metrics = metrics or Metrics()
    model_client = model_client or StubModelClient()
    records = RecordStore(settings.max_records, settings.max_ttl_seconds,
                          on_remove=lambda reason: metrics.records_removed.labels(reason).inc())
    gateway = ModelGateway(model_client, metrics, concurrency=settings.model_concurrency,
                           call_cap_ms=settings.model_call_timeout_ms,
                           reserve_ms=settings.degraded_reserve_ms)
    orch = Orchestrator(components, gateway, records, metrics, AuditLog(settings.audit_log_path), settings)
    readiness = {"model_up": None}

    async def refresh_readiness() -> dict:
        readiness["model_up"] = await model_client.ping()
        mode = "ready" if readiness["model_up"] else "degraded"
        metrics.set_mode(mode)
        return readiness

    async def housekeeping():
        while True:
            records.sweep()
            st = records.stats()
            metrics.records_active.set(st["active"])
            metrics.records_capacity.set(st["capacity"])
            await refresh_readiness()
            await asyncio.sleep(10)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        metrics.build_info.labels(
            settings.service_version, settings.contract_version, components.policy.version,
            model_client.version, components.detection_prompt_version,
            components.assessment_prompt_version, components.context_store.version).set(1)
        task = asyncio.create_task(housekeeping())
        yield
        task.cancel()

    app = FastAPI(title="Local Redaction Service", version=settings.contract_version,
                  lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.records, app.state.metrics, app.state.orchestrator = records, metrics, orch
    app.state.refresh_readiness = refresh_readiness

    # ---- middleware: request id, auth, metrics, last-resort 500 ------------------------------
    @app.middleware("http")
    async def gate(request: Request, call_next):
        rid = new_request_id()
        request.state.request_id = rid
        t0 = time.perf_counter()
        try:
            if request.url.path not in PUBLIC and not _authorized(request, settings):
                resp = problem_response(ProblemError(401, "unauthorized", "Missing or invalid API key"), rid)
            else:
                resp = await call_next(request)
        except ProblemError as e:
            resp = problem_response(e, rid)
        except Exception as e:  # noqa: BLE001
            log_event("unhandled_error", request_id=rid, error_type=type(e).__name__)
            resp = problem_response(ProblemError(500, "internal", "Internal error; content was not processed"), rid)
        route = request.scope.get("route")
        route_path = route.path if route else "unmatched"
        metrics.http_requests.labels(route_path, request.method, str(resp.status_code)).inc()
        dt = time.perf_counter() - t0
        if route_path == "/v1/redactions" and resp.status_code >= 400:
            metrics.request_duration.labels("redactions", "error").observe(dt)
        resp.headers.setdefault("X-Request-ID", rid)
        log_event("request", request_id=rid, route=route_path, method=request.method,
                  status=resp.status_code, duration_ms=round(dt * 1000, 1))
        return resp

    @app.exception_handler(ProblemError)
    async def _problem(request: Request, err: ProblemError):
        return problem_response(err, request.state.request_id)

    # ---- routes ------------------------------------------------------------------------------
    @app.post("/v1/redactions")
    async def create_redaction(request: Request):
        rid = request.state.request_id
        req = await _parse(request, RedactionRequest, settings)
        _check_business_rules(req, settings, components)
        records.reserve(rid)  # 503 before any processing if the record store is full
        metrics.inflight.inc()
        try:
            resp = await orch.redact(req, rid)
        finally:
            metrics.inflight.dec()
        body = resp.model_dump(mode="json")
        if not resp.degraded:
            body.pop("degraded_reason"); body.pop("degraded_stage")
        return JSONResponse(body, headers={"X-Degraded": "true" if resp.degraded else "false"})

    @app.post("/v1/redactions/{rid}/restore")
    async def restore(rid: str, request: Request):
        req = await _parse(request, RestoreRequest, settings)
        rec = records.get(rid)  # 404 / 410
        if rec.mapping is None:
            return {"restore_decision": "BLOCKED", "unmatched_placeholders": [],
                    "reason": "mapping_not_retained"}
        out = components.restore(req.reply_text, rec.mapping)
        return out.model_dump(exclude_none=True)

    @app.delete("/v1/redactions/{rid}", status_code=204)
    async def delete(rid: str):
        records.delete(rid)
        return Response(status_code=204)

    @app.get("/v1/info")
    async def info():
        p = components.policy
        return {
            "service_version": settings.service_version, "contract_version": settings.contract_version,
            "policy_version": p.version, "model_version": model_client.version,
            "prompt_versions": {"detection": components.detection_prompt_version,
                                "assessment": components.assessment_prompt_version},
            "context_store_version": components.context_store.version,
            "tiers": p.tiers,
            "entity_types": [{"type": t, "tier": tier} for t, tier in sorted(p.taxonomy.items())],
            "limits": {"max_request_bytes": settings.max_request_bytes, "timeout_ms": settings.timeout_ms,
                       "max_ttl_seconds": settings.max_ttl_seconds, "max_records": settings.max_records},
            "failure_behavior": "redact_all_candidates"}

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz():
        if readiness["model_up"] is None:
            await refresh_readiness()
        up = bool(readiness["model_up"])
        return {"mode": "ready" if up else "degraded",
                "components": {"rules": "up", "presidio": "up",
                               "model_detection": "up" if up else "down",
                               "model_assessment": "up" if up else "down"}}

    return app


# ---- helpers ---------------------------------------------------------------------------------
def _authorized(request: Request, settings: Settings) -> bool:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return False
    digest = hash_key(auth[7:].strip())
    return any(hmac.compare_digest(digest, h) for h in settings.api_key_hashes)


async def _parse(request: Request, model, settings: Settings):
    if not request.headers.get("content-type", "").lower().startswith("application/json"):
        raise ProblemError(415, "unsupported-media-type", "Body must be application/json")
    limit = settings.max_request_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise ProblemError(413, "payload-too-large", "Request exceeds max_request_bytes")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise ProblemError(413, "payload-too-large", "Request exceeds max_request_bytes")
        chunks.append(chunk)
    try:
        data = json.loads(b"".join(chunks))
    except ValueError:
        raise ProblemError(400, "malformed-json", "Malformed JSON or missing body") from None
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise validation_failed(violations_from_pydantic(e.errors(include_url=False,
                                                                   include_context=False,
                                                                   include_input=False))) from None


def _check_business_rules(req: RedactionRequest, settings: Settings, components: Components) -> None:
    v: list[dict] = []
    if req.session_id and not req.mapping.retain:
        v.append({"field": "session_id", "code": "session_requires_retain"})
    if req.mapping.ttl_seconds and req.mapping.ttl_seconds > settings.max_ttl_seconds:
        v.append({"field": "mapping.ttl_seconds", "code": "ttl_too_large"})
    ov = req.policy.overrides
    for tier, value in ov.thresholds.items():
        f = f"policy.overrides.thresholds.{tier}"
        if tier != "medium":
            v.append({"field": f, "code": "high_tier_fixed" if tier == "high" else "override_not_allowed"})
        elif not 0.0 <= value <= 1.0:
            v.append({"field": f, "code": "out_of_range"})
    for key, types in ov.entity_types.items():
        if key != "exclude":
            v.append({"field": f"policy.overrides.entity_types.{key}", "code": "unknown_key"})
        elif any(components.policy.tier_of(t) == "high" for t in types):
            v.append({"field": "policy.overrides.entity_types.exclude", "code": "high_tier_fixed"})
    if v:
        raise validation_failed(v)
