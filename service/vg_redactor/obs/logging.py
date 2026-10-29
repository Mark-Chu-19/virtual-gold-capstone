"""Structured logging with a field allowlist: unknown keys are dropped, so a stray
`log.info("x", text=...)` cannot leak input."""
from __future__ import annotations

import json
import logging

ALLOWED = {"event", "request_id", "route", "method", "status", "duration_ms", "stage", "tier",
           "action", "counts", "error_type", "degraded", "degraded_reason", "degraded_stage",
           "mode", "versions", "prompt", "outcome", "session_id"}


class AllowlistJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"level": record.levelname.lower(), "ts": round(record.created, 3),
                "event": record.getMessage()}
        for k, v in getattr(record, "fields", {}).items():
            if k in ALLOWED:
                data[k] = v
        return json.dumps(data, separators=(",", ":"), default=str)


def get_logger() -> logging.Logger:
    log = logging.getLogger("vg_redactor")
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(AllowlistJsonFormatter())
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log


def log_event(event: str, **fields) -> None:
    get_logger().info(event, extra={"fields": fields})
