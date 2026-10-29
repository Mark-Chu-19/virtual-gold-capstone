"""Prometheus metrics. Every label has a small fixed set of values; none ever holds text or ids."""
from __future__ import annotations

from contextlib import contextmanager
import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

_B = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 6, 8, 12, 15, 20)
STAGES = ("validate", "segment", "detect_rules", "detect_presidio", "detect_model", "merge",
          "assess_model", "calibrate", "decide", "pseudonymize", "audit")


class Metrics:
    def __init__(self, registry: CollectorRegistry | None = None):
        r = self.registry = registry or CollectorRegistry()
        self.http_requests = Counter("vg_http_requests_total", "HTTP requests",
                                     ["route", "method", "status"], registry=r)
        self.request_duration = Histogram("vg_request_duration_seconds", "End-to-end latency",
                                          ["route", "mode"], buckets=_B, registry=r)
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
        self.records_removed = Counter("vg_records_removed_total", "Records removed", ["reason"], registry=r)
        self.inflight = Gauge("vg_inflight_requests", "Requests being processed", registry=r)
        self.service_mode = Gauge("vg_service_mode", "1 for the current mode", ["mode"], registry=r)
        self.build_info = Gauge("vg_build_info", "Versions in use", [
            "service", "contract", "policy", "model", "prompt_detection", "prompt_assessment",
            "context_store"], registry=r)

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
