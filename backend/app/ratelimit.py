"""Spend guard. Two limits, protecting against two different accidents.

Saaras is billed per second of audio, so cost is driven by request count. The
realistic runaway is not gradual overuse -- it is a voice unit stuck in a reboot
loop, or a firmware bug that retries on failure without a backoff, hammering
/command overnight while everyone is asleep.

    per-minute   a human physically cannot exceed this; a loop will instantly
    per-day      the backstop, in case something stays just under the minute
                 limit and grinds away for hours

In-memory and global, which is correct here for the same reason the power
debounce is: one machine, one household. Both counters reset on restart -- fine
for a guard whose job is bounding a runaway, not enforcing a quota.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class Verdict:
    allowed: bool
    reason: str = ""          # "minute" | "day"
    retry_after_s: int = 0


@dataclass
class Limiter:
    per_minute: int
    per_day: int

    _recent: deque[float] = field(default_factory=deque)
    _day_count: int = 0
    _day_started: float | None = None

    def check(self, now: float) -> Verdict:
        """Called before any paid API call. Records the request if allowed."""
        # --- daily window ---
        if self._day_started is None or now - self._day_started >= 86_400:
            if self._day_started is not None:
                log.info("daily counter reset after %d requests", self._day_count)
            self._day_started = now
            self._day_count = 0

        # --- rolling 60s window ---
        cutoff = now - 60
        while self._recent and self._recent[0] < cutoff:
            self._recent.popleft()

        if len(self._recent) >= self.per_minute:
            retry = max(1, int(60 - (now - self._recent[0])))
            log.warning(
                "RATE LIMIT: %d requests in 60s (cap %d). Suspect a client "
                "retry loop -- nothing was sent to Sarvam.",
                len(self._recent), self.per_minute,
            )
            return Verdict(False, "minute", retry)

        if self._day_count >= self.per_day:
            log.warning(
                "DAILY CAP: %d requests today (cap %d). Nothing sent to Sarvam.",
                self._day_count, self.per_day,
            )
            return Verdict(False, "day", 3600)

        self._recent.append(now)
        self._day_count += 1
        return Verdict(True)

    @property
    def stats(self) -> dict:
        return {"last_minute": len(self._recent), "today": self._day_count}
