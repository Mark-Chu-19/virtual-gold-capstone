# Monitoring: Prometheus and Grafana

The provisioned **Virtual Gold: Redaction Service** dashboard follows the eight modules in the
midterm presentation (slides 36–37). It shows live service behavior; it does not measure privacy
accuracy. Default view: last 15 minutes, 5-second refresh, one selected service instance.

## Run locally

From `service/`, in separate terminals:

```bash
VG_API_KEYS=dev-key VG_METRICS_HOST=0.0.0.0 python -m vg_redactor.main
docker compose -f dashboards/docker-compose.yml up -d
python scripts/traffic.py --key dev-key --rate 5 --duration 300
```

Grafana: http://127.0.0.1:3000, user `admin`, password `$GRAFANA_ADMIN_PASSWORD` (default `admin`).
Prometheus: http://127.0.0.1:9090. Both monitoring UIs bind to loopback.

On macOS Docker needs the host metrics server to listen on a reachable address. Setting
`VG_METRICS_HOST=0.0.0.0` makes metrics port 9100 reachable on your network during the demo.
For a loopback-only install, run native Prometheus with `prometheus.native.yml`, install Grafana,
and configure its provisioned datasource URL as `http://127.0.0.1:9090`.

Default model backend is **stub**. The versions/runtime table reports the actual model backend,
restoration backend, and `stub` or `mixed` components. Mixed means real privacy components with
remaining stub prompts/parsers; switching to Ollama alone does not make those components real.

## P0: eight core modules

| Module | Display and measurement |
|---|---|
| Requests and errors | Selected-range count and status-code RPS for **POST** `/v3/redaction`; DELETE is excluded |
| Availability | 2xx / (2xx + 5xx), excluding 4xx; degraded 200 counts as available |
| Latency | Separate HTTP end-to-end and pipeline p50/p95/p99, grouped by processing mode |
| Stages | p95 by stage, including validation; concurrent detector timings must not be summed |
| Degraded responses | Successful degraded / all successful redactions; causes and stages in a separate rate graph |
| Model calls | Mutually exclusive final outcomes by detection/assessment prompt |
| Sessions | Active + reserved against capacity; deletions/expiry and explicit capacity rejections |
| Readiness and versions | Scrape UP/DOWN, model endpoint probe, last rules/Presidio result and runtime versions |

### Metric boundaries

* `vg_http_duration_seconds{route,method,status,mode}` starts before gateway/auth handling and
  ends after sending the final ASGI response body. It includes validation, session work, pipeline
  and serialization, but excludes client network transit. All HTTP routes are measured. Mode is
  `normal`, `degraded`, or `error` for POST redaction, and `none` for other routes.
* `vg_pipeline_duration_seconds{route="redactions",mode}` measures the orchestrator only,
  including failed pipeline attempts. Replaces the ambiguously named `vg_request_duration_seconds`.
  A later serialization failure does not change a pipeline that already completed successfully.
  Never subtract p95 values to infer HTTP overhead.
* `vg_redaction_responses_total{mode}` counts completed HTTP responses only. Final errors after
  fallback count as `error`, never successful degradation. `vg_degraded_total{reason,stage}` is
  incremented only when the final degraded response body has been sent successfully.
* `vg_model_calls_total{prompt,outcome}` counts one terminal result per gateway invocation:
  `ok` **after parsing**, `unavailable`, `timeout`, `unparseable`, or `cancelled`. Queue timeout
  counts as an invocation; calls cancelled by an enclosing request are explicit. A raw model
  response rejected by the parser contributes only `unparseable`.
* Model endpoint probe is reachability, not inference readiness. Rules/Presidio state is the
  **last observed execution**, with -1 before first use, 0 on failure, 1 on success. It is not a
  continuous component probe. `vg_service_mode` remains a compatibility metric based on model
  reachability; the dashboard deliberately names the probe directly.
* Capacity uses active **plus reserved** slots. `vg_capacity_rejected_total` counts only
  `capacity-exhausted`, not unrelated 503s. Gauges refresh after HTTP responses and every 10s.

### Empty and unavailable data

No eligible requests gives an undefined ratio (No data), never 100% availability. Check the
separate scrape card: DOWN means metrics cannot be collected; UP with no requests is idle.
Component states are instant queries rather than historical last-known state cards. Counters
use `rate`/`increase` and tolerate restarts; selected-range counts are Prometheus estimates and
may be fractional. Quantiles on sparse traffic should be interpreted with request volume.

### Demo and acceptance scenarios

Set `VG_STUB_FAULT_FILE=/tmp/vg_fault` before launching the stub backend, then write `down`,
`timeout`, `garbage`, or `slow:2500` to that file. Remove it to restore normal behavior.
Use recognizer failure injection in tests to exercise Presidio degradation. Also verify normal
redaction/restore/delete, session expiry, capacity exhaustion, no traffic and scrape outage.
Tests cover one final outcome per model call, delayed serialization in HTTP but not pipeline
latency, authentication failures, capacity reservation, and failures after fallback.

## Dashboard source

Edit `build_dashboard.py`, then run:

```bash
python dashboards/build_dashboard.py
```

Commit both the builder and generated `grafana/dashboards/*.json`. File provisioning is read-only
in the Grafana UI; changes reload automatically. Metrics labels never contain email text, entity
values, API keys, request IDs, session IDs or tenant identifiers.

## P1: expandable diagnostics

Expand the Diagnostics row for model queue wait and execution/parse p50/p95/p99, in-flight
redactions, per-stage p95 trends, endpoint/status breakdowns, HTTP p95 by status, rendered span
decisions by tier/action/mode, and the proportion of model calls with valid parsed output.

The **Diagnostic route** and **Diagnostic method** selectors affect only the operation-specific
panels. Select `/v3/restore` + POST for restoration or `/v3/redaction` + DELETE for deletion;
top-level service KPIs always measure POST redaction. Model queue-only timeouts have a queue
sample but no execution sample. Rendered span counts may include requests failing later in
audit/serialization; they are processing activity, not completed responses or privacy accuracy.
