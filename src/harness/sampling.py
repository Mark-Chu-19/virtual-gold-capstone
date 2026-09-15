"""The one shared cost: generate k samples per query, once.

Design doc section 4.1 — Config A, B, and C all derive from this same
batch so the harness pays for k generations once per query, not 3k.
"""

from __future__ import annotations

from harness.local_model import LocalModel
from harness.types import Query, Sample


def generate_shared_samples(
    local_model: LocalModel, query: Query, k: int, temperature: float
) -> list[Sample]:
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")
    samples = local_model.generate(query, n=k, temperature=temperature)
    if len(samples) != k:
        raise ValueError(
            f"local_model.generate returned {len(samples)} samples, expected {k}"
        )
    return samples
