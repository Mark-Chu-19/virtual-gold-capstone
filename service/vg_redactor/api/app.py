"""V3-only FastAPI gateway for tenant-bound redaction and restoration."""
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
from ..contracts.errors import DeadlineExceeded, ProblemError, validation_failed
from ..contracts.types import (RedactionRequestV3, RedactionResponseV3, RestoreRequestV3,
                               RestoreResponseV3, SessionRequestV3)
from ..model.client import ModelGateway, StubModelClient
from ..obs.audit import AuditLog
from ..obs.logging import log_event
from ..obs.metrics import Metrics
from ..obs.http import HttpMetricsMiddleware
from ..pipeline.orchestrator import Orchestrator
from ..pipeline.deadline import Deadline
from ..records.store import RecordStore
from ..settings import Settings, hash_key
from ..sessions.backends import AesMappingBackend, MappingBackend, decode_keyring
from ..sessions.identifiers import SessionIdGenerator, UlidSessionIdGenerator
from ..sessions.service import SessionService
from ..auth import Principal
from .problems import problem_response, violations_from_pydantic

PUBLIC = {"/healthz", "/readyz"}


def new_request_id() -> str:
    return "req_" + str(ULID())


def create_app(settings: Settings, components: Components, model_client: ModelClient | None = None,
               metrics: Metrics | None = None, *,
               session_ids: SessionIdGenerator | None = None) -> FastAPI:
    metrics = metrics or Metrics()
    model_client = model_client or StubModelClient()
    records = RecordStore(settings.max_records, settings.max_ttl_seconds,
                          on_remove=lambda reason: metrics.records_removed.labels(reason).inc())
    gateway = ModelGateway(model_client, metrics, concurrency=settings.model_concurrency,
                           call_cap_ms=settings.model_call_timeout_ms,
                           reserve_ms=settings.degraded_reserve_ms)
    orch = Orchestrator(components, gateway, metrics, AuditLog(settings.audit_log_path), settings)
    keys = decode_keyring(settings.v3.keys, settings.v3.active_key_id)
    if settings.v3.backend == "aes_siv" and not keys:
        raise ValueError("V3 AES-SIV requires a persistent VG_SESSION_KEYS keyring")
    sessions = SessionService(records, components, session_ids or UlidSessionIdGenerator(),
        {"mapping": MappingBackend(),
         "aes_siv": AesMappingBackend(keys, settings.v3.active_key_id)},
        settings.v3.backend, settings.default_ttl_seconds, settings.max_restored_bytes)
    readiness = {"model_up": None}

    async def refresh_readiness() -> dict:
        readiness["model_up"] = await model_client.ping()
        metrics.component_up.labels("model_endpoint").set(int(readiness["model_up"]))
        mode = "ready" if readiness["model_up"] else "degraded"
        metrics.set_mode(mode)
        return readiness

    async def housekeeping():
        while True:
            records.sweep()
            stats = records.stats()
            metrics.records_active.set(stats["active"])
            metrics.records_reserved.set(stats["reserved"])
            metrics.records_capacity.set(stats["capacity"])
            await refresh_readiness()
            await asyncio.sleep(10)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        metrics.build_info.labels(
            settings.service_version, settings.contract_version, components.policy.version,
            model_client.version, components.detection_prompt_version,
            components.assessment_prompt_version, components.context_store.version).set(1)
        task = asyncio.create_task(housekeeping())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="Local Redaction Service", version=settings.contract_version,
                  lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.records, app.state.metrics, app.state.orchestrator = records, metrics, orch
    app.state.refresh_readiness = refresh_readiness
    app.state.sessions = sessions

    def error_response(request: Request, err: ProblemError):
        # V3 clients only manage session_id; per-call diagnostics live in the header.
        if err.type == "capacity-exhausted":
            metrics.capacity_rejected.inc()
        return problem_response(err, request.state.request_id)

    # ---- middleware: request id, auth, metrics, last-resort 500 ------------------------------
    @app.middleware("http")
    async def gate(request: Request, call_next):
        rid = new_request_id()
        request.state.request_id = rid
        t0 = time.perf_counter()
        try:
            if request.url.path not in PUBLIC and not _authorized(request, settings):
                resp = error_response(request, ProblemError(401, "unauthorized", "Missing or invalid API key"))
            else:
                if request.url.path not in PUBLIC:
                    digest = hash_key(request.headers.get("authorization", "")[7:].strip())
                    identity = settings.api_identities.get(digest)
                    request.state.principal = (Principal(identity.tenant_id)
                                               if identity else Principal(digest))
                resp = await call_next(request)
        except ProblemError as e:
            resp = error_response(request, e)
        except Exception as e:  # noqa: BLE001
            log_event("unhandled_error", request_id=rid, error_type=type(e).__name__)
            resp = error_response(request, ProblemError(500, "internal", "Internal error; content was not processed"))
        route = request.scope.get("route")
        route_path = route.path if route else "unmatched"
        dt = time.perf_counter() - t0
        resp.headers.setdefault("X-Request-ID", rid)
        log_event("request", request_id=rid, route=route_path, method=request.method,
                  status=resp.status_code, duration_ms=round(dt * 1000, 1))
        return resp

    @app.exception_handler(ProblemError)
    async def _problem(request: Request, err: ProblemError):
        return error_response(request, err)

    # ---- routes ------------------------------------------------------------------------------
    @app.post("/v3/redaction", response_model=RedactionResponseV3)
    async def create_redaction_v3(request: Request):
        with metrics.stage("validate"):
            req = await _parse(request, RedactionRequestV3, settings)
            _check_business_rules(req, components)
        context = sessions.begin(req, request.state.principal)
        context.deadline = Deadline(settings.timeout_ms)
        metrics.inflight.inc()
        try:
            async with asyncio.timeout(settings.timeout_ms / 1000):
                result = await orch.redact(req, request.state.request_id, session_context=context)
                # Serialize before leaving the cleanup boundary. A late worker cannot publish data.
                response = await asyncio.to_thread(_json_response, result)
                context.deadline.check()
        except TimeoutError:
            context.abort()
            raise DeadlineExceeded() from None
        except BaseException:
            context.abort()
            raise
        finally:
            metrics.inflight.dec()
        request.state.redaction_mode = "degraded" if result.degraded else "normal"
        request.state.redaction_degraded = context.degraded
        log_event("session_created", request_id=request.state.request_id, session_id=context.session_id)
        return response

    @app.post("/v3/restore", response_model=RestoreResponseV3)
    async def restore_v3(request: Request):
        req = await _parse(request, RestoreRequestV3, settings)
        deadline = Deadline(settings.timeout_ms)
        try:
            async with asyncio.timeout(settings.timeout_ms / 1000):
                text = await asyncio.to_thread(sessions.restore,
                    req.session_id, req.text, request.state.principal)
                response = await asyncio.to_thread(_json_response, RestoreResponseV3(restored_text=text))
                deadline.check()
        except TimeoutError:
            raise DeadlineExceeded() from None
        return response

    @app.delete("/v3/redaction", status_code=204)
    async def delete_v3(request: Request):
        req = await _parse(request, SessionRequestV3, settings)
        sessions.delete(req.session_id, request.state.principal)
        return Response(status_code=204)

    @app.get("/v3/info")
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
                       "max_restored_bytes": settings.max_restored_bytes,
                       "max_ttl_seconds": settings.max_ttl_seconds, "max_records": settings.max_records},
            "failure_behavior": "redact_all_candidates",
            "restoration": {"backend": settings.v3.backend, "store": "memory",
                            "default_ttl_seconds": min(settings.default_ttl_seconds, settings.max_ttl_seconds)},
            "supported_contracts": ["v3"]}

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
                               "model_assessment": "up" if up else "down",
                               "session_store": "up", "restoration": "up"}}

    metrics.records_capacity.set(settings.max_records)
    metrics.runtime_info.labels(
        "stub" if isinstance(model_client, StubModelClient) else settings.model.backend,
        settings.v3.backend,
        "stub" if components.detect_rules.__module__.endswith("stubs.components") else "mixed",
    ).set(1)
    # Outermost user middleware sees auth failures and the final response body.
    app.add_middleware(HttpMetricsMiddleware, metrics=metrics, records=records)
    return app


# ---- helpers ---------------------------------------------------------------------------------
def _json_response(result: RedactionResponseV3 | RestoreResponseV3) -> JSONResponse:
    return JSONResponse(result.model_dump(mode="json"))


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
    _check_unicode(data)
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise validation_failed(violations_from_pydantic(e.errors(include_url=False,
                                                                   include_context=False,
                                                                   include_input=False))) from None


def _check_unicode(data) -> None:
    """Reject unpaired surrogate escapes, including dictionary keys, before reserving storage."""
    pending = [data]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            try:
                item.encode("utf8")
            except UnicodeError:
                raise validation_failed([{"field": "body", "code": "invalid_unicode"}]) from None
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)


def _check_business_rules(req: RedactionRequestV3, components: Components) -> None:
    v: list[dict] = []
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
