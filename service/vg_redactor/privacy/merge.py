"""Union of candidate lists (`merge_candidates`). Privacy Research."""
from __future__ import annotations

from typing import Callable

from ..contracts.policy import Policy
from ..contracts.types import Candidate

# Stricter first. Unknown types count as High (Policy.tier_of fails safe).
TIER_RANK = {"high": 0, "medium": 1, "low": 2, "public": 3}


def make_merge(policy: Policy) -> Callable[..., list[Candidate]]:
    def rank(c: Candidate) -> int:
        return TIER_RANK[policy.tier_of(c.type)]

    def merge_candidates(*lists: list[Candidate]) -> list[Candidate]:
        """Overlapping spans in one field become one span covering both; `detectors` is the
        union; the type with the stricter tier wins; any `hint` is kept. Inputs are not mutated."""
        items = sorted((c for lst in lists for c in lst), key=lambda c: (c.field, c.start, -c.end))
        merged: list[Candidate] = []
        for c in items:
            last = merged[-1] if merged else None
            if last and last.field == c.field and c.start < last.end:
                last.end = max(last.end, c.end)
                last.detectors = last.detectors | c.detectors
                last.hint = last.hint or c.hint
                if rank(c) < rank(last):
                    last.type = c.type
            else:
                merged.append(c.model_copy(deep=True))
        return merged

    return merge_candidates
