"""Entry point: `python -m vg_redactor.main` (single process; records live in memory)."""
from __future__ import annotations

import uvicorn
from prometheus_client import start_http_server

from .api.app import create_app
from .contracts.policy import Policy
from .model.client import OllamaModelClient, StubModelClient
from .obs.metrics import Metrics
from .settings import CONFIG_DIR, Settings
from .stubs.components import build_stub_components


def build():
    settings = Settings.load()
    components = build_stub_components(Policy.load(CONFIG_DIR / "policy.yaml"))
    client = (OllamaModelClient(settings.model.ollama_url, settings.model.model_name)
              if settings.model.backend == "ollama" else StubModelClient())
    metrics = Metrics()
    return settings, create_app(settings, components, client, metrics), metrics


if __name__ == "__main__":
    settings, app, metrics = build()
    start_http_server(settings.metrics_port, addr="127.0.0.1", registry=metrics.registry)
    uvicorn.run(app, host="127.0.0.1", port=8080)  # one worker only: records are in-process
