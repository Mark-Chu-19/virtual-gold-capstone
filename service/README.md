# vg_redactor: local redaction service (V3)

Gateway, record store, model adapter, orchestrator, metrics and audit log. The Privacy
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

V3 records live in memory. Run one worker; restart loses all restoration records.

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

## V3 API

Only V3 is served. V1/V2 routes and their token/conversation/Redis machinery have been removed;
they were development iterations and were never offered as supported customer APIs.

| Method | Path | JSON request | Success |
|---|---|---|---|
| POST | `/v3/redaction` | `{purpose, email, policy?}` | `{session_id, redacted_email, redacted_purpose, expires_at, degraded}` |
| POST | `/v3/restore` | `{session_id, text}` | `{restored_text}` |
| DELETE | `/v3/redaction` | `{session_id}` | 204, no body |
| GET | `/v3/info` | none | versions, policy, limits and restoration configuration |
| GET | `/healthz` | none | `{status: "ok"}` |
| GET | `/readyz` | none | `{mode, components}` |

All routes except health/readiness require `Authorization: Bearer <API_KEY>` from `VG_API_KEYS`.
By default each key is an isolated tenant. `VG_API_IDENTITIES` maps SHA256 key digests to
`{tenant_id}` when multiple keys should share records. Clients retain only `session_id`;
`X-Request-ID` is an optional diagnostic header. Each redaction is independent, with no
client-provided session, group or conversation context. Literal placeholders already in the input
are preserved without colliding with generated labels. Expanded restoration output is limited by
`max_restored_bytes` (default 1 MiB), checked before replacement. Invalid Unicode is rejected before
retention; timed-out workers and response-serialization failures cannot leave usable records.

Backend selection is internal (`v3.backend`): `mapping` is the default, `aes_siv` encrypts the
entire mapping while preserving short placeholders. AES needs a persistent `VG_SESSION_KEYS`
JSON keyring (`{key_id: base64_encoded_64_bytes}`); `VG_ACTIVE_SESSION_KEY_ID` selects the active
key. Keep old keys until their records expire. Keys are never returned or committed.
There is no Redis dependency or shared session storage. Service version is 3.0.0, contract v3.

See the [English V3 contract](../docs/api/sessions-v3-en.md) /
[中文接口说明](../docs/api/sessions-v3-zh.md). Earlier API documents are historical design references.
