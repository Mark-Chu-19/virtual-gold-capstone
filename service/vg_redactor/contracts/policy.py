"""Tier table, taxonomy and thresholds (config/policy.yaml). Shared read-only data holder."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .types import Tier


@dataclass(frozen=True)
class Policy:
    version: str
    tiers: dict[str, dict]            # tier -> {"rule": str, "threshold": float|None}
    taxonomy: dict[str, Tier]         # entity type -> tier
    low_tier_combine_count: int = 3   # low-tier items redacted when this many appear together

    @classmethod
    def load(cls, path: str | Path) -> "Policy":
        d = yaml.safe_load(Path(path).read_text(encoding="utf8"))
        return cls(version=d["policy_version"], tiers=d["tiers"], taxonomy=d["taxonomy"],
                   low_tier_combine_count=d.get("low_tier_combine_count", 3))

    def tier_of(self, entity_type: str) -> Tier:
        # Unknown types are treated as the most severe tier (fail safe).
        return self.taxonomy.get(entity_type, "high")

    def threshold(self, tier: str, overrides: dict[str, float] | None = None) -> float | None:
        if overrides and tier in overrides:
            return overrides[tier]
        return self.tiers[tier].get("threshold")

    def high_types(self) -> set[str]:
        return {t for t, tier in self.taxonomy.items() if tier == "high"}
