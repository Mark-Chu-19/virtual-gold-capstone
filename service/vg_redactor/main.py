"""V3 service entry point. Session records are process-local; run one worker."""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import uvicorn
from prometheus_client import start_http_server

from .api.app import create_app
from .contracts.components import Components
from .contracts.policy import Policy
from .model.client import OllamaModelClient, StubModelClient
from .obs.metrics import Metrics
from .privacy import (FileContextStore, decide, detect_rules, load_table, make_calibrate,
                      make_detect_presidio, make_merge, pseudonymize)
from .settings import CONFIG_DIR, Settings
from .stubs.components import build_stub_components


def build_components(config_dir: Path = CONFIG_DIR, *, presidio: bool = True,
                     analyzer: Any | None = None) -> Components:
    """Stubs, with the Privacy Research components swapped in. Model Work's prompts and parsers
    replace the remaining stubs here when they are ready."""
    policy = Policy.load(config_dir / "policy.yaml")
    ctx = FileContextStore.load(config_dir / "context_store.yaml", policy.high_types())
    swapped: dict[str, Any] = dict(
        detect_rules=detect_rules, merge_candidates=make_merge(policy),
        calibrate=make_calibrate(load_table(config_dir / "calibration.yaml")),
        decide=decide, pseudonymize=pseudonymize, policy=policy, context_store=ctx)
    if presidio:  # loads the spaCy model once, at startup
        swapped["detect_presidio"] = make_detect_presidio(analyzer)
    return replace(build_stub_components(policy, ctx), **swapped)


def build():
    settings = Settings.load()
    # VG_COMPONENTS=stub runs the original stubs (no Presidio install needed).
    if os.environ.get("VG_COMPONENTS") == "stub":
        components = build_stub_components(Policy.load(CONFIG_DIR / "policy.yaml"))
    else:
        components = build_components()
    client = (OllamaModelClient(settings.model.ollama_url, settings.model.model_name)
              if settings.model.backend == "ollama" else StubModelClient(settings.model.stub_fault_file))
    metrics = Metrics()
    return settings, create_app(settings, components, client, metrics), metrics


if __name__ == "__main__":
    settings, app, metrics = build()
    start_http_server(settings.metrics_port, addr=settings.metrics_host, registry=metrics.registry)
    uvicorn.run(app, host=settings.host, port=settings.port)  # one process per instance
