"""Escalation rule shared by all signal variants (design doc §4.3:
`escalate = confidence < threshold`). Threshold calibration is a separate
branch (feat/harness-threshold-calibration)."""

from __future__ import annotations


def should_escalate(confidence: float, threshold: float) -> bool:
    return confidence < threshold
