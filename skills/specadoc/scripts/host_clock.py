"""Tell a host sleep from a stalled role during a wait.

`time.monotonic()` stops while macOS sleeps and `time.time()` does not. In run 6.14 a
`--timeout 540` wait took 20 wall minutes and three reviewer runs looked stalled, while the
Mac was in idle sleep (`pmset -g log`: each wait returned at a DarkWake).
"""
from __future__ import annotations

import time as _time
from typing import Any

# Clock drift and scheduling stay far below this; a real sleep is minutes.
GAP = 5.0
NOTE_AFTER = 60.0


class HostClock:
    """Accumulate the wall time that passed while the monotonic clock stood still."""

    def __init__(self, clock: Any = _time) -> None:
        self._clock = clock
        self._wall = clock.time()
        self._mono = clock.monotonic()
        self.slept = 0.0
        self._naps: list[tuple[float, float]] = []  # (wall time the nap ended, its length)

    def tick(self) -> float:
        wall, mono = self._clock.time(), self._clock.monotonic()
        gap = (wall - self._wall) - (mono - self._mono)
        if gap > GAP:
            self.slept += gap
            self._naps.append((wall, gap))
        self._wall, self._mono = wall, mono
        return self.slept

    def slept_since(self, moment: float) -> float:
        """Sleep that ended after `moment` (a log write), capped at the time since it: only that sleep
        belongs to the role's present silence."""
        return sum(min(gap, end - moment) for end, gap in self._naps if end > moment)

    def note(self) -> str:
        if self.slept < NOTE_AFTER:
            return ""
        return f"; host slept {int(self.slept)} s (machine sleep, not a stalled role)"
