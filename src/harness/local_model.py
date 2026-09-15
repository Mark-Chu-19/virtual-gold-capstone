"""Local-model interface the harness generates samples through.

feat/signal-* branches don't need this — they consume the `Sample` list
the core loop already produced. This module only exists so
`generate_shared_samples` has something typed to call, and so tests can
supply a fake implementation instead of a real Ollama/vLLM backend.
"""

from __future__ import annotations

from typing import Protocol

from harness.types import Query, Sample


class LocalModel(Protocol):
    def generate(self, query: Query, n: int, temperature: float) -> list[Sample]:
        """Return `n` samples for `query`. Implementations wrap the actual
        inference backend (Ollama, vLLM, ...); wiring one up is tracked in
        todo/TODO.md item 11, not part of this branch."""
        ...
