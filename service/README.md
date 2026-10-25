# vg_redactor: local redaction service (contract 0.4.2)

W9 skeleton: gateway, record store, model adapter, orchestrator, metrics, audit log. The Privacy
Research components (`vg_redactor/privacy/`) are wired in by default; the remaining components
(prompts and parsers) run as **stubs** (`vg_redactor/stubs/components.py`) behind the exact
signatures in `vg_redactor/contracts/components.py`.

```bash
cd service
pip install -e ".[dev,privacy]"
python -m spacy download en_core_web_lg             # Presidio's English model (~400 MB)
VG_API_KEYS=dev-key python -m vg_redactor.main      # API on :8080, metrics on 127.0.0.1:9100
python -m pytest                                    # contract, failure-injection, leak tests
```

To run without Presidio, install `pip install -e ".[dev]"` and start with
`VG_COMPONENTS=stub VG_API_KEYS=dev-key python -m vg_redactor.main`, which uses the original stubs.

Monitoring (Prometheus + Grafana, 8-panel dashboard, traffic generator): see `dashboards/README.md`.

V1 request records live in memory and require one process. V2 can use shared Redis
for independent replicas; see the v2 setup below.

| Path | Owner | What |
|---|---|---|
| `api/` `pipeline/` `model/` `records/` `obs/` | Service Eng. | gateway, orchestration, model adapter, records, metrics/logs/audit |
| `contracts/` | shared, read-only for components | types, errors, component bundle |
| `privacy/` | Privacy Research | rules, Presidio, merge, calibration, decision, pseudonymisation, context store |
| `stubs/components.py` | replaced by component owners | segmentation, prompts and parsers, restore (still in use); the rest kept for `VG_COMPONENTS=stub` |
| `config/policy.yaml` | Privacy Research / Evaluation | tier table, taxonomy, thresholds (provisional) |
| `config/service.yaml` | Service Eng. | timeouts, limits, model backend (`stub` or `ollama`) |

To plug in a real component, build the `Components` bundle in `main.py` with your function in
place of the stub; the contract tests in `tests/` should keep passing.

## V2: mapping or AES-SIV tokens

V2 supports `tokenization.mode: mapping | aes_siv`, restoration directly from message text,
shared Redis mappings, tenant/group permissions and optional cross-instance idempotency.
V1 remains compatible. Configure a persistent `VG_TOKEN_KEYS` keyring to enable v2; use
Redis for independent replicas (memory is development-only). No plaintext mapping is retained
in AES-SIV mode. Real-model token preservation still needs evaluation.

See [the v2 contract and setup](../docs/api/tokenization-v2-en.md) /
[中文说明](../docs/api/tokenization-v2-zh.md). `infra/compose.yaml` supplies development Redis;
`scripts/evaluate_tokens.py` compares both modes through local Ollama without changing notebooks.
