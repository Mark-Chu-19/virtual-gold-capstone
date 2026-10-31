"""Observe completed ASGI responses, including response construction and body send."""
import time

KNOWN_ROUTES = {"/v3/redaction", "/v3/restore", "/v3/info", "/healthz", "/readyz"}


class HttpMetricsMiddleware:
    def __init__(self, app, metrics, records):
        self.app, self.metrics, self.records = app, metrics, records

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started, status = time.perf_counter(), None

        async def observed_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
            if message["type"] != "http.response.body" or message.get("more_body", False):
                return
            m = self.metrics
            route = scope.get("route")
            path = route.path if route else scope["path"] if scope["path"] in KNOWN_ROUTES else "unmatched"
            method = scope["method"]
            state = scope.get("state", {})
            is_redaction = path == "/v3/redaction" and method == "POST"
            mode = ("error" if status >= 400 else state.get("redaction_mode", "normal")) if is_redaction else "none"
            m.http_requests.labels(path, method, str(status)).inc()
            m.http_duration.labels(path, method, str(status), mode).observe(time.perf_counter() - started)
            if is_redaction:
                m.redaction_responses.labels(mode).inc()
                if mode == "degraded":
                    reason, stage = state["redaction_degraded"]
                    m.degraded.labels(reason, stage).inc()
            stats = self.records.stats()
            m.records_active.set(stats["active"])
            m.records_reserved.set(stats["reserved"])
            m.records_capacity.set(stats["capacity"])

        await self.app(scope, receive, observed_send)
