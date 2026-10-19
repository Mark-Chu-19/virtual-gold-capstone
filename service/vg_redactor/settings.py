from __future__ import annotations

import hashlib
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class ModelSettings(BaseModel):
    backend: str = "stub"
    ollama_url: str = "http://127.0.0.1:11434"
    model_name: str = "llama3:8b"
    # Dev/demo only (backend "stub"): a file whose content selects an injected model fault, see
    # dashboards/README.md. Unset means no fault injection.
    stub_fault_file: str | None = None


class Settings(BaseModel):
    timeout_ms: int = 15000
    model_call_timeout_ms: int = 6000
    degraded_reserve_ms: int = 1500
    model_concurrency: int = 1
    max_request_bytes: int = 262144
    default_ttl_seconds: int = 3600
    max_ttl_seconds: int = 86400
    max_records: int = 1000
    allow_list_in_degraded: bool = False
    audit_log_path: str | None = None
    metrics_port: int = 9100
    # Metrics are local-only by default. Only widen this for Docker on macOS (dashboards/README.md).
    metrics_host: str = "127.0.0.1"
    model: ModelSettings = Field(default_factory=ModelSettings)
    # sha256 hex digests of accepted API keys
    api_key_hashes: set[str] = Field(default_factory=set)
    service_version: str = "0.4.2"
    contract_version: str = "0.4.2"

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        data = yaml.safe_load((path or CONFIG_DIR / "service.yaml").read_text(encoding="utf8")) or {}
        s = cls(**data)
        keys = [k.strip() for k in os.environ.get("VG_API_KEYS", "").split(",") if k.strip()]
        s.api_key_hashes = {hash_key(k) for k in keys}
        s.metrics_host = os.environ.get("VG_METRICS_HOST", s.metrics_host)
        s.model.stub_fault_file = os.environ.get("VG_STUB_FAULT_FILE", s.model.stub_fault_file)
        return s


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()
