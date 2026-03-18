"""Binary direction target for 5m/15m Up/Down prediction.

Mirrors Polymarket resolution exactly:
  y = 1 if close[t+1] >= open[t+1], else 0
  "Resolve to 'Up' if price at END of window >= price at BEGINNING of same window."

CRITICAL: The target compares close and open of the SAME FUTURE bar,
NOT close of future bar vs open of current bar. The latter leaks
information from the current bar (which features can see).
"""

from __future__ import annotations

import polars as pl


class BinaryDirectionTarget:
    """Target: 1 if the NEXT bar went up (close >= open), 0 otherwise.

    This matches Polymarket 5m/15m market resolution:
    "Price at end of window >= price at beginning of THAT window."

    Args:
        horizon_bars: How many bars ahead to predict. For 5m markets
                      on 5m bars, horizon=1. For 1h markets on 5m bars,
                      horizon=12.
    """

    def __init__(self, horizon_bars: int = 1) -> None:
        self.horizon_bars = horizon_bars

    def compute(self, bars: pl.DataFrame) -> pl.Series:
        """Compute binary target from OHLCV data.

        Target: close[t+h] >= open[t+h]  (did the future bar itself go up?)
        NOT: close[t+h] >= open[t]  (which leaks current bar info)

        The last `horizon_bars` rows will be null (no future data).
        """
        future_close = bars["close"].shift(-self.horizon_bars)
        future_open = bars["open"].shift(-self.horizon_bars)
        return (future_close >= future_open).cast(pl.Int8).alias("target")

    def compute_with_meta(self, bars: pl.DataFrame) -> pl.DataFrame:
        """Compute target and add metadata columns for analysis."""
        target = self.compute(bars)
        future_close = bars["close"].shift(-self.horizon_bars)
        future_open = bars["open"].shift(-self.horizon_bars)
        future_return = (future_close - future_open) / future_open

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
