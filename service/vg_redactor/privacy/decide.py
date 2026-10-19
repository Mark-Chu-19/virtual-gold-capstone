"""Decision step (`decide`): tier x threshold on the calibrated score. Privacy Research.

"The model proposes, code decides." Pure function: no I/O, no logging of values.
"""
from __future__ import annotations

from collections import defaultdict

from ..contracts.components import ContextStore
from ..contracts.policy import Policy
from ..contracts.types import Decision, Overrides, ScoredCandidate

FORCED_REDACT_HINTS = {"term_list_match", "deny_list"}


def decide(scored: list[ScoredCandidate], policy: Policy, overrides: Overrides,
           ctx: ContextStore) -> list[Decision]:
    # Low-tier items are redacted when enough DISTINCT low-tier types appear in the same field
    # (city + employer + age points to one person; three dates do not). Provisional rule.
    low_types: dict[str, set[str]] = defaultdict(set)
    for s in scored:
        if s.candidate.type in policy.taxonomy and policy.tier_of(s.candidate.type) == "low":
            low_types[s.candidate.field].add(s.candidate.type)

    out: list[Decision] = []
    for s in scored:
        c, score = s.candidate, s.calibrated
        tier = policy.tier_of(c.type)

        def d(action: str, reason: str) -> Decision:
            return Decision(candidate=c, tier=tier, action=action, confidence=score, reason=reason)

        if c.hint in FORCED_REDACT_HINTS:
            out.append(d("redact", c.hint))  # a client-listed term is always redacted
        elif c.type not in policy.taxonomy:
            out.append(d("redact", "cannot_classify_default_redact"))  # a type the taxonomy does not list
        elif score is None:
            out.append(d("redact", "cannot_classify_default_redact"))
        elif c.hint == "allow_list":
            out.append(d("retain", "allow_list"))  # the service never marks High-tier items
        elif tier == "low":
            combined = len(low_types[c.field]) >= policy.low_tier_combine_count
            out.append(d("redact", "combined_low_tier") if combined
                       else d("retain", "isolated_low_tier"))
        else:  # high, medium, public: score = P(private) against the tier threshold
            thr = policy.threshold(tier, overrides.thresholds if tier == "medium" else None)
            out.append(d("redact", "meets_threshold") if score >= thr
                       else d("retain", "below_threshold"))
    return out
