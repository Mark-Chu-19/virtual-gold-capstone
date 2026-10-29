from __future__ import annotations

from fastapi.responses import JSONResponse

from ..contracts.errors import PROBLEM_PREFIX, ProblemError


def problem_response(err: ProblemError, request_id: str, *, include_request_id: bool = True) -> JSONResponse:
    body = {"type": PROBLEM_PREFIX + err.type, "title": err.title, "status": err.status,
            "request_id": request_id}
    if not include_request_id:
        body.pop("request_id")
    if err.detail:
        body["detail"] = err.detail
    if err.violations:
        body["violations"] = err.violations
    return JSONResponse(body, status_code=err.status, media_type="application/problem+json",
                        headers={"X-Request-ID": request_id, **err.headers})


def violations_from_pydantic(errors: list[dict]) -> list[dict]:
    """Field path + error code only. Never the offending value or pydantic's message text."""
    out = []
    for e in errors:
        path = ""
        for part in e["loc"]:
            path += f"[{part}]" if isinstance(part, int) else (f".{part}" if path else str(part))
        out.append({"field": path or "body", "code": e["type"]})
    return out
