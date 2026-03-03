from __future__ import annotations

import time
from collections import deque
from datetime import date


class RateLimitExceeded(RuntimeError):
    pass


class CompositeRateLimiter:
    """Enforces max calls per minute and per day."""

    def __init__(self, calls_per_minute: int, calls_per_day: int) -> None:
        self.calls_per_minute = calls_per_minute
        self.calls_per_day = calls_per_day
        self.minute_window: deque[float] = deque()
        self.current_day = date.today().isoformat()
        self.day_count = 0

    def acquire(self) -> None:
        now = time.time()
        self._reset_if_new_day()
        self._evict_old(now)

        if self.day_count >= self.calls_per_day:
            raise RateLimitExceeded("Daily call quota reached")

        if len(self.minute_window) >= self.calls_per_minute:
            sleep_seconds = 60 - (now - self.minute_window[0]) + 0.01
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            now = time.time()
            self._evict_old(now)

        self.minute_window.append(now)
        self.day_count += 1

    def _evict_old(self, now: float) -> None:
        while self.minute_window and now - self.minute_window[0] >= 60:
            self.minute_window.popleft()

    def _reset_if_new_day(self) -> None:
        today = date.today().isoformat()
        if today != self.current_day:
            self.current_day = today
            self.day_count = 0
            self.minute_window.clear()
