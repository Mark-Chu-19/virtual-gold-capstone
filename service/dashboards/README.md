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

## P2: host integration and offline evaluation

Open **Virtual Gold: Release and Offline Evaluation** using the service dashboard link. This
second dashboard reads an **optional separate exporter** on port 9101. The service remains
independent of both VG08 and labelled benchmark inputs. No benchmark run is started automatically,
and no reserved test predictions or fabricated benchmark results are committed.

### Start the optional exporter

From `service/`:

```bash
python -m vg_redactor.obs.external \
  --host-snapshot /tmp/vg08-monitoring.json \
  --evaluation-report /tmp/vg-evaluation.json
```

Native Prometheus scrapes `127.0.0.1:9101`. For Docker on macOS, add `--host 0.0.0.0` so its
`host.docker.internal:9101` target can reach it (same network exposure considerations as 9100).
Both scrape jobs are provisioned; the optional one stays DOWN until you start the exporter.
Each input can be absent independently. Missing/invalid inputs expose source availability 0
and omit that source's metrics. They never expose successful release or accuracy as zero.
Panels show source validity and producer timestamp age separately: a valid old snapshot can
still be stale. Check these before interpreting event rates.

### VG08 producer contract (integration boundary)

The VG08 host must atomically replace its snapshot with its **own cumulative counters**. This
repository has no VG08 host implementation, so this implements the receiving contract and
monitoring path, not an actual provider dispatch hook. The host must wire the publisher at its
routing/release boundaries. It must count each event once in its own process; scraping the same
snapshot does not add counts again. Counter resets on host restart are handled by Prometheus.
Keep the snapshot bounded to these exact fields:

```json
{
  "schema_version": 1,
  "updated_at": 1793404800,
  "routing": {"cloud": 0, "local": 0, "blocked": 0},
  "release": {"sent": 0, "blocked": 0, "failed": 0}
}
```

This is a schema example, not demo telemetry. `updated_at` is the producer's Unix time in seconds
when publishing. `cloud/local/blocked` are final routing decisions. `sent` means the provider
request was dispatched successfully, `blocked` means the host prevented dispatch, and `failed`
means attempted dispatch failed. Routing and release are separate event populations; local routes
need not generate release events. Neither a redaction 200 nor `degraded=false` implies release
eligibility or an actual cloud call. The existing V3 response contract is unchanged.

Publish via a temporary file and rename, rather than overwriting the live file in place. Never
include text, entity values, session/request IDs, credentials, URLs or additional arbitrary labels.

### Generate a sanitized evaluation report

The offline report command reuses `data/baseline/score.py` and accepts the repository's labelled
v1.1 format plus predictions with global text offsets or service field offsets. Supply the
**exact same set of email IDs** in gold and predictions; explicit `spans: []` means nothing was
masked. Missing records, duplicate IDs and invalid prediction offsets are rejected. HTTP V3
responses omit spans: obtain predictions from the offline harness, not by guessing offsets from
redacted HTTP text. `action: retain` predictions are excluded from mask coverage.

Create a metadata JSON file with these exact version identifiers (replace example values):

```json
{
  "run": "dev-run-001",
  "dataset": "baseline-v1.1",
  "split": "dev",
  "model": "model-version",
  "policy": "policy-version",
  "prompt_detection": "detection-version",
  "prompt_assessment": "assessment-version",
  "calibration": "calibration-version"
}
```

Then, from `service/`:

```bash
python -m vg_redactor.obs.evaluation \
  --gold ../data/baseline/baseline_v1.1_dev.jsonl \
  --pred /path/to/dev-predictions.jsonl \
  --metadata /path/to/metadata.json \
  --out /tmp/vg-evaluation.json
```

This writes an atomic aggregate report with **no email IDs, raw text, misses or entity values**.
The exporter accepts `dev`, `validation`, or `test` split identifiers, but does not verify dataset
provenance; callers must supply truthful versions and the correct split. Reserved test evaluation
remains a deliberate action after pipeline freeze. The dashboard displays the **latest imported
run** as instant values, not historical time series mixing different datasets/configurations.

### Evaluation definitions

* **Required span leak ratio by tier**: missed required spans / required spans of the tier,
  including FACT. An entity is caught at >=95% alphanumeric coverage; FACT at >=50%, matching
  the repository's coverage thresholds. Tiers with no required spans have no ratio.
* **Emails leaking entities by tier**: existing scorer's `leak_rate_by_tier`, with all evaluated
  emails as denominator. FACT is excluded by that scorer and shown separately as FACT recall.
  This differs from the span ratio above, and both panels state their denominator.
* **Public labelled spans touched**: `optional_masked`, any overlap with retain-labelled spans.
  **Extra masks**: predictions overlapping no label. These are limited usefulness measures,
  not a task-answer utility score or whole-document character over-redaction percentage.
* Both leak metrics measure residual exposure in benchmark outputs. They do not observe actual
  cloud leakage and are never derived from live HTTP status or `vg_spans_total`.

### Optional calibration evaluation

Add `--calibration-samples /path/to/heldout-candidates.jsonl` to the report command. Every line
must contain exactly `raw`, `calibrated` (finite probabilities) and `is_private` (boolean gold
label). Use independently labelled held-out candidates, the same set for both scores, and exclude
deterministic policy overrides. These samples cannot be recovered from aggregate HTTP status or
unlabelled audit scores. Without them the calibration panels show No data.

ECE uses ten equal-width bins: [0,0.1), … [0.9,1], weighted by candidate count. The dashboard shows
raw/calibrated ECE, sample count, mean score and observed private fraction by occupied bin. It
reports calibration on the supplied sample population; it does not establish detector recall.
