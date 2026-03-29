"""Detects and flags price outliers / spikes in OHLCV data.

Catches exchange-specific glitches where a single exchange reports a
wildly different price that doesn't appear on other exchanges.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Outlier:
    """A detected price outlier."""

    index: int
    time: object
    field: str  # 'high', 'low', 'close', etc.
    value: float
    z_score: float


def detect_price_outliers(
    bars: pl.DataFrame,
    z_threshold: float = 5.0,
    window: int = 50,
) -> list[Outlier]:
    """Detect price spikes using rolling z-score.

    For each price field (open, high, low, close), compute a rolling mean
    and std, then flag values beyond z_threshold standard deviations.

    Args:
        bars: OHLCV DataFrame sorted by time.
        z_threshold: Number of std devs to flag as outlier (default 5).
        window: Rolling window size in bars.

    Returns:
        List of detected outliers.
    """
    if len(bars) < window:
        return []

    outliers: list[Outlier] = []

    for field in ("open", "high", "low", "close"):
        col = bars[field]
        rolling_mean = col.rolling_mean(window_size=window, min_periods=window // 2)
        rolling_std = col.rolling_std(window_size=window, min_periods=window // 2)

        # Avoid division by zero
        safe_std = rolling_std.fill_null(1.0).clip(lower_bound=1e-10)
        z_scores = (col - rolling_mean) / safe_std

        for i in range(len(z_scores)):
            z = z_scores[i]
            if z is not None and abs(z) > z_threshold:
                outliers.append(
                    Outlier(
                        index=i,
                        time=bars["time"][i],
                        field=field,
                        value=col[i],
                        z_score=float(z),
                    )
                )

    if outliers:
        logger.warning(f"Detected {len(outliers)} price outliers (z > {z_threshold})")

    return outliers


def filter_outliers(
    bars: pl.DataFrame,
    z_threshold: float = 5.0,
    window: int = 50,
) -> pl.DataFrame:
    """Remove rows containing price outliers. Returns filtered DataFrame."""
    outliers = detect_price_outliers(bars, z_threshold, window)
    if not outliers:
        return bars

    outlier_indices = {o.index for o in outliers}
    mask = [i not in outlier_indices for i in range(len(bars))]
    return bars.filter(pl.Series(mask))
