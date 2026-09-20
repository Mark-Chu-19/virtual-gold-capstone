"""Cloud model interface and stub.

Design doc §4.3: the cloud is called once per query, unconditionally, and
the answer is cached so cloud-only and every hybrid variant reuse it.
Which provider (todo/TODO.md A6) and the redaction pipeline are still
open — this stub lets the sampling core be built and tested without
deciding either.
"""

from __future__ import annotations

from typing import Protocol

from harness.types import CloudResponse, Query


class CloudModel(Protocol):
    def generate(self, query: Query) -> CloudResponse:
        """Return the cloud model's answer and token usage for `query`."""
        ...


class UnconfiguredCloudModel:
    """Default `CloudModel`: raises on use, so callers must pass a real (or
    fake, in tests) cloud model rather than silently getting an empty answer."""

    def generate(self, query: Query) -> CloudResponse:
        raise NotImplementedError(
            "No cloud model configured — pass a CloudModel implementation "
            "to run_query()/run_eval_set() instead of the default stub."
        )
