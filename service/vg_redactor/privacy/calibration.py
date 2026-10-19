"""Score calibration (`calibrate`). Privacy Research.

Histogram binning fitted offline on held-out labelled emails, made monotonic with
pool-adjacent-violators, stored in a versioned YAML file (config/calibration.yaml).
"""
from __future__ import annotations

from bisect import bisect_right
from pathlib import Path
from typing import Callable

import yaml

DEFAULT_EDGES = (0.5, 0.7, 0.9, 1.0)  # upper bin edges; the last must be 1.0


def _bin(edges: list[float], score: float) -> int:
    return min(bisect_right(edges, score), len(edges) - 1)


def _pav(rates: list[float], weights: list[int]) -> list[float]:
    """Pool adjacent violators: the closest non-decreasing sequence (weighted)."""
    blocks = [[r, w, 1] for r, w in zip(rates, weights)]  # value, weight, bins merged
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0]:
            v1, w1, n1 = blocks[i]
            v2, w2, n2 = blocks.pop(i + 1)
            blocks[i] = [(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, n1 + n2]
            i = max(i - 1, 0)
        else:
            i += 1
    return [v for v, _, n in blocks for _ in range(n)]


def fit_table(raw_scores: list[float], is_private: list[bool],
              edges: tuple[float, ...] = DEFAULT_EDGES, version: str = "calibration-fit") -> dict:
    """Fit a calibration table. Empty bins are filled from their neighbours."""
    counts, positives = [0] * len(edges), [0] * len(edges)
    for s, y in zip(raw_scores, is_private):
        i = _bin(list(edges), s)
        counts[i] += 1
        positives[i] += int(y)
    seen = [i for i, c in enumerate(counts) if c]
    if not seen:
        raise ValueError("no labelled scores to fit")
    rates = [positives[i] / counts[i] if counts[i] else None for i in range(len(edges))]
    for i in range(len(edges)):  # fill empty bins with the nearest fitted one
        if rates[i] is None:
            rates[i] = rates[min(seen, key=lambda j: abs(j - i))]
    rates = _pav(rates, [max(c, 1) for c in counts])
    return {"version": version, "edges": list(edges), "rates": [round(r, 4) for r in rates]}


def make_calibrate(table: dict | None) -> Callable[[float], float]:
    """`table` None = identity (no labelled data yet)."""
    if table is None:
        return lambda raw: min(max(raw, 0.0), 1.0)
    edges, rates = list(table["edges"]), list(table["rates"])
    if any(b < a for a, b in zip(rates, rates[1:])):
        raise ValueError("calibration table is not monotonic")

    def calibrate(raw: float) -> float:
        return rates[_bin(edges, min(max(raw, 0.0), 1.0))]

    return calibrate


def load_table(path: str | Path) -> dict | None:
    """Returns None when the file says `identity: true` (the default until data is fitted)."""
    d = yaml.safe_load(Path(path).read_text(encoding="utf8"))
    return None if d.get("identity") else d
