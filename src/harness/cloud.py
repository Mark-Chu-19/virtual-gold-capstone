"""Cloud-escalation interface and stub.

Design doc section 4.3: at most one cloud call per query, shared across
whichever configs escalate. Which provider (todo/TODO.md item 6) and the
redaction/minimization pipeline (architecture-v0.2-en.md section 6) are
both still open — this stub exists so the sampling core can be built and
tested against something, without deciding either.
"""

from __future__ import annotations

from typing import Protocol

from harness.types import Query


class CloudModel(Protocol):
    def generate(self, query: Query) -> str:
        """Return the cloud model's answer for `query`."""
        ...


class UnconfiguredCloudModel:
    """Default `CloudModel`: raises if the harness actually tries to
    escalate. Forces callers to pass a real (or fake, in tests) cloud
    model explicitly rather than silently getting an empty answer."""

    def generate(self, query: Query) -> str:
        raise NotImplementedError(
            "No cloud model configured — pass a CloudModel implementation "
            "to run_query()/run_eval_set() instead of the default stub."
        )
