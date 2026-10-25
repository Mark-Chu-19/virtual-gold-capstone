from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

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


class TokenSettings(BaseModel):
    default_mode: Literal["mapping", "aes_siv"] = "mapping"
    store: Literal["memory", "redis"] = "memory"
    redis_url: str = "redis://127.0.0.1:6379/0"
    active_key_id: str = "k1"
    # Inject through VG_TOKEN_KEYS, never commit keys in YAML.
    keys: dict[str, str] = Field(default_factory=dict, repr=False)


class IdentitySettings(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    groups: list[str] = Field(default_factory=lambda: ["*"], min_length=1)


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)
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
    tokenization: TokenSettings = Field(default_factory=TokenSettings)
    # SHA256 API-key digest -> tenant and group permissions. Unconfigured keys are isolated.
    api_identities: dict[str, IdentitySettings] = Field(default_factory=dict)
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
        s.host = os.environ.get("VG_HOST", s.host)
        s.port = int(os.environ.get("VG_PORT", s.port))
        s.metrics_port = int(os.environ.get("VG_METRICS_PORT", s.metrics_port))
        s.metrics_host = os.environ.get("VG_METRICS_HOST", s.metrics_host)
        s.model.stub_fault_file = os.environ.get("VG_STUB_FAULT_FILE", s.model.stub_fault_file)
        if os.environ.get("VG_TOKEN_KEYS"):
            s.tokenization.keys = json.loads(os.environ["VG_TOKEN_KEYS"])
        if os.environ.get("VG_ACTIVE_TOKEN_KEY_ID"):
            s.tokenization.active_key_id = os.environ["VG_ACTIVE_TOKEN_KEY_ID"]
        if os.environ.get("VG_TOKEN_STORE"):
            s.tokenization.store = TokenSettings(store=os.environ["VG_TOKEN_STORE"]).store
        if os.environ.get("VG_REDIS_URL"):
            s.tokenization.redis_url = os.environ["VG_REDIS_URL"]
        if os.environ.get("VG_API_IDENTITIES"):
            identities = json.loads(os.environ["VG_API_IDENTITIES"])
            s.api_identities = {k: IdentitySettings.model_validate(v) for k, v in identities.items()}
        return s


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()
