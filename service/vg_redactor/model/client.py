"""Model adapter layer (Service Eng). Calls the local model and classifies failures.

Prompts and output parsing belong to the model-work owner; this layer only moves a prompt string
in and a raw string out, enforces the per-call budget, limits concurrency and counts outcomes.
"""
from __future__ import annotations

import asyncio
import json
import time

import httpx

from ..contracts.errors import ModelCallError, ModelTimeout, ModelUnavailable
from ..obs.metrics import Metrics
from ..pipeline.deadline import Deadline


class StubModelClient:
    """Deterministic fake that speaks the stub prompt protocol (see stubs/components.py)."""
    version = "model-stub-0"

    async def generate(self, prompt: str, *, prompt_name: str, deadline_ms: int) -> str:
        head, _, payload = prompt.partition("\n")
        if head == "DETECT":
            return "[]"
        cands = json.loads(payload)
        return json.dumps([{"i": i, "private": True, "score": 0.9} for i, _ in enumerate(cands)])

    async def ping(self) -> bool:
        return True


class OllamaModelClient:
    def __init__(self, base_url: str, model_name: str):
        self.base_url, self.model_name = base_url.rstrip("/"), model_name
        self.version = model_name
        self._http = httpx.AsyncClient()

    async def generate(self, prompt: str, *, prompt_name: str, deadline_ms: int) -> str:
        try:
            r = await self._http.post(
                f"{self.base_url}/api/generate", timeout=deadline_ms / 1000,
                json={"model": self.model_name, "prompt": prompt, "stream": False, "format": "json"})
            r.raise_for_status()
            return r.json()["response"]
        except httpx.TimeoutException as e:
            raise ModelTimeout() from e
        except (httpx.TransportError, httpx.HTTPStatusError, KeyError, ValueError) as e:
            raise ModelUnavailable() from e

    async def ping(self) -> bool:
        try:
            return (await self._http.get(f"{self.base_url}/api/tags", timeout=2)).status_code == 200
        except httpx.HTTPError:
            return False


class ModelGateway:
    """What the orchestrator calls: slot queue + budget + metrics around a raw client."""

    def __init__(self, client, metrics: Metrics, *, concurrency: int, call_cap_ms: int,
                 reserve_ms: int):
        self.client, self.metrics = client, metrics
        self.call_cap_ms, self.reserve_ms = call_cap_ms, reserve_ms
        self._sem = asyncio.Semaphore(concurrency)

    @property
    def version(self) -> str:
        return self.client.version

    async def call(self, prompt_name: str, prompt: str, deadline: Deadline) -> str:
        m = self.metrics
        t_wait = time.perf_counter()
        try:  # waiting for the slot counts against the same budget
            wait_s = max(deadline.model_budget_ms(self.call_cap_ms, self.reserve_ms), 0) / 1000
            await asyncio.wait_for(self._sem.acquire(), timeout=wait_s)
        except asyncio.TimeoutError:
            m.model_queue_wait.labels(prompt_name).observe(time.perf_counter() - t_wait)
            m.model_calls.labels(prompt_name, "timeout").inc()
            raise ModelTimeout() from None
        m.model_queue_wait.labels(prompt_name).observe(time.perf_counter() - t_wait)
        t_call = time.perf_counter()
        try:
            budget = deadline.model_budget_ms(self.call_cap_ms, self.reserve_ms)
            if budget <= 0:
                raise ModelTimeout()
            try:
                raw = await asyncio.wait_for(
                    self.client.generate(prompt, prompt_name=prompt_name, deadline_ms=budget),
                    timeout=budget / 1000)
            except asyncio.TimeoutError as e:
                raise ModelTimeout() from e
            m.model_calls.labels(prompt_name, "ok").inc()
            return raw
        except ModelCallError as e:
            m.model_calls.labels(prompt_name, e.reason.removeprefix("model_")).inc()
            raise
        except Exception as e:  # noqa: BLE001  any other adapter failure counts as unavailable
            m.model_calls.labels(prompt_name, "unavailable").inc()
            raise ModelUnavailable() from e
        finally:
            m.model_call_duration.labels(prompt_name).observe(time.perf_counter() - t_call)
            self._sem.release()

    def note_unparseable(self, prompt_name: str) -> None:
        """Called by the orchestrator when a component's parser rejects the model output."""
        self.metrics.model_calls.labels(prompt_name, "unparseable").inc()
