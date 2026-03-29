"""Aligns timestamps to Polymarket window boundaries.

Polymarket 5-minute markets resolve based on price at the START vs END of
each window. Windows are aligned to clock boundaries in ET timezone:
  5m:  XX:00, XX:05, XX:10, XX:15, ...
  15m: XX:00, XX:15, XX:30, XX:45
  1h:  XX:00

This module handles the alignment including DST transitions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

POLYMARKET_TZ = ZoneInfo("America/New_York")


class BarAligner:
    """Aligns timestamps to Polymarket-compatible window boundaries."""

    def get_window(
        self, ts: datetime, timeframe_minutes: int
    ) -> tuple[datetime, datetime]:
        """Get the (start, end) of the window that contains `ts`.

        Both start and end are timezone-aware datetimes in ET.

        Args:
            ts: The timestamp to align (must be tz-aware).
            timeframe_minutes: Window size in minutes (5, 15, or 60).

        Returns:
            (window_start, window_end) as tz-aware datetimes.
        """
        et_time = ts.astimezone(POLYMARKET_TZ)

        if timeframe_minutes >= 60:
            # Hourly: align to the hour
            hours = timeframe_minutes // 60
            aligned_hour = (et_time.hour // hours) * hours
            window_start = et_time.replace(
                hour=aligned_hour, minute=0, second=0, microsecond=0
            )
        else:
            # Sub-hourly: align to minute boundary
            aligned_minute = (et_time.minute // timeframe_minutes) * timeframe_minutes
            window_start = et_time.replace(
                minute=aligned_minute, second=0, microsecond=0
            )

        window_end = window_start + timedelta(minutes=timeframe_minutes)
        return window_start, window_end

    def next_window_start(
        self, ts: datetime, timeframe_minutes: int
    ) -> datetime:
        """Get the start of the NEXT window after `ts`."""
        _, window_end = self.get_window(ts, timeframe_minutes)
        return window_end

    def time_until_window_end(
        self, ts: datetime, timeframe_minutes: int
    ) -> timedelta:
        """How much time remains in the current window."""
        _, window_end = self.get_window(ts, timeframe_minutes)
        return window_end - ts.astimezone(POLYMARKET_TZ)

    def is_window_boundary(
        self, ts: datetime, timeframe_minutes: int
    ) -> bool:
        """Check if `ts` falls exactly on a window boundary."""
        et_time = ts.astimezone(POLYMARKET_TZ)
        if et_time.second != 0 or et_time.microsecond != 0:
            return False
        if timeframe_minutes >= 60:
            return et_time.minute == 0 and et_time.hour % (timeframe_minutes // 60) == 0
        return et_time.minute % timeframe_minutes == 0
