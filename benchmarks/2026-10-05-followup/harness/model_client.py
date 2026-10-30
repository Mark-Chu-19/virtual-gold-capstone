"""
Model client supporting OpenRouter (with pinned provider + quantization routing),
Groq direct LPU inference (including Free Tier rate-limit pacing), and local Ollama/vLLM inference.
Implements Section 2.1, Section 3.2, and Section 4.2 of VPC_MODEL_EVALUATION_PLAN.md.
"""

import os
import re
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional

class BudgetExceededError(Exception):
    pass

# Canonical 13-Model OpenRouter & Groq Provider-Pinning Registry (Table 3.2 & Section 4.2)
VPC_MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Tier 1 Anchors
    "meta-llama/llama-3.1-8b-instruct": {
        "id": "A0",
        "tier": "Tier1_Anchor",
        "provider_order": ["DeepInfra", "Novita"],
        "quantizations": ["fp8"],
        "reasoning_mode": "none",
        "default_max_tokens": 2048,
        "hf_fp8": "neuralmagic/Meta-Llama-3.1-8B-Instruct-FP8",
        "hf_int4": "hugging-quants/Meta-Llama-3.1-8B-Instruct-AWQ-INT4",
    },
    "qwen/qwen3.5-9b": {
        "id": "A1",
        "tier": "Tier1_Anchor",
        "provider_order": ["SiliconFlow", "DeepInfra"],
        "quantizations": ["fp8", "bf16"],
        "reasoning_mode": "hybrid",
        "default_max_tokens": 2048,
        "hf_fp8": "RedHatAI/Qwen3.5-9B-FP8-dynamic",
        "hf_int4": "cyankiwi/Qwen3.5-9B-AWQ-4bit",
    },
    # Tier 1 Candidates (1x L40S 48GB FP8 / 1x L4 24GB INT4)
    "mistralai/mistral-small-3.2-24b-instruct": {
        "id": "S1",
        "tier": "Tier1_Small",
        "provider_order": ["DeepInfra", "Venice"],
        "quantizations": ["fp8"],
        "reasoning_mode": "none",
        "default_max_tokens": 2048,
        "hf_fp8": "RedHatAI/Mistral-Small-3.2-24B-Instruct-2506-FP8",
        "hf_int4": "jeffcookio/Mistral-Small-3.2-24B-Instruct-2506-awq-sym",
    },
    "google/gemma-4-26b-a4b-it": {
        "id": "S2",
        "tier": "Tier1_Small",
        "provider_order": ["DeepInfra", "SiliconFlow"],
        "quantizations": ["fp8"],
        "reasoning_mode": "hybrid",
        "default_max_tokens": 2048,
        "hf_fp8": "RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic",
        "hf_int4": "cyankiwi/gemma-4-26B-A4B-it-AWQ-4bit",
    },
    "qwen/qwen3.6-35b-a3b": {
        "id": "S3",
        "tier": "Tier1_Small",
        "provider_order": ["DeepInfra", "Parasail", "AkashML"],
        "quantizations": ["fp8"],
        "reasoning_mode": "hybrid",
        "default_max_tokens": 2048,
        "hf_fp8": "Qwen/Qwen3.6-35B-A3B-FP8",
        "hf_int4": "QuantTrio/Qwen3.6-35B-A3B-AWQ",
    },
    "qwen/qwen3-32b": {
        "id": "S4",
        "tier": "Tier1_Small",
        "provider_order": ["DeepInfra", "SiliconFlow"],
        "quantizations": ["fp8"],
        "reasoning_mode": "hybrid",
        "default_max_tokens": 2048,
        "hf_fp8": "Qwen/Qwen3-32B",
        "hf_int4": "Qwen/Qwen3-32B-AWQ",
    },
    # Tier 2 Candidates (1x H100/A100 80GB INT4/MXFP4)
    "meta-llama/llama-3.3-70b-instruct": {
        "id": "M0",
        "tier": "Tier2_Medium",
        "provider_order": ["DeepInfra", "Parasail", "AkashML"],
        "quantizations": ["fp8"],
        "reasoning_mode": "none",
        "default_max_tokens": 2048,
        "hf_fp8": "RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic",
        "hf_int4": "casperhansen/llama-3.3-70b-instruct-awq",
    },
    "openai/gpt-oss-120b": {
        "id": "M1",
        "tier": "Tier2_Medium",
        "provider_order": ["CoreWeave", "Novita", "Near AI"],
        "quantizations": ["fp4"],
        "reasoning_mode": "mandatory_low",
        "default_max_tokens": 4096,
        "groq_model": "openai/gpt-oss-120b",
        "hf_fp8": "openai/gpt-oss-120b",
        "hf_int4": "openai/gpt-oss-120b",
    },
    "meta-llama/llama-4-scout": {
        "id": "M2",
        "tier": "Tier2_Medium",
        "provider_order": ["DeepInfra"],
        "quantizations": ["fp8"],
        "reasoning_mode": "none",
        "default_max_tokens": 2048,
        "hf_fp8": "nvidia/Llama-4-Scout-17B-16E-Instruct-FP8",
        "hf_int4": "RedHatAI/Llama-4-Scout-17B-16E-Instruct-quantized.w4a16",
    },
    "qwen/qwen3.5-122b-a10b": {
        "id": "M3",
        "tier": "Tier2_Medium",
        "provider_order": ["SiliconFlow", "AtlasCloud"],
        "quantizations": ["fp8"],
        "reasoning_mode": "hybrid",
        "default_max_tokens": 2048,
        "hf_fp8": "Qwen/Qwen3.5-122B-A10B-FP8",
        "hf_int4": "Qwen/Qwen3.5-122B-A10B-GPTQ-Int4",
    },
    # Tier 3 Candidates (2x-8x 80GB Multi-GPU)
    "qwen/qwen3-235b-a22b-2507": {
        "id": "L1",
        "tier": "Tier3_Large",
        "provider_order": ["GMICloud", "DeepInfra", "Parasail"],
        "quantizations": ["fp8"],
        "reasoning_mode": "none",
        "default_max_tokens": 2048,
        "hf_fp8": "Qwen/Qwen3-235B-A22B-Instruct-2507-FP8",
        "hf_int4": "Qwen/Qwen3-235B-A22B-GPTQ-Int4",
    },
    "deepseek/deepseek-v3.2": {
        "id": "L2",
        "tier": "Tier3_Large",
        "provider_order": ["AtlasCloud", "SiliconFlow", "Baidu"],
        "quantizations": ["fp8"],
        "reasoning_mode": "hybrid",
        "default_max_tokens": 2048,
        "hf_fp8": "deepseek-ai/DeepSeek-V3.2",
        "hf_int4": "deepseek-ai/DeepSeek-V3.2",
    },
    # Dedicated Stage 2 Policy Verifier (Config D)
    "openai/gpt-oss-safeguard-20b": {
        "id": "V1",
        "tier": "Stage2_Verifier",
        "provider_order": ["Groq"],
        "quantizations": None,  # Groq reports 'unknown' on OpenRouter
        "reasoning_mode": "mandatory_low",
        "default_max_tokens": 4096,
        "groq_model": "openai/gpt-oss-safeguard-20b",
        "hf_fp8": "openai/gpt-oss-safeguard-20b",
        "hf_int4": "openai/gpt-oss-safeguard-20b",
    },
    # Additional Groq Free-Tier Open-Weight Candidates
    "openai/gpt-oss-20b": {
        "id": "S0_Groq",
        "tier": "Tier1_Small",
        "provider_order": ["Groq"],
        "quantizations": None,
        "reasoning_mode": "mandatory_low",
        "default_max_tokens": 4096,
        "groq_model": "openai/gpt-oss-20b",
        "hf_fp8": "openai/gpt-oss-20b",
        "hf_int4": "openai/gpt-oss-20b",
    },
    "qwen/qwen3.8-27b": {
        "id": "S5_Groq",
        "tier": "Tier1_Small",
        "provider_order": ["Groq"],
        "quantizations": None,
        "reasoning_mode": "hybrid",
        "default_max_tokens": 2048,
        "groq_model": "qwen/qwen3.8-27b",
        "hf_fp8": "Qwen/Qwen3.8-27B",
        "hf_int4": "Qwen/Qwen3.8-27B",
    },
}

