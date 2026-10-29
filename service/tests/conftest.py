import asyncio

import httpx
import pytest

from vg_redactor.api.app import create_app
from vg_redactor.contracts.errors import ModelTimeout, ModelUnavailable
from vg_redactor.contracts.policy import Policy
from vg_redactor.model.client import StubModelClient
from vg_redactor.obs.metrics import Metrics
from vg_redactor.settings import CONFIG_DIR, Settings, hash_key
from vg_redactor.stubs.components import StubContextStore, build_stub_components

KEY = "test-key"
HEADERS = {"Authorization": f"Bearer {KEY}"}

EMAIL_REQ = {
    "purpose": "Summarize this email",
    "email": {
        "subject": "Support question",
        "from": {"name": "Example Sender", "address": "sender@example.test"},
        "to": [{"name": "Support Team", "address": "support@example.test"}],
        "body": "Please call me at 202-555-0102. SSN 123-45-6789.",
        "thread": [{"message_id": "m-1", "source": "quoted_thread",
                    "text": "Our public support line is 800-555-0100."}],
    },
}


class ScriptedModel(StubModelClient):
    """Stub model whose behaviour per prompt can be switched: ok | down | timeout | garbage | hang."""
    version = "model-scripted"

    def __init__(self):
        super().__init__()
        self.mode = {"detection": "ok", "assessment": "ok"}
        self.up = True

    async def generate(self, prompt, *, prompt_name, deadline_ms):
        m = self.mode[prompt_name]
        if m == "down":
            raise ModelUnavailable()
        if m == "timeout":
            raise ModelTimeout()
        if m == "garbage":
            return "<<not json>>"
        if m == "hang":
            await asyncio.sleep(60)
        return await super().generate(prompt, prompt_name=prompt_name, deadline_ms=deadline_ms)

    async def ping(self):
        return self.up


@pytest.fixture
def settings(tmp_path):
    return Settings(api_key_hashes={hash_key(KEY)}, audit_log_path=str(tmp_path / "audit.jsonl"),
                    timeout_ms=3000, model_call_timeout_ms=1000, degraded_reserve_ms=300)


@pytest.fixture
def model():
    return ScriptedModel()


@pytest.fixture
def components():
    return build_stub_components(Policy.load(CONFIG_DIR / "policy.yaml"),
                                 StubContextStore(term_list={"Project Falcon"}))


@pytest.fixture
def app(settings, components, model):
    return create_app(settings, components, model, Metrics())


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t", headers=HEADERS) as c:
        yield c


def post_json(client, url, body, **kw):
    return client.post(url, content=__import__("json").dumps(body),
                       headers={"Content-Type": "application/json", **kw.pop("headers", {})}, **kw)
