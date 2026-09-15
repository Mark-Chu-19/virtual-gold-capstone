"""Escalation rule shared by all three configurations.

Design doc section 4.3: `escalate_X = conf_X < threshold_X`. Threshold
calibration itself (feat/harness-threshold-calibration) is a separate,
later branch — this just applies whatever threshold a ConfigSpec carries.
"""

from __future__ import annotations


def should_escalate(confidence: float, threshold: float) -> bool:
    return confidence < threshold
