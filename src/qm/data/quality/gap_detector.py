"""Detects missing bars (gaps) in OHLCV time series.

Gaps occur when exchange websockets disconnect, exchanges go down for
maintenance, or the bar builder misses a window. Detecting gaps is critical
because features computed over gaps produce garbage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import polars as pl

from qm.core.constants import TIMEFRAME_MINUTES
from qm.core.types import Asset, Timeframe

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Gap:
    """A detected gap in the bar time series."""

    asset: Asset
    timeframe: Timeframe
    expected_time: datetime
    gap_duration_minutes: int


def detect_gaps(
    bars: pl.DataFrame,
    asset: Asset,
    timeframe: Timeframe,
) -> list[Gap]:
    """Detect missing bars in an OHLCV DataFrame.

    Args:
        bars: DataFrame with a 'time' column, sorted ascending.
        asset: Asset these bars belong to.
        timeframe: Expected timeframe interval.

    Returns:
        List of Gap objects for each missing bar.
    """
    if bars.is_empty() or len(bars) < 2:
        return []

    interval_minutes = TIMEFRAME_MINUTES[timeframe]
    expected_delta = timedelta(minutes=interval_minutes)

    gaps: list[Gap] = []
    times = bars["time"].to_list()

    for i in range(1, len(times)):
        actual_delta = times[i] - times[i - 1]
        if actual_delta > expected_delta * 1.5:  # allow small timing jitter
            # Count how many bars are missing
            n_missing = int(actual_delta / expected_delta) - 1
            for j in range(1, n_missing + 1):
                expected_time = times[i - 1] + expected_delta * j
                gaps.append(
                    Gap(
                        asset=asset,
                        timeframe=timeframe,
                        expected_time=expected_time,
                        gap_duration_minutes=interval_minutes,
                    )
                )

    if gaps:
        logger.warning(
            f"Detected {len(gaps)} gaps",
            extra={"asset": asset.value, "timeframe": timeframe.value},
        )

    return gaps


def completeness_score(
    bars: pl.DataFrame,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> float:
    """Calculate data completeness as a fraction [0, 1].

    Returns the ratio of actual bars to expected bars in the given range.
    """
    interval_minutes = TIMEFRAME_MINUTES[timeframe]
    total_minutes = (end - start).total_seconds() / 60
    expected_bars = int(total_minutes / interval_minutes)

    if expected_bars <= 0:
        return 1.0

    actual_bars = len(bars)
    return min(actual_bars / expected_bars, 1.0)
