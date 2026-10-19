"""Exceptions shared by components and the gateway. Messages must never contain input text."""
from __future__ import annotations

PROBLEM_PREFIX = "urn:vg:problem:"


class ProblemError(Exception):
    """An error that maps to an RFC 9457 problem+json response."""

    def __init__(self, status: int, type_: str, title: str, *, detail: str | None = None,
                 violations: list[dict] | None = None, headers: dict[str, str] | None = None):
        super().__init__(title)
        self.status, self.type, self.title = status, type_, title
        self.detail, self.violations, self.headers = detail, violations, headers or {}


def validation_failed(violations: list[dict]) -> ProblemError:
    return ProblemError(422, "validation-failed", "Request failed validation", violations=violations)


def high_tier_fixed(field: str) -> ProblemError:
    return validation_failed([{"field": field, "code": "high_tier_fixed"}])


class CapacityExhausted(ProblemError):
    def __init__(self, retry_after: int = 5):
        super().__init__(503, "capacity-exhausted", "Request-record capacity exhausted",
                         headers={"Retry-After": str(retry_after)})


class DeadlineExceeded(ProblemError):
    def __init__(self):
        super().__init__(504, "deadline-exceeded", "End-to-end timeout exceeded; content was not processed")


class RecordNotFound(ProblemError):
    def __init__(self):
        super().__init__(404, "not-found", "No record with this id")


class RecordGone(ProblemError):
    def __init__(self):
        super().__init__(410, "gone", "Record expired or was deleted")


class ModelCallError(Exception):
    """The local model could not be used. `reason` is the degraded_reason value."""
    reason = "model_unavailable"


class ModelUnavailable(ModelCallError):
    reason = "model_unavailable"


class ModelTimeout(ModelCallError):
    reason = "model_timeout"


class ModelOutputUnparseable(ModelCallError):
    reason = "model_output_unparseable"


class RuleEngineError(Exception):
    """The rule engine failed; there is no safe fallback, so the request ends in a 500."""


class RecognizerError(Exception):
    """Presidio failed; the request continues in degraded mode (recognizer_failure)."""
