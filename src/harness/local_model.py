"""Local-model interface the harness generates samples through.

The real implementation is `harness.hf_local_model.HFTransformersModel`
(HF transformers, per todo/TODO.md A1: the harness needs per-token
logprobs and hidden states, which Ollama/llama.cpp/vLLM don't expose).
Tests supply a fake instead.
"""

from __future__ import annotations

from typing import Protocol

from harness.types import Query, Sample


class LocalModel(Protocol):
    def generate(self, query: Query, n: int, temperature: float) -> list[Sample]:
        """Return `n` samples for `query`."""
        ...
