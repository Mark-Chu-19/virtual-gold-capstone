"""Model adapter layer (Service Eng). Calls the local model and classifies failures.

Prompts and parsing belong to the model-work owner. This layer invokes the supplied parser
before recording a terminal outcome, enforces the per-call budget and limits concurrency.
Unexpected parser errors propagate; only adapter failures become model unavailability.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import httpx

from ..contracts.errors import ModelCallError, ModelTimeout, ModelUnavailable, ModelOutputUnparseable
from ..obs.metrics import Metrics
from ..pipeline.deadline import Deadline


class StubModelClient:
    """Deterministic fake that speaks the stub prompt protocol (see stubs/components.py).

    Optional dev/demo fault injection: if `fault_file` names a file, its content is read on every
    call. Supported values: `down`, `timeout`, `garbage`, `slow:<milliseconds>`; anything else
    (or no file) means no fault. This lets a live demo raise the degraded rate on the dashboard.
    """
    version = "model-stub-0"

    def __init__(self, fault_file: str | None = None):
        self.fault_file = fault_file

    def _fault(self) -> str:
        if not self.fault_file:
            return ""
        try:
            return Path(self.fault_file).read_text().strip()
        except OSError:
            return ""

    async def generate(self, prompt: str, *, prompt_name: str, deadline_ms: int) -> str:
        fault = self._fault()
        if fault == "down":
            raise ModelUnavailable()
        if fault == "timeout":
            raise ModelTimeout()
        if fault == "garbage":
            return "<<not json>>"
        if fault.startswith("slow:"):
            await asyncio.sleep(int(fault[5:]) / 1000)
        head, _, payload = prompt.partition("\n")
        if head == "DETECT":
            return "[]"
        cands = json.loads(payload)
        return json.dumps([{"i": i, "private": True, "score": 0.9} for i, _ in enumerate(cands)])

    async def ping(self) -> bool:
        return self._fault() != "down"


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

    async def call(self, prompt_name: str, prompt: str, deadline: Deadline, *, parse=None):
        m = self.metrics
        t_wait = time.perf_counter()
        try:  # waiting for the slot counts against the same budget
            wait_s = max(deadline.model_budget_ms(self.call_cap_ms, self.reserve_ms), 0) / 1000
            await asyncio.wait_for(self._sem.acquire(), timeout=wait_s)
        except asyncio.TimeoutError:
            m.model_queue_wait.labels(prompt_name).observe(time.perf_counter() - t_wait)
            m.model_calls.labels(prompt_name, "timeout").inc()
            raise ModelTimeout() from None
        except asyncio.CancelledError:
            m.model_queue_wait.labels(prompt_name).observe(time.perf_counter() - t_wait)
            m.model_calls.labels(prompt_name, "cancelled").inc()
            raise
        m.model_queue_wait.labels(prompt_name).observe(time.perf_counter() - t_wait)
        t_call = time.perf_counter()
        outcome = "internal_error"
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
            except ModelCallError:
                raise
            except Exception as e:  # noqa: BLE001  adapter failures only
                raise ModelUnavailable() from e
            result = parse(raw) if parse else raw
            outcome = "ok"
            return result
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except ModelOutputUnparseable:
            outcome = "unparseable"
            raise
        except ModelCallError as e:
            outcome = e.reason.removeprefix("model_")
            raise
        finally:
            m.model_calls.labels(prompt_name, outcome).inc()
            m.model_call_duration.labels(prompt_name).observe(time.perf_counter() - t_call)
            self._sem.release()
