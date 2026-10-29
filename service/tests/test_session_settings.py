"""V3 key configuration, startup validation and tenant identity configuration."""
import base64
import json

import pytest

from vg_redactor.api.app import create_app
from vg_redactor.settings import Settings, hash_key

KEY = base64.b64encode(bytes(range(64))).decode()


def test_session_keys_loaded_from_environment(tmp_path, monkeypatch, components, model):
    config = tmp_path / "service.yaml"
    config.write_text("v3:\n  backend: aes_siv\n", encoding="utf8")
    monkeypatch.setenv("VG_SESSION_KEYS", json.dumps({"rotation1": KEY}))
    monkeypatch.setenv("VG_ACTIVE_SESSION_KEY_ID", "rotation1")
    monkeypatch.setenv("VG_API_KEYS", "synthetic-key")
    monkeypatch.setenv("VG_API_IDENTITIES", json.dumps({
        hash_key("synthetic-key"): {"tenant_id": "customer-a"}}))
    settings = Settings.load(config)
    app = create_app(settings, components, model)
    assert app.state.sessions.backend == "aes_siv"
    assert settings.v3.active_key_id == "rotation1"
    assert settings.api_identities[hash_key("synthetic-key")].tenant_id == "customer-a"
    assert KEY not in repr(settings)


@pytest.mark.parametrize("keys,active", [
    ({"bad:key": KEY}, "bad:key"),
    ({"k1": "not-base64"}, "k1"),
    ({"k1": base64.b64encode(b"short").decode()}, "k1"),
    ({"k1": KEY}, "missing"),
])
def test_invalid_keyring_fails_startup(settings, components, model, keys, active):
    settings.v3.keys, settings.v3.active_key_id = keys, active
    with pytest.raises(ValueError):
        create_app(settings, components, model)


async def test_lifespan_reports_single_store_capacity(app, client, settings):
    async with app.router.lifespan_context(app):
        import asyncio
        await asyncio.sleep(0)  # Let the initial housekeeping sweep run.
        assert app.state.metrics.records_capacity._value.get() == settings.max_records
        assert (await client.get("/readyz")).json()["mode"] == "ready"