# Strict JSON Schemas for Guided Decoding (Section 4.2 & Section 5.4)
STAGE1_DETECTION_JSON_SCHEMA: Dict[str, Any] = {
    "name": "stage1_detection_output",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "category": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["text", "category", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["candidates"],
        "additionalProperties": False,
    },
}

STAGE2_ASSESSMENT_JSON_SCHEMA: Dict[str, Any] = {
    "name": "stage2_assessment_output",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "assessments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_id": {"type": "integer"},
                        "verdict": {"type": "string", "enum": ["PRIVATE", "PUBLIC"]},
                        "confidence": {"type": "number"},
                    },
                    "required": ["candidate_id", "verdict", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["assessments"],
        "additionalProperties": False,
    },
}

SINGLE_PASS_JSON_SCHEMA: Dict[str, Any] = {
    "name": "single_pass_privacy_output",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "baseline_assessments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "baseline_id": {"type": "integer"},
                        "verdict": {"type": "string", "enum": ["PRIVATE", "PUBLIC"]},
                        "confidence": {"type": "number"},
                    },
                    "required": ["baseline_id", "verdict", "confidence"],
                    "additionalProperties": False,
                },
            },
            "new_private_spans": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "occurrence_index": {"type": "integer"},
                        "category": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["text", "occurrence_index", "category", "confidence"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["baseline_assessments", "new_private_spans"],
        "additionalProperties": False,
    },
}


