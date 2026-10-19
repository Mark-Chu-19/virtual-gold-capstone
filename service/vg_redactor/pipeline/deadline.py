from __future__ import annotations

import time
from typing import Callable


class Deadline:
    """End-to-end budget for one request (`timeout_ms`)."""

    def __init__(self, total_ms: int, clock: Callable[[], float] = time.monotonic):
        self._clock, self.total_ms = clock, total_ms
        self._end = clock() + total_ms / 1000

    def remaining_ms(self) -> int:
        return int((self._end - self._clock()) * 1000)

    def elapsed_ms(self) -> int:
        return self.total_ms - self.remaining_ms()

    def expired(self) -> bool:
        return self.remaining_ms() <= 0

    def model_budget_ms(self, call_cap_ms: int, reserve_ms: int) -> int:
        """Time one model call may take, keeping `reserve_ms` free for the degraded path."""
        return min(call_cap_ms, self.remaining_ms() - reserve_ms)
