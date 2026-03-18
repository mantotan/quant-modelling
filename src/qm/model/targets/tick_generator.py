"""Training data generator from real aggTrades -- zero interpolation.

Builds intra-bar training samples from actual Binance trade data.
Every feature value comes from a real market observation, not an
interpolation between 1-minute bar closes.

For each parent bar (5m), loads all trades in that window and computes
exact partial bar state at each time_pct from real trade prices.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import numpy as np
import polars as pl

from qm.backtest.market_sim import MarketOddsSimulator
from qm.core.constants import TIMEFRAME_MINUTES
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.intrabar import (
    ALL_FEATURE_NAMES,
    CACHED_DEFAULTS,
    CACHED_FEATURE_NAMES,
)
from qm.model.targets.intrabar import IntraBarDataset

logger = logging.getLogger(__name__)

# Time points for sampling: same as honest 1m-based generator (capped at 0.80)
DEFAULT_TIME_PCTS: list[float] = [
    0.003, 0.01, 0.05, 0.10, 0.20, 0.40, 0.60, 0.80,
]


class RealTickDataGenerator:
    """Build training samples from actual aggTrades -- zero interpolation.

    At each time_pct, uses the real last-traded price, real cumulative
    volume, and real trade count. No deterministic path, no linear
    interpolation between bar closes.

    Processes one day at a time to control memory (~1-5M trades/day).
    """

    def __init__(
        self,
        timeframe: Timeframe = Timeframe.M5,
        seed: int = 42,
    ) -> None:
        self._minutes = TIMEFRAME_MINUTES[timeframe]
        self._total_seconds = float(self._minutes * 60)
        self._seed = seed

    def generate(
        self,
        bars_df: pl.DataFrame,
        trades_store: ParquetStore,
        history_features: pl.DataFrame,
        market_sim: MarketOddsSimulator | None = None,
        time_pcts: list[float] | None = None,
    ) -> IntraBarDataset:
        """Generate training data from parent bars + real trades.

        Args:
            bars_df: Parent timeframe bars (5m) with 'time' column.
            trades_store: ParquetStore containing aggTrades data.
            history_features: Sentinel pipeline features aligned with bars_df.
            market_sim: Market odds simulator (fallback until real Polymarket data).
            time_pcts: Elapsed fractions to sample.

        Returns:
            IntraBarDataset. Bars without trade data are dropped.
        """
        if time_pcts is None:
            time_pcts = DEFAULT_TIME_PCTS

        n_tp = len(time_pcts)

        if len(bars_df) == 0:
            return self._empty_dataset()

        # Get available trade dates
        asset = self._detect_asset(bars_df)
        if asset is None:
            logger.warning("Cannot detect asset from bars_df")
            return self._empty_dataset()

        trade_dates = set(trades_store.list_trade_dates(asset))
        if not trade_dates:
            logger.warning("No trade data found for %s", asset.value)
            return self._empty_dataset()

        # Filter bars to dates with trade data
        bars_df = bars_df.with_columns(
            pl.col("time").dt.date().cast(pl.Utf8).alias("_date_str")
        )
        bars_with_trades = bars_df.filter(
            pl.col("_date_str").is_in(list(trade_dates))
        )

        n_bars_total = len(bars_df)
        n_bars_valid = len(bars_with_trades)
        n_dropped = n_bars_total - n_bars_valid

        if n_bars_valid == 0:
            logger.warning("No bars have matching trade data")
            return self._empty_dataset()

        if n_dropped > 0:
            logger.info(
                "Using %d/%d bars with trade data (%.1f%% coverage)",
                n_bars_valid, n_bars_total, 100 * n_bars_valid / n_bars_total,
            )

        # Extract cached historical features
        # Filter history_features to match valid bars
        valid_mask = bars_df["_date_str"].is_in(list(trade_dates)).to_numpy()
        history_features = history_features[np.where(valid_mask)[0]]

        hist_arrays: dict[str, np.ndarray] = {}
        for name in CACHED_FEATURE_NAMES:
            if name in history_features.columns:
                arr = history_features[name].to_numpy().astype(np.float64)
                mask = np.isnan(arr)
                if mask.any():
                    arr[mask] = CACHED_DEFAULTS[name]
                hist_arrays[name] = arr
            else:
                hist_arrays[name] = np.full(n_bars_valid, CACHED_DEFAULTS[name])

        # Previous-bar indices for historical features
        prev_indices = np.arange(n_bars_valid)
        prev_indices[1:] = np.arange(n_bars_valid - 1)

        realized_vols = hist_arrays.get(
            "realized_vol_10", np.full(n_bars_valid, CACHED_DEFAULTS["realized_vol_10"])
        )
        vol_sma_10s = hist_arrays.get(
            "volume_sma_10", np.full(n_bars_valid, CACHED_DEFAULTS["volume_sma_10"])
        )
        prev_vols = realized_vols[prev_indices]
        prev_vol_sma = vol_sma_10s[prev_indices]

        hist_matrix = np.column_stack([
            hist_arrays[name][prev_indices] for name in CACHED_FEATURE_NAMES
        ])

        # Get bar opens, closes, targets
        opens = bars_with_trades["open"].to_numpy().astype(np.float64)
        closes = bars_with_trades["close"].to_numpy().astype(np.float64)
        targets = (closes >= opens).astype(np.float64)
        bar_times = bars_with_trades["time"].to_list()

        # Process one day at a time
        all_X = []
        all_y = []
        all_mp = []
        all_bi = []
        all_tp = []

        unique_dates = sorted(set(bars_with_trades["_date_str"].to_list()))
        global_bar_idx = 0

        for date_str in unique_dates:
            # Load trades for this day
            day_trades = trades_store.read_trades(asset, start=date_str, end=date_str)
            if day_trades.is_empty():
                # Count bars for this day to advance global index
                day_mask = bars_with_trades["_date_str"] == date_str
                global_bar_idx += int(day_mask.sum())
                continue

            trade_times_us = day_trades["time"].dt.epoch("us").to_numpy()
            trade_prices = day_trades["price"].to_numpy().astype(np.float64)
            trade_qtys = day_trades["quantity"].to_numpy().astype(np.float64)
            trade_buyer = (
                day_trades["is_buyer_maker"].to_numpy()
                if "is_buyer_maker" in day_trades.columns
                else None
            )

            # Get bars for this day
            day_bar_mask = bars_with_trades["_date_str"] == date_str
            day_bar_indices = np.where(day_bar_mask.to_numpy())[0]

            for local_idx in day_bar_indices:
                bar_start = bar_times[local_idx]
                bar_start_us = int(bar_start.timestamp() * 1_000_000)
                bar_end_us = bar_start_us + int(self._total_seconds * 1_000_000)

                # Find trades in this bar's window
                window_mask = (trade_times_us >= bar_start_us) & (trade_times_us < bar_end_us)
                window_times = trade_times_us[window_mask]
                window_prices = trade_prices[window_mask]
                window_qtys = trade_qtys[window_mask]
                window_buyer = trade_buyer[window_mask] if trade_buyer is not None else None

                if len(window_prices) < 2:
                    global_bar_idx += 1
                    continue  # Skip bars with insufficient trades

                bar_open = opens[local_idx]
                bar_target = targets[local_idx]
                bar_prev_vol = prev_vols[local_idx]
                bar_prev_vol_sma = prev_vol_sma[local_idx]
                bar_hist = hist_matrix[local_idx]

                for t_pct in time_pcts:
                    cutoff_us = bar_start_us + int(t_pct * self._total_seconds * 1_000_000)
                    # All trades up to this time point
                    up_to = window_times <= cutoff_us

                    if not up_to.any():
                        # No trades yet at this time point — use open
                        price = bar_open
                        high = bar_open
                        low = bar_open
                        vol_so_far = 0.0
                        tc_so_far = 0
                    else:
                        prices_so_far = window_prices[up_to]
                        qtys_so_far = window_qtys[up_to]
                        price = float(prices_so_far[-1])
                        high = float(prices_so_far.max())
                        low = float(prices_so_far.min())
                        vol_so_far = float(qtys_so_far.sum())
                        tc_so_far = int(up_to.sum())

                    # Compute tick features
                    elapsed = t_pct * self._total_seconds
                    range_size = high - low
                    distance = (price - bar_open) / (bar_open + 1e-10)
                    vol_norm_dist = distance / (bar_prev_vol + 1e-10)

                    if range_size < 1e-10:
                        bar_pos = 0.5
                    else:
                        bar_pos = (price - low) / range_size

                    if t_pct < 0.001:
                        vol_ratio_partial = 0.0
                    else:
                        expected = bar_prev_vol_sma * t_pct
                        vol_ratio_partial = vol_so_far / (expected + 1e-10)

                    trade_intensity = tc_so_far / max(elapsed, 0.1)

                    features = np.empty(len(ALL_FEATURE_NAMES), dtype=np.float64)
                    features[0] = distance
                    features[1] = vol_norm_dist
                    features[2] = t_pct
                    features[3] = 1.0 - t_pct
                    features[4] = range_size / (bar_open + 1e-10)
                    features[5] = bar_pos
                    features[6] = vol_ratio_partial
                    features[7] = trade_intensity
                    features[8:] = bar_hist

                    all_X.append(features)
                    all_y.append(bar_target)
                    all_bi.append(global_bar_idx)
                    all_tp.append(t_pct)

                    # Market probability
                    if market_sim is not None:
                        mp = market_sim.market_prob(
                            bar_open, price, bar_prev_vol, elapsed,
                        )
                    else:
                        mp = 0.50
                    all_mp.append(mp)

                global_bar_idx += 1

        if not all_X:
            logger.warning("No valid samples generated from trade data")
            return self._empty_dataset()

        n_bars_used = len(set(all_bi))
        logger.info(
            "Generated %d samples from %d bars using real tick data",
            len(all_X), n_bars_used,
        )

        return IntraBarDataset(
            X=np.array(all_X, dtype=np.float64),
            y=np.array(all_y, dtype=np.float64),
            market_probs=np.array(all_mp, dtype=np.float64),
            bar_indices=np.array(all_bi, dtype=np.int64),
            time_pcts=np.array(all_tp, dtype=np.float64),
            feature_names=list(ALL_FEATURE_NAMES),
        )

    def _detect_asset(self, bars_df: pl.DataFrame) -> Asset | None:
        """Detect asset from bars_df if it has an asset column."""
        if "asset" in bars_df.columns:
            val = bars_df["asset"][0]
            for a in Asset:
                if a.value == val:
                    return a
        # Default to BTC if not detectable
        return Asset.BTC

    def _empty_dataset(self) -> IntraBarDataset:
        return IntraBarDataset(
            X=np.empty((0, len(ALL_FEATURE_NAMES)), dtype=np.float64),
            y=np.empty(0, dtype=np.float64),
            market_probs=np.empty(0, dtype=np.float64),
            bar_indices=np.empty(0, dtype=np.int64),
            time_pcts=np.empty(0, dtype=np.float64),
            feature_names=list(ALL_FEATURE_NAMES),
        )