class UnifiedModelClient:
    def __init__(
        self,
        budget_ceiling_usd: float = 50.0,
        timeout_s: float = 180.0,
        ollama_url: str = "http://localhost:11434",
        vllm_url: Optional[str] = None,
        allow_local_fallback: bool = False,
        enable_groq_fallback: bool = True,
        enable_thinking: bool = False,
    ):
        self.budget_ceiling_usd = budget_ceiling_usd
        self.timeout_s = timeout_s
        self.ollama_url = ollama_url
        self.vllm_url = vllm_url
        self.allow_local_fallback = allow_local_fallback
        self.enable_groq_fallback = enable_groq_fallback
        self.enable_thinking = enable_thinking
        self.total_cost_usd = 0.0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.call_history: List[Dict[str, Any]] = []
        self._env_cache: Dict[str, str] = {}

    def _get_env_key(self, key_name: str) -> Optional[str]:
        if key_name in self._env_cache:
            return self._env_cache[key_name]
        val = os.environ.get(key_name)
        if val:
            self._env_cache[key_name] = val
            return val
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        for p in [
            repo_root / ".env",
            Path("virtual-gold-capstone/.env"),
            Path(".env"),
            Path("../virtual-gold-capstone/.env"),
        ]:
            if p.exists():
                for line in p.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == key_name:
                            cleaned = v.strip().strip('"').strip("'")
                            self._env_cache[key_name] = cleaned
                            return cleaned
        return None

    def _get_api_key(self) -> str:
        key = self._get_env_key("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("OPENROUTER_API_KEY not found in environment or .env file.")
        return key

    def _get_groq_api_key(self) -> str:
        key = self._get_env_key("GROQ_API_KEY")
        if not key:
            raise ValueError("GROQ_API_KEY not found in environment or .env file.")
        return key

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        retries: int = 3,
        json_schema: Optional[Dict[str, Any]] = None,
        enable_thinking: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Dispatches to:
        - Local Ollama if model starts with 'ollama/' or 'local_' or is in ['qwen3.5:9b', 'llama3.1:8b']
        - Direct Groq LPU API if model starts with 'groq/'
        - Self-hosted vLLM if model starts with 'vllm/' or self.vllm_url is set
        - OpenRouter with pinned provider/quantization routing otherwise (falling back to direct Groq
          ONLY for identical model weights hosted on Groq when OpenRouter credits are 0 / HTTP 402).
        Never silently substitutes a different model (Fix #1).
        """
        use_thinking = self.enable_thinking if enable_thinking is None else enable_thinking

        if model.startswith("ollama/") or model.startswith("local_") or model in ["qwen3.5:9b", "llama3.1:8b"]:
            eff_max = max_tokens or 2048
            return self._call_ollama(model, messages, temperature, eff_max, retries)

        if model.startswith("groq/"):
            groq_model = model.split("/", 1)[1]
            spec = VPC_MODEL_REGISTRY.get(groq_model, {})
            eff_max = max_tokens or spec.get("default_max_tokens", 2048)
            return self._call_groq(
                model_requested=model,
                groq_model=groq_model,
                messages=messages,
                temperature=temperature,
                max_tokens=eff_max,
                retries=retries,
                json_schema=json_schema,
                enable_thinking=use_thinking,
            )

        spec = VPC_MODEL_REGISTRY.get(model, {})
        eff_max = max_tokens or (4096 if use_thinking else spec.get("default_max_tokens", 2048))

        res = self._call_openrouter(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=eff_max,
            retries=retries,
            json_schema=json_schema,
            enable_thinking=use_thinking,
        )

        # If OpenRouter returns HTTP 402 (wallet has $0 credits) and the EXACT SAME open-weight
        # model is hosted on Groq and GROQ_API_KEY is available, route to Groq for the identical checkpoint.
        if (
            not res.get("success")
            and self.enable_groq_fallback
            and "402" in str(res.get("error", ""))
            and spec.get("groq_model")
            and self._get_env_key("GROQ_API_KEY")
        ):
            groq_m = spec["groq_model"]
            print(f"[ModelClient] OpenRouter returned HTTP 402 for {model}; routing identical checkpoint via direct Groq API ({groq_m})...")
            return self._call_groq(
                model_requested=model,
                groq_model=groq_m,
                messages=messages,
                temperature=temperature,
                max_tokens=eff_max,
                retries=retries,
                json_schema=json_schema,
                enable_thinking=use_thinking,
            )

        # Fix #1: Never silently fall back to local llama3.1:8b unless allow_local_fallback=True
        if not res.get("success") and self.allow_local_fallback:
            print(f"[ModelClient] Explicit local fallback enabled; falling back from {model} to llama3.1:8b...")
            fallback_res = self._call_ollama("llama3.1:8b", messages, temperature, eff_max, retries)
            fallback_res["fallback_from_model"] = model
            fallback_res["provider"] = "local_ollama_fallback"
            return fallback_res

        return res

    def _call_ollama(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        retries: int,
    ) -> Dict[str, Any]:
        ollama_model_name = model
        if model.startswith("ollama/"):
            ollama_model_name = model.split("/", 1)[1]
        elif model.startswith("local_"):
            ollama_model_name = model[6:]

        payload = {
            "model": ollama_model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "think": False,
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.ollama_url}/api/chat",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
        )

        last_error = None
        attempt = 0
        latency = 0.0
        while attempt < retries:
            attempt += 1
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    raw_text = resp.read().decode("utf-8")
                    latency = time.perf_counter() - t0
                    data = json.loads(raw_text)

                choice = data.get("message", {}).get("content", "")
                p_tokens = int(data.get("prompt_eval_count", 0))
                c_tokens = int(data.get("eval_count", 0))
                load_duration_ns = data.get("load_duration", 0)
                eval_duration_ns = data.get("eval_duration", 0)
                done_reason = data.get("done_reason", "stop")

                self.total_prompt_tokens += p_tokens
                self.total_completion_tokens += c_tokens

                record = {
                    "model_requested": model,
                    "model_returned": ollama_model_name,
                    "provider": "local_ollama_m4",
                    "quantization": "q4_k_m",
                    "finish_reason": done_reason,
                    "reasoning_tokens": 0,
                    "visible_completion_tokens": c_tokens,
                    "latency_s": latency,
                    "load_duration_s": load_duration_ns / 1e9,
                    "eval_duration_s": eval_duration_ns / 1e9,
                    "prompt_tokens": p_tokens,
                    "completion_tokens": c_tokens,
                    "cost_usd": 0.0,
                    "attempts": attempt,
                    "success": (done_reason != "length"),
                    "failure_type": "operational" if done_reason == "length" else None,
                    "error": "finish_reason=length" if done_reason == "length" else None,
                    "content": choice,
                    "raw_response": data,
                }
                self.call_history.append(record)
                return record

            except Exception as e:
                latency = time.perf_counter() - t0
                last_error = str(e)
                time.sleep(1.0 * (2 ** (attempt - 1)))

        record = {
            "model_requested": model,
            "model_returned": None,
            "provider": "local_ollama_m4",
            "quantization": None,
            "finish_reason": None,
            "reasoning_tokens": 0,
            "visible_completion_tokens": 0,
            "latency_s": latency,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
            "attempts": attempt,
            "success": False,
            "failure_type": "operational" if "timed out" in str(last_error).lower() else "infrastructure",
            "error": last_error,
            "content": None,
            "raw_response": None,
        }
        self.call_history.append(record)
        return record

    def _call_groq(
        self,
        model_requested: str,
        groq_model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        retries: int,
        json_schema: Optional[Dict[str, Any]] = None,
        enable_thinking: bool = False,
    ) -> Dict[str, Any]:
        api_key = self._get_groq_api_key()
        spec = VPC_MODEL_REGISTRY.get(groq_model, {})
        reasoning_mode = spec.get("reasoning_mode", "none")

        # Adjust max_tokens to respect Groq Free-Tier TPM limits (e.g., 2000 TPM on safeguard-20b)
        eff_max_tokens = max_tokens
        if groq_model == "openai/gpt-oss-safeguard-20b":
            eff_max_tokens = min(max_tokens, 900)
        elif groq_model in ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"):
            eff_max_tokens = min(max_tokens, 2048)

        payload: Dict[str, Any] = {
            "model": groq_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": eff_max_tokens,
            "seed": 42,
        }

        if reasoning_mode == "mandatory_low":
            payload["reasoning_effort"] = "low"
        elif reasoning_mode == "hybrid":
            payload["reasoning_effort"] = "low" if enable_thinking else "none"

        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": json_schema,
            }

        last_error = None
        attempt = 0
        latency = 0.0
        max_attempts = max(retries, 5)  # Allow rate-limit pacing retries on Groq Free Tier
        while attempt < max_attempts:
            attempt += 1
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=data_bytes,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "VirtualGold-Benchmark/2.0",
                },
            )
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    raw_text = resp.read().decode("utf-8")
                    latency = time.perf_counter() - t0
                    resp_headers = dict(resp.info())
                    data = json.loads(raw_text)

                # Proactive Groq Free-Tier token rate-limit pacing
                rem_tokens = resp_headers.get("x-ratelimit-remaining-tokens")
                if rem_tokens is not None and int(rem_tokens) < 1200:
                    time.sleep(4.0)

                choice_obj = data.get("choices", [{}])[0]
                choice = choice_obj.get("message", {}).get("content", "")
                finish_reason = choice_obj.get("finish_reason", "stop")
                usage = data.get("usage", {})
                p_tokens = int(usage.get("prompt_tokens", 0))
                c_tokens = int(usage.get("completion_tokens", 0))
                comp_details = usage.get("completion_tokens_details") or {}
                r_tokens = int(comp_details.get("reasoning_tokens", 0))
                vis_tokens = max(0, c_tokens - r_tokens)
                returned_model = data.get("model", groq_model)

                self.total_prompt_tokens += p_tokens
                self.total_completion_tokens += c_tokens

                is_len_fail = (finish_reason == "length" and not choice)
                record = {
                    "model_requested": model_requested,
                    "model_returned": returned_model,
                    "provider": "Groq",
                    "quantization": "mxfp4" if "gpt-oss" in groq_model else "fp8",
                    "finish_reason": finish_reason,
                    "reasoning_tokens": r_tokens,
                    "visible_completion_tokens": vis_tokens,
                    "latency_s": latency,
                    "prompt_tokens": p_tokens,
                    "completion_tokens": c_tokens,
                    "cost_usd": 0.0,
                    "attempts": attempt,
                    "success": not is_len_fail,
                    "failure_type": "operational" if is_len_fail else None,
                    "error": "finish_reason=length" if is_len_fail else None,
                    "content": choice,
                    "raw_response": data,
                }
                self.call_history.append(record)
                return record

            except urllib.error.HTTPError as e:
                latency = time.perf_counter() - t0
                error_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
                last_error = f"HTTP {e.code}: {error_body}"
                if e.code == 400 and "json_schema" in error_body and "response_format" in payload:
                    # Fallback to json_object if strict json_schema rejected for a specific model
                    payload["response_format"] = {"type": "json_object"}
                    attempt -= 1
                    continue
                if e.code == 429:
                    # Parse wait time from Groq error message (e.g., "Please try again in 14.2s")
                    m_wait = re.search(r"try again in ([0-9.]+)s", error_body)
                    wait_s = float(m_wait.group(1)) + 1.5 if m_wait else (6.0 * attempt)
                    print(f"[Groq Rate Limit] Sleeping {wait_s:.1f}s before retry {attempt}/{max_attempts}...")
                    time.sleep(min(wait_s, 65.0))
                    continue
                if e.code in [500, 502, 503, 504]:
                    time.sleep(2.0 * (2 ** (attempt - 1)))
                    continue
                break
            except Exception as e:
                latency = time.perf_counter() - t0
                last_error = str(e)
                time.sleep(2.0 * (2 ** (attempt - 1)))

        record = {
            "model_requested": model_requested,
            "model_returned": None,
            "provider": "Groq",
            "quantization": None,
            "finish_reason": None,
            "reasoning_tokens": 0,
            "visible_completion_tokens": 0,
            "latency_s": latency,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
            "attempts": attempt,
            "success": False,
            "failure_type": "operational" if "timed out" in str(last_error).lower() else "infrastructure",
            "error": last_error,
            "content": None,
            "raw_response": None,
        }
        self.call_history.append(record)
        return record

    def _call_openrouter(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        retries: int,
        json_schema: Optional[Dict[str, Any]] = None,
        enable_thinking: bool = False,
    ) -> Dict[str, Any]:
        if self.total_cost_usd >= self.budget_ceiling_usd:
            raise BudgetExceededError(
                f"Budget ceiling reached: ${self.total_cost_usd:.4f} >= ${self.budget_ceiling_usd:.2f}"
            )

        api_key = self._get_api_key()
        spec = VPC_MODEL_REGISTRY.get(model, {})
        is_free_slug = model.endswith(":free") or model == "openrouter/free"

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "seed": 42,
        }

        # Apply Provider & Quantization Pinning from VPC_MODEL_REGISTRY (Section 4.1)
        if spec and not is_free_slug:
            provider_cfg: Dict[str, Any] = {
                "order": spec["provider_order"],
                "allow_fallbacks": False,
                "require_parameters": True,
            }
            if spec.get("quantizations"):
                provider_cfg["quantizations"] = spec["quantizations"]
            payload["provider"] = provider_cfg

        # Apply Per-Model Reasoning Controls (Section 4.2)
        reasoning_mode = spec.get("reasoning_mode", "none")
        if reasoning_mode == "mandatory_low":
            payload["reasoning"] = {"effort": "low"}
        elif reasoning_mode == "hybrid":
            if enable_thinking:
                payload["reasoning"] = {"enabled": True, "effort": "low"}
            else:
                payload["reasoning"] = {"enabled": False}

        # Apply Strict Guided JSON Schema (Section 4.2)
        if json_schema is not None and not is_free_slug:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": json_schema,
            }

        last_error = None
        attempt = 0
        latency = 0.0
        while attempt < retries:
            attempt += 1
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=data_bytes,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://cmu.edu/capstone",
                    "X-Title": "VirtualGold-VPC-Model-Benchmark",
                },
            )
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    raw_text = resp.read().decode("utf-8")
                    latency = time.perf_counter() - t0
                    data = json.loads(raw_text)

                if "error" in data and not data.get("choices"):
                    err_obj = data["error"]
                    err_code = err_obj.get("code", 500)
                    last_error = f"HTTP {err_code}: {json.dumps(err_obj)}"
                    if err_code in [429, 500, 502, 503, 504]:
                        time.sleep(2.0 * (2 ** (attempt - 1)))
                        continue
                    break

                choice_obj = (data.get("choices") or [{}])[0]
                choice = choice_obj.get("message", {}).get("content", "")
                finish_reason = choice_obj.get("finish_reason") or choice_obj.get("native_finish_reason") or "stop"
                usage = data.get("usage", {})
                cost = float(usage.get("cost", 0.0))
                p_tokens = int(usage.get("prompt_tokens", 0))
                c_tokens = int(usage.get("completion_tokens", 0))
                comp_details = usage.get("completion_tokens_details") or {}
                r_tokens = int(comp_details.get("reasoning_tokens", 0))
                vis_tokens = max(0, c_tokens - r_tokens)
                provider = data.get("provider", "unknown")
                returned_model = data.get("model", model)
                quant = (spec.get("quantizations") or ["unknown"])[0] if spec else "unknown"

                self.total_cost_usd += cost
                self.total_prompt_tokens += p_tokens
                self.total_completion_tokens += c_tokens

                is_len_fail = (finish_reason == "length" and not choice)
                record = {
                    "model_requested": model,
                    "model_returned": returned_model,
                    "provider": provider,
                    "quantization": quant,
                    "finish_reason": finish_reason,
                    "reasoning_tokens": r_tokens,
                    "visible_completion_tokens": vis_tokens,
                    "latency_s": latency,
                    "prompt_tokens": p_tokens,
                    "completion_tokens": c_tokens,
                    "cost_usd": cost,
                    "attempts": attempt,
                    "success": not is_len_fail,
                    "failure_type": "operational" if is_len_fail else None,
                    "error": "finish_reason=length" if is_len_fail else None,
                    "content": choice,
                    "raw_response": data,
                }
                self.call_history.append(record)
                return record

            except urllib.error.HTTPError as e:
                latency = time.perf_counter() - t0
                error_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
                last_error = f"HTTP {e.code}: {error_body}"
                if e.code in [429, 500, 502, 503, 504]:
                    time.sleep(2.0 * (2 ** (attempt - 1)))
                    continue
                else:
                    break
            except Exception as e:
                latency = time.perf_counter() - t0
                last_error = str(e)
                time.sleep(2.0 * (2 ** (attempt - 1)))

        record = {
            "model_requested": model,
            "model_returned": None,
            "provider": None,
            "quantization": None,
            "finish_reason": None,
            "reasoning_tokens": 0,
            "visible_completion_tokens": 0,
            "latency_s": latency,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost_usd": 0.0,
            "attempts": attempt,
            "success": False,
            "failure_type": "operational" if "timed out" in str(last_error).lower() else "infrastructure",
            "error": last_error,
            "content": None,
            "raw_response": None,
        }
        self.call_history.append(record)
        return record
