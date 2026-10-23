"""Static context store: client term list and allow-list. Privacy Research.

Loaded once at startup from a client-supplied YAML file; never changes afterwards (a new list
means a new deployment and a new `version`).
"""
from __future__ import annotations

from pathlib import Path

import yaml


class FileContextStore:
    def __init__(self, version: str, term_list: set[str], allow_list: set[str],
                 high_types: set[str]):
        self.version = version
        self.term_list = frozenset(term_list)
        self.allow_list = frozenset(allow_list)
        self._high_types = frozenset(high_types)

    @classmethod
    def load(cls, path: str | Path, high_types: set[str]) -> "FileContextStore":
        d = yaml.safe_load(Path(path).read_text(encoding="utf8")) or {}
        return cls(d.get("version", "context-unversioned"), set(d.get("term_list") or []),
                   set(d.get("allow_list") or []), high_types)

    def is_allowed(self, entity_type: str, text: str) -> bool:
        """Exact match only. High-tier types are never allow-listed."""
        return entity_type not in self._high_types and text in self.allow_list
