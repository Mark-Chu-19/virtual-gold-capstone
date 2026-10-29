"""Opaque business identifiers, independent of HTTP tracing and input content."""
from typing import Protocol

from ulid import ULID


class SessionIdGenerator(Protocol):
    def new_id(self) -> str: ...


class UlidSessionIdGenerator:
    def new_id(self) -> str:
        return "sid_" + str(ULID())
