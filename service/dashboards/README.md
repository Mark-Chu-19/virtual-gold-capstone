# Monitoring: Prometheus and Grafana

Local monitoring stack for the redaction service. One dashboard, **Virtual Gold: Redaction Service**, with the
eight P0 panels from the schedule. Everything stays on the machine; both web UIs listen on 127.0.0.1 only.

| File | Purpose |
|---|---|
| `docker-compose.yml` | Prometheus and Grafana containers |
| `prometheus.yml` | scrape config for Docker (target `host.docker.internal:9100`) |
| `prometheus.native.yml` | same job for a Prometheus installed without Docker (target `127.0.0.1:9100`) |
| `grafana/provisioning/` | data source and dashboard provider, loaded automatically |
| `grafana/dashboards/vg-redactor.json` | the dashboard, committed as code |
| `../scripts/traffic.py` | synthetic traffic for the dashboard and the demo |

## Run it (Docker)

```bash
cd service
VG_API_KEYS=dev-key VG_METRICS_HOST=0.0.0.0 python -m vg_redactor.main     # terminal 1: the service
docker compose -f dashboards/docker-compose.yml up -d                       # terminal 2: monitoring
python scripts/traffic.py --key dev-key --rate 5 --duration 300             # terminal 3: traffic
```

Open Grafana at http://127.0.0.1:3000 (user `admin`, password `$GRAFANA_ADMIN_PASSWORD`, default `admin`) and the
dashboard under the folder **Virtual Gold**. Prometheus is at http://127.0.0.1:9090 (Status, Targets should show
`vg-redactor` as UP).

**Docker on macOS:** a container cannot reach a service that listens on the host's loopback address only. Metrics
are bound to `127.0.0.1` by default (contract: local only), so for Docker you must set `VG_METRICS_HOST=0.0.0.0`
as above. That exposes port 9100 (counts and timings only, never text) to your network while it runs, so use it
on a trusted network or switch to the native install below. On Linux you can instead run Prometheus with
host networking and keep the default.

## Run it without Docker

```bash
brew install prometheus grafana
prometheus --config.file=dashboards/prometheus.native.yml                  # :9090
# Grafana: copy grafana/provisioning/* and grafana/dashboards/* into your Grafana paths, and change the data
# source URL in provisioning/datasources/prometheus.yml to http://127.0.0.1:9090
```

The service keeps the default `VG_METRICS_HOST=127.0.0.1` in this mode.

## Demo: show the degraded path

The stub model reads a fault file on every call (stub backend only, never the real Ollama client):

```bash
export VG_STUB_FAULT_FILE=/tmp/vg_fault          # before starting the service
echo down    > /tmp/vg_fault                     # model_unavailable: degraded rate rises, service mode turns degraded
echo timeout > /tmp/vg_fault                     # model_timeout
echo garbage > /tmp/vg_fault                     # model_output_unparseable
echo slow:2500 > /tmp/vg_fault                   # slow model, higher latency
rm /tmp/vg_fault                                 # back to normal
```

## Panels

| # | Panel | Metric |
|---|---|---|
| 1 | Request rate and status codes | `vg_http_requests_total` |
| 2 | Availability, 2xx / (2xx + 5xx) | `vg_http_requests_total` |
| 3 | End-to-end latency p50/p95/p99, normal vs degraded | `vg_request_duration_seconds` |
| 4 | Per-stage time (p95) | `vg_stage_duration_seconds` |
| 5 | Degraded rate and reasons | `vg_degraded_total` |
| 6 | Model-call outcomes per prompt | `vg_model_calls_total` |
| 7 | Records and capacity | `vg_records_active`, `vg_records_capacity`, `vg_records_removed_total` |
| 8 | Service mode and versions in use | `vg_service_mode`, `vg_build_info` |

The dashboard is provisioned read-only: edit `grafana/dashboards/vg-redactor.json` (or export from the UI and
paste the JSON) and commit it. Benchmark leak rate is measured offline with labels; these panels show service
health, not accuracy.
