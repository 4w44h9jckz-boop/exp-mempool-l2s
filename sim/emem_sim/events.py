"""A deterministic discrete-event scheduler."""

from __future__ import annotations

import heapq
import itertools
from typing import Callable


class Scheduler:
    """Callbacks ordered by time, ties by the order they were scheduled."""

    def __init__(self) -> None:
        self.now = 0.0
        self._queue: list = []
        self._order = itertools.count()

    def at(self, time: float, callback: Callable[[], None]) -> None:
        if time < self.now:
            raise ValueError(f"cannot schedule in the past: {time} < {self.now}")
        heapq.heappush(self._queue, (time, next(self._order), callback))

    def after(self, delay: float, callback: Callable[[], None]) -> None:
        self.at(self.now + delay, callback)

    def every(self, interval: float, callback: Callable[[], None], start: float | None = None) -> None:
        """Call `callback` at `start` and every `interval` after it."""
        def tick():
            callback()
            self.after(interval, tick)
        self.at(self.now + interval if start is None else start, tick)

    def run(self, until: float) -> None:
        while self._queue and self._queue[0][0] <= until:
            time, _, callback = heapq.heappop(self._queue)
            self.now = time
            callback()
        self.now = until
