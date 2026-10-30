"""
OpenRouter API Client with budget tracking, latency logging,
provider routing detection, and retry support.
"""

import os
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional

class BudgetExceededError(Exception):
    pass

class ModelClient:
    def __init__(self, budget_ceiling_usd: float = 5.0, timeout_s: float = 30.0):
        self.budget_ceiling_usd = budget_ceiling_usd
        self.timeout_s = timeout_s
        self.total_cost_usd = 0.0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.call_history: List[Dict[str, Any]] = []
        self.api_key = self._load_api_key()

    def _load_api_key(self) -> str:
        # Check environment variable first
        key = os.environ.get("OPENROUTER_API_KEY")
        if key:
            return key
        # Check .env file
        for p in [Path("virtual-gold-capstone/.env"), Path(".env"), Path("../virtual-gold-capstone/.env")]:
            if p.exists():
                for line in p.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == "OPENROUTER_API_KEY":
                            return v.strip()
        raise ValueError("OPENROUTER_API_KEY not found in environment or .env file.")

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 1500,
        retries: int = 3
    ) -> Dict[str, Any]:
        if self.total_cost_usd >= self.budget_ceiling_usd:
            raise BudgetExceededError(
                f"Budget ceiling reached: ${self.total_cost_usd:.4f} >= ${self.budget_ceiling_usd:.2f}"
            )

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        data_bytes = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=data_bytes,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://cmu.edu/capstone",
                "X-Title": "VirtualGold-Model-Benchmark"
            }
        )

        last_error = None
        attempt = 0
        while attempt < retries:
            attempt += 1
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    raw_text = resp.read().decode("utf-8")
                    latency = time.perf_counter() - t0
                    data = json.loads(raw_text)

                choice = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                usage = data.get("usage", {})
                cost = float(usage.get("cost", 0.0))
                p_tokens = int(usage.get("prompt_tokens", 0))
                c_tokens = int(usage.get("completion_tokens", 0))
                provider = data.get("provider", "unknown")
                returned_model = data.get("model", model)

                self.total_cost_usd += cost
                self.total_prompt_tokens += p_tokens
                self.total_completion_tokens += c_tokens

                record = {
                    "model_requested": model,
                    "model_returned": returned_model,
                    "provider": provider,
                    "latency_s": latency,
                    "prompt_tokens": p_tokens,
                    "completion_tokens": c_tokens,
                    "cost_usd": cost,
                    "attempts": attempt,
                    "success": True,
                    "content": choice,
                    "raw_response": data
                }
                self.call_history.append(record)
                return record

            except urllib.error.HTTPError as e:
                latency = time.perf_counter() - t0
                error_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
                last_error = f"HTTP {e.code}: {error_body}"
                if e.code in [429, 500, 502, 503, 504]:
                    time.sleep(2.0 * attempt)
                    continue
                else:
                    break
            except Exception as e:
                latency = time.perf_counter() - t0
                last_error = str(e)
                time.sleep(1.0 * attempt)

        record = {
            "model_requested": model,
            "model_returned": None,
            "provider": None,
            "latency_s": latency,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
            "attempts": attempt,
            "success": False,
            "error": last_error,
            "content": None,
            "raw_response": None
        }
        self.call_history.append(record)
        return record
