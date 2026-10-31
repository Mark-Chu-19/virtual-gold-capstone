"""Prometheus metrics. Every label has a small fixed set of values; none ever holds text or ids."""
from __future__ import annotations

from contextlib import contextmanager
import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

_B = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 6, 8, 12, 15, 20)
MODEL_OUTCOMES = ("ok", "unavailable", "timeout", "unparseable", "cancelled", "internal_error")


class Metrics:
    def __init__(self, registry: CollectorRegistry | None = None):
        r = self.registry = registry or CollectorRegistry()
        self.http_requests = Counter("vg_http_requests_total", "HTTP requests",
                                     ["route", "method", "status"], registry=r)
        self.pipeline_duration = Histogram("vg_pipeline_duration_seconds", "Orchestrator latency, excluding HTTP handling",
                                          ["route", "mode"], buckets=_B, registry=r)
        self.http_duration = Histogram("vg_http_duration_seconds", "Server HTTP latency through final response body send",
                                       ["route", "method", "status", "mode"], buckets=_B, registry=r)
        self.redaction_responses = Counter("vg_redaction_responses_total", "Completed redaction responses",
                                          ["mode"], registry=r)
        self.stage_duration = Histogram("vg_stage_duration_seconds", "Per-stage time", ["stage"],
                                        buckets=_B, registry=r)
        self.model_calls = Counter("vg_model_calls_total", "Model calls", ["prompt", "outcome"], registry=r)
        self.model_call_duration = Histogram("vg_model_call_duration_seconds", "Model call time",
                                             ["prompt"], buckets=_B, registry=r)
        self.model_queue_wait = Histogram("vg_model_queue_wait_seconds", "Wait for the model slot",
                                          ["prompt"], buckets=_B, registry=r)
        self.degraded = Counter("vg_degraded_total", "Degraded responses", ["reason", "stage"], registry=r)
        self.spans = Counter("vg_spans_total", "Spans decided", ["tier", "action", "mode"], registry=r)
        self.records_active = Gauge("vg_records_active", "Live request records", registry=r)
        self.records_capacity = Gauge("vg_records_capacity", "Record capacity", registry=r)
        self.records_reserved = Gauge("vg_records_reserved", "Reserved record slots", registry=r)
        self.capacity_rejected = Counter("vg_capacity_rejected_total", "Requests rejected for record capacity", registry=r)
        self.component_up = Gauge("vg_component_up", "Last observed component result; -1 means not observed",
                                  ["component"], registry=r)
        for component in ("rules", "presidio", "model_endpoint"):
            self.component_up.labels(component).set(-1)
        self.runtime_info = Gauge("vg_runtime_info", "Runtime backends (stub is not production model evaluation)",
                                  ["model_backend", "restoration_backend", "components"], registry=r)
        self.records_removed = Counter("vg_records_removed_total", "Records removed", ["reason"], registry=r)
        self.inflight = Gauge("vg_inflight_requests", "Requests being processed", registry=r)
        self.service_mode = Gauge("vg_service_mode", "1 for the current mode", ["mode"], registry=r)
        self.build_info = Gauge("vg_build_info", "Versions in use", [
            "service", "contract", "policy", "model", "prompt_detection", "prompt_assessment",
            "context_store"], registry=r)
        for mode in ("normal", "degraded", "error"):
            self.redaction_responses.labels(mode)
        for prompt in ("detection", "assessment"):
            for outcome in MODEL_OUTCOMES:
                self.model_calls.labels(prompt, outcome)
        for reason in ("model_unavailable", "model_timeout", "model_output_unparseable", "recognizer_failure"):
            for stage in ("detection", "assessment"):
                self.degraded.labels(reason, stage)

    @contextmanager
    def stage(self, name: str, timings: dict[str, float] | None = None):
        t = time.perf_counter()
        try:
            yield
        finally:
            dt = time.perf_counter() - t
            self.stage_duration.labels(name).observe(dt)
            if timings is not None:
                timings[name] = round(dt * 1000, 2)

    def set_mode(self, mode: str) -> None:
        for m in ("ready", "degraded", "down"):
            self.service_mode.labels(m).set(1 if m == mode else 0)

    def render(self) -> bytes:
        return generate_latest(self.registry)
