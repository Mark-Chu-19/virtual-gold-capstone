"""Audit log: one JSON line per request. Category, score, tier, action; never raw text."""
from __future__ import annotations

import json
import threading
from pathlib import Path


class AuditLog:
    def __init__(self, path: str | None):
        self._path = Path(path) if path else None
        self._lock = threading.Lock()
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: dict) -> None:
        if not self._path:
            return
        line = json.dumps(event, separators=(",", ":"), default=str)
        with self._lock, self._path.open("a", encoding="utf8") as f:
            f.write(line + "\n")
