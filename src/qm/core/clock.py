"""Unified clock: wall-clock for live, simulated for backtest."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

POLYMARKET_TZ = ZoneInfo("America/New_York")
UTC = timezone.utc


class WallClock:
    """Real wall clock for live trading."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def now_et(self) -> datetime:
        return datetime.now(POLYMARKET_TZ)


class SimulatedClock:
    """Simulated clock for backtesting. Steps through timestamps."""

    def __init__(
        self,
        start: datetime,
        end: datetime,
        step: timedelta = timedelta(minutes=5),
    ) -> None:
        self._current = start
        self._end = end
        self._step = step

    def now(self) -> datetime:
        return self._current

    def advance(self) -> bool:
        """Advance clock by one step. Returns False if past end."""
        self._current += self._step
        return self._current <= self._end

    def __iter__(self) -> SimulatedClock:
        return self

    def __next__(self) -> datetime:
        if self._current > self._end:
            raise StopIteration
        ts = self._current
        self._current += self._step
        return ts


def align_to_window(ts: datetime, timeframe_minutes: int) -> datetime:
    """Snap a timestamp to the start of its Polymarket window boundary.

    Polymarket windows are aligned to clock boundaries in ET timezone.
    E.g., 5-minute windows: XX:00, XX:05, XX:10, etc.
    """
    et_time = ts.astimezone(POLYMARKET_TZ)
    aligned_minute = (et_time.minute // timeframe_minutes) * timeframe_minutes
    return et_time.replace(minute=aligned_minute, second=0, microsecond=0)
