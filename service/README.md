# vg_redactor: local redaction service (contract 0.4.2)

W9 skeleton: gateway, record store, model adapter, orchestrator, metrics, audit log. Components
that other teammates own run as **stubs** (`vg_redactor/stubs/components.py`) behind the exact
signatures in `vg_redactor/contracts/components.py`.

```bash
cd service
pip install -e ".[dev]"
VG_API_KEYS=dev-key python -m vg_redactor.main      # API on :8080, metrics on 127.0.0.1:9100
python -m pytest                                    # contract, failure-injection, leak tests
```

Single process only: request records live in memory, so run one worker.

| Path | Owner | What |
|---|---|---|
| `api/` `pipeline/` `model/` `records/` `obs/` | Service Eng. | gateway, orchestration, model adapter, records, metrics/logs/audit |
| `contracts/` | shared, read-only for components | types, errors, component bundle |
| `stubs/components.py` | replaced by component owners | segmentation, rules, Presidio, prompts, calibration, decision, pseudonymisation |
| `config/policy.yaml` | Privacy Research / Evaluation | tier table, taxonomy, thresholds (provisional) |
| `config/service.yaml` | Service Eng. | timeouts, limits, model backend (`stub` or `ollama`) |

To plug in a real component, build the `Components` bundle in `main.py` with your function in
place of the stub; the contract tests in `tests/` should keep passing.
