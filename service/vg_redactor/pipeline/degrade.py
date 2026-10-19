from __future__ import annotations

from dataclasses import dataclass

from ..contracts.types import DegradedReason, DegradedStage


@dataclass(frozen=True)
class Degraded:
    reason: DegradedReason
    stage: DegradedStage
