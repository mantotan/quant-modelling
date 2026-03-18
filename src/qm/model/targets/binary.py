"""Binary direction target for 5m/15m Up/Down prediction.

Mirrors Polymarket resolution exactly:
  y = 1 if close[t + horizon] >= open[t], else 0
  "Resolve to 'Up' if price at end of window >= price at beginning."
"""

from __future__ import annotations

import polars as pl


class BinaryDirectionTarget:
    """Target: 1 if price went up over the horizon, 0 otherwise.

    Args:
        horizon_bars: Number of bars forward to look. For 5m markets
                      on 5m bars, horizon=1. For 1h markets on 5m bars,
                      horizon=12.
    """

    def __init__(self, horizon_bars: int = 1) -> None:
        self.horizon_bars = horizon_bars

    def compute(self, bars: pl.DataFrame) -> pl.Series:
        """Compute binary target from OHLCV data.

        Uses close[t+horizon] vs open[t] to match Polymarket resolution.
        The last `horizon_bars` rows will be null (no future data).
        """
        future_close = bars["close"].shift(-self.horizon_bars)
        current_open = bars["open"]
        return (future_close >= current_open).cast(pl.Int8).alias("target")

    def compute_with_meta(self, bars: pl.DataFrame) -> pl.DataFrame:
        """Compute target and add metadata columns for analysis."""
        target = self.compute(bars)
        future_close = bars["close"].shift(-self.horizon_bars)
        current_open = bars["open"]
        future_return = (future_close - current_open) / current_open

        return bars.with_columns(
            target,
            future_return.alias("target_return"),
        )


class ThresholdTouchTarget:
    """Target for monthly 'will BTC hit $X' markets.

    y = 1 if any high during the forward window >= threshold, else 0
    """

    def __init__(self, threshold: float, window_bars: int) -> None:
        self.threshold = threshold
        self.window_bars = window_bars

    def compute(self, bars: pl.DataFrame) -> pl.Series:
        """Compute threshold touch target.

        Looks forward `window_bars` and checks if any bar's high
        reaches the threshold. Last `window_bars` rows are null
        (incomplete forward window — no look-ahead contamination).
        """
        # Rolling max of high over the forward window
        # Reverse → rolling_max (becomes forward-looking) → reverse back
        forward_highs = bars["high"].reverse().rolling_max(
            window_size=self.window_bars, min_samples=self.window_bars
        ).reverse().shift(-1)

        return (forward_highs >= self.threshold).cast(pl.Int8).alias("target")
