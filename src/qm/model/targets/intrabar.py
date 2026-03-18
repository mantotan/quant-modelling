"""Training data generator for the Pulse intra-bar model.

Uses REAL 1-minute bar data to construct honest intra-bar snapshots.
No synthetic path simulation — intermediate prices come from actual
market observations that may or may not align with the final bar direction.

CRITICAL: Samples from the same bar share a target.
Split at BAR level using bar_indices, not sample level.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import polars as pl

from qm.backtest.market_sim import MarketOddsSimulator
from qm.core.constants import TIMEFRAME_MINUTES
from qm.core.types import Timeframe
from qm.features.intrabar import (
    ALL_FEATURE_NAMES,
    CACHED_DEFAULTS,
    CACHED_FEATURE_NAMES,
)

logger = logging.getLogger(__name__)

# Aligned with real 1m boundaries for 5m bars + early interpolation points
DEFAULT_TIME_PCTS: list[float] = [
    0.003, 0.01, 0.05, 0.10, 0.20, 0.40, 0.60, 0.80, 0.90, 0.95,
]


@dataclass
class IntraBarDataset:
    """Training data for the Pulse model."""

    X: np.ndarray  # (n_samples, 23) features
    y: np.ndarray  # (n_samples,) binary targets (close >= open)
    market_probs: np.ndarray  # (n_samples,) simulated market odds
    bar_indices: np.ndarray  # (n_samples,) bar index per sample
    time_pcts: np.ndarray  # (n_samples,) elapsed_pct per sample
    feature_names: list[str]  # 23 feature names


def _align_1m_to_parent(
    bars_df: pl.DataFrame,
    m1_bars_df: pl.DataFrame,
    parent_minutes: int,
) -> tuple[pl.DataFrame, np.ndarray]:
    """Align 1-minute bars to parent timeframe bars.

    For each parent bar, finds its constituent 1m bars and builds a
    snapshot matrix of 1m close prices.

    Args:
        bars_df: Parent bars (e.g. 5m) with 'time' column.
        m1_bars_df: 1-minute bars with 'time' column.
        parent_minutes: Duration of parent bars in minutes (e.g. 5).

    Returns:
        (filtered_bars_df, m1_closes) where:
        - filtered_bars_df: Parent bars that have all constituent 1m bars
        - m1_closes: shape (n_valid_bars, parent_minutes) array of 1m close prices
    """
    n_constituent = parent_minutes  # e.g. 5 for 5m bars

    # Build lookup: parent_time -> list of 1m close prices
    # For parent bar at time T, 1m bars are at T, T+60s, ..., T+(n-1)*60s
    m1_times = m1_bars_df["time"]
    m1_close_arr = m1_bars_df["close"].to_numpy().astype(np.float64)
    m1_vol_arr = m1_bars_df["volume"].to_numpy().astype(np.float64)
    m1_tc_arr = (
        m1_bars_df["trade_count"].to_numpy().astype(np.float64)
        if "trade_count" in m1_bars_df.columns
        else np.ones(len(m1_bars_df))
    )

    # Create a dict mapping timestamp -> index in m1 arrays
    m1_time_to_idx: dict[int, int] = {}
    m1_times_list = m1_times.to_list()
    for i, t in enumerate(m1_times_list):
        # Use epoch microseconds as key for fast lookup
        m1_time_to_idx[int(t.timestamp() * 1_000_000)] = i

    parent_times = bars_df["time"].to_list()
    valid_mask = []
    all_m1_closes = []
    all_m1_volumes = []
    all_m1_tc = []

    for pt in parent_times:
        closes = []
        vols = []
        tcs = []
        complete = True
        for offset_min in range(n_constituent):
            t_1m = pt + timedelta(minutes=offset_min)
            key = int(t_1m.timestamp() * 1_000_000)
            idx = m1_time_to_idx.get(key)
            if idx is None:
                complete = False
                break
            closes.append(m1_close_arr[idx])
            vols.append(m1_vol_arr[idx])
            tcs.append(m1_tc_arr[idx])

        valid_mask.append(complete)
        if complete:
            all_m1_closes.append(closes)
            all_m1_volumes.append(vols)
            all_m1_tc.append(tcs)

    valid_np = np.array(valid_mask)
    n_valid = int(valid_np.sum())

    if n_valid == 0:
        return bars_df.head(0), np.empty((0, n_constituent))

    filtered_bars = bars_df.filter(pl.Series(valid_mask))

    m1_closes = np.array(all_m1_closes, dtype=np.float64)  # (n_valid, n_constituent)
    m1_volumes = np.array(all_m1_volumes, dtype=np.float64)
    m1_tcs = np.array(all_m1_tc, dtype=np.float64)

    n_dropped = len(bars_df) - n_valid
    if n_dropped > 0:
        logger.info(
            "Dropped %d/%d parent bars without complete 1m data (%.1f%% kept)",
            n_dropped, len(bars_df), 100 * n_valid / len(bars_df),
        )

    return filtered_bars, m1_closes, m1_volumes, m1_tcs


def _interpolate_price_at_pct(
    opens: np.ndarray,
    m1_closes: np.ndarray,
    time_pct: float,
    parent_minutes: int,
) -> np.ndarray:
    """Interpolate price at a given time_pct using real 1m data.

    Snapshot points: open at pct=0.0, then 1m closes at
    pct = 1/N, 2/N, ..., N/N where N = parent_minutes.

    Between snapshots, linearly interpolate.

    Args:
        opens: Parent bar opens, shape (n_bars,)
        m1_closes: 1m close prices, shape (n_bars, parent_minutes)
        time_pct: Fraction of bar elapsed (0 to 1)
        parent_minutes: Number of constituent 1m bars

    Returns:
        Interpolated prices, shape (n_bars,)
    """
    n = parent_minutes
    # Snapshot fractions: 0.0 (open), 1/n, 2/n, ..., 1.0
    # e.g. for 5m: 0.0, 0.2, 0.4, 0.6, 0.8, 1.0
    # m1_closes[:, 0] = close at 1/n, m1_closes[:, n-1] = close at 1.0

    # Which segment does time_pct fall in?
    segment_frac = time_pct * n  # e.g. 0.3 * 5 = 1.5
    seg_idx = int(segment_frac)  # 1
    local_frac = segment_frac - seg_idx  # 0.5

    if seg_idx <= 0:
        # Before first 1m close: interpolate between open and m1_closes[:, 0]
        frac = time_pct * n  # 0 to 1 within first segment
        return opens + (m1_closes[:, 0] - opens) * frac
    elif seg_idx >= n:
        # At or past the end: return last 1m close (= parent close)
        return m1_closes[:, n - 1]
    else:
        # Between two 1m closes
        prev_close = m1_closes[:, seg_idx - 1]
        next_close = m1_closes[:, seg_idx]
        return prev_close + (next_close - prev_close) * local_frac


def _compute_high_low_so_far(
    opens: np.ndarray,
    m1_closes: np.ndarray,
    time_pct: float,
    parent_minutes: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute running high/low from real 1m data up to time_pct.

    Uses the open + all 1m closes that have completed before time_pct.

    Returns:
        (high_so_far, low_so_far) each shape (n_bars,)
    """
    n = parent_minutes
    # How many complete 1m bars have elapsed?
    n_complete = min(int(time_pct * n), n)

    # Start with open
    high = opens.copy()
    low = opens.copy()

    # Include completed 1m closes
    for i in range(n_complete):
        high = np.maximum(high, m1_closes[:, i])
        low = np.minimum(low, m1_closes[:, i])

    # Also include the interpolated current price
    current = _interpolate_price_at_pct(opens, m1_closes, time_pct, parent_minutes)
    high = np.maximum(high, current)
    low = np.minimum(low, current)

    return high, low


class RealPathIntraBarDataGenerator:
    """Generate intra-bar samples using REAL 1-minute bar data.

    For each parent bar (5m/15m/1h), looks up its constituent 1m bars
    to get real intermediate prices. No synthetic path simulation.

    A 5m up-bar can have its 1m close at t=120s BELOW the open.
    The model cannot learn 'distance > 0 implies Up' because that
    rule is frequently wrong at intermediate times in real data.
    """

    def __init__(self, timeframe: Timeframe = Timeframe.M5, seed: int = 42) -> None:
        self._minutes = TIMEFRAME_MINUTES[timeframe]
        self._total_seconds = float(self._minutes * 60)
        self._seed = seed

    def generate(
        self,
        bars_df: pl.DataFrame,
        m1_bars_df: pl.DataFrame,
        history_features: pl.DataFrame,
        market_sim: MarketOddsSimulator,
        time_pcts: list[float] | None = None,
        chunk_size: int = 50_000,
    ) -> IntraBarDataset:
        """Generate training data from parent bars + real 1m data.

        Args:
            bars_df: Parent timeframe bars (5m/15m/1h).
            m1_bars_df: 1-minute bars covering the same period.
            history_features: Sentinel pipeline features aligned with bars_df.
            market_sim: Market odds simulator.
            time_pcts: Elapsed fractions to sample.
            chunk_size: Bars per chunk for memory control.

        Returns:
            IntraBarDataset. Bars without complete 1m data are dropped.
        """
        if time_pcts is None:
            time_pcts = DEFAULT_TIME_PCTS

        n_tp = len(time_pcts)

        if len(bars_df) == 0 or len(m1_bars_df) == 0:
            return self._empty_dataset()

        # Align 1m bars to parent bars, drop incomplete
        filtered_bars, m1_closes, m1_volumes, m1_tcs = _align_1m_to_parent(
            bars_df, m1_bars_df, self._minutes,
        )
        n_bars = len(filtered_bars)

        if n_bars == 0:
            logger.warning("No parent bars have complete 1m data")
            return self._empty_dataset()

        logger.info(
            "Using %d parent bars with complete 1m data (%d 1m bars each)",
            n_bars, self._minutes,
        )

        # Also filter history_features to match
        filtered_times_set = set(filtered_bars["time"].to_list())
        valid_indices = np.array([
            i for i, t in enumerate(bars_df["time"].to_list())
            if t in filtered_times_set
        ])
        history_features = history_features[valid_indices]

        # Convert to numpy
        opens = filtered_bars["open"].to_numpy().astype(np.float64)
        closes = filtered_bars["close"].to_numpy().astype(np.float64)
        targets = (closes >= opens).astype(np.float64)

        # Extract cached features
        hist_arrays: dict[str, np.ndarray] = {}
        for name in CACHED_FEATURE_NAMES:
            if name in history_features.columns:
                arr = history_features[name].to_numpy().astype(np.float64)
                mask = np.isnan(arr)
                if mask.any():
                    arr[mask] = CACHED_DEFAULTS[name]
                hist_arrays[name] = arr
            else:
                hist_arrays[name] = np.full(n_bars, CACHED_DEFAULTS[name])

        # Previous-bar indices
        prev_indices = np.arange(n_bars)
        prev_indices[1:] = np.arange(n_bars - 1)

        realized_vols = hist_arrays.get(
            "realized_vol_10", np.full(n_bars, CACHED_DEFAULTS["realized_vol_10"])
        )
        vol_sma_10s = hist_arrays.get(
            "volume_sma_10", np.full(n_bars, CACHED_DEFAULTS["volume_sma_10"])
        )
        prev_vols = realized_vols[prev_indices]
        prev_vol_sma = vol_sma_10s[prev_indices]

        hist_matrix = np.column_stack([
            hist_arrays[name][prev_indices] for name in CACHED_FEATURE_NAMES
        ])

        # Total volume/trade_count per parent bar (sum of 1m constituents)
        total_volumes = m1_volumes.sum(axis=1)
        total_tc = m1_tcs.sum(axis=1)
        # Cumulative volumes per 1m bar (for interpolation)
        cum_volumes = np.cumsum(m1_volumes, axis=1)
        cum_tc = np.cumsum(m1_tcs, axis=1)

        # Build dataset: iterate time points, vectorize over bars
        all_X = []
        all_y = []
        all_mp = []
        all_bi = []
        all_tp = []

        for chunk_start in range(0, n_bars, chunk_size):
            chunk_end = min(chunk_start + chunk_size, n_bars)
            sl = slice(chunk_start, chunk_end)
            n_chunk = chunk_end - chunk_start
            n_samples = n_chunk * n_tp

            X = np.empty((n_samples, len(ALL_FEATURE_NAMES)), dtype=np.float64)
            y_out = np.empty(n_samples, dtype=np.float64)
            mp_out = np.empty(n_samples, dtype=np.float64)
            bi_out = np.empty(n_samples, dtype=np.int64)
            tp_out = np.empty(n_samples, dtype=np.float64)

            c_opens = opens[sl]
            c_m1_closes = m1_closes[sl]
            c_targets = targets[sl]
            c_prev_vols = prev_vols[sl]
            c_prev_vol_sma = prev_vol_sma[sl]
            c_hist = hist_matrix[sl]
            c_total_vol = total_volumes[sl]
            c_total_tc = total_tc[sl]
            c_cum_vol = cum_volumes[sl]
            c_cum_tc = cum_tc[sl]
            c_bar_indices = np.arange(chunk_start, chunk_end)

            for t_idx, t_pct in enumerate(time_pcts):
                row_start = t_idx * n_chunk
                row_end = row_start + n_chunk

                # Real interpolated prices from 1m data
                prices = _interpolate_price_at_pct(
                    c_opens, c_m1_closes, t_pct, self._minutes,
                )
                h_so_far, l_so_far = _compute_high_low_so_far(
                    c_opens, c_m1_closes, t_pct, self._minutes,
                )

                elapsed = t_pct * self._total_seconds
                range_size = h_so_far - l_so_far

                # Volume/TC so far: use cumulative 1m data
                n_complete_1m = min(int(t_pct * self._minutes), self._minutes)
                if n_complete_1m > 0:
                    vol_so_far = c_cum_vol[:, n_complete_1m - 1]
                    tc_so_far = c_cum_tc[:, n_complete_1m - 1]
                else:
                    vol_so_far = np.zeros(n_chunk)
                    tc_so_far = np.ones(n_chunk)

                # Tick features
                distance = (prices - c_opens) / (c_opens + 1e-10)
                vol_norm_dist = distance / (c_prev_vols + 1e-10)

                bar_pos = np.where(
                    range_size < 1e-10,
                    0.5,
                    (prices - l_so_far) / (range_size + 1e-10),
                )

                if t_pct < 0.001:
                    vol_ratio_partial = np.zeros(n_chunk)
                else:
                    expected_vol = c_prev_vol_sma * t_pct
                    vol_ratio_partial = vol_so_far / (expected_vol + 1e-10)

                trade_intensity = tc_so_far / max(elapsed, 0.1)

                X[row_start:row_end, 0] = distance
                X[row_start:row_end, 1] = vol_norm_dist
                X[row_start:row_end, 2] = t_pct
                X[row_start:row_end, 3] = 1.0 - t_pct
                X[row_start:row_end, 4] = range_size / (c_opens + 1e-10)
                X[row_start:row_end, 5] = bar_pos
                X[row_start:row_end, 6] = vol_ratio_partial
                X[row_start:row_end, 7] = trade_intensity
                X[row_start:row_end, 8:] = c_hist

                y_out[row_start:row_end] = c_targets
                bi_out[row_start:row_end] = c_bar_indices
                tp_out[row_start:row_end] = t_pct

                mp_out[row_start:row_end] = market_sim.market_prob_batch(
                    c_opens, prices, c_prev_vols,
                    np.full(n_chunk, elapsed),
                )

            # Reorder: (n_tp, n_chunk) -> (n_chunk, n_tp) so bar samples are contiguous
            idx = np.arange(n_samples).reshape(n_tp, n_chunk).T.ravel()
            all_X.append(X[idx])
            all_y.append(y_out[idx])
            all_mp.append(mp_out[idx])
            all_bi.append(bi_out[idx])
            all_tp.append(tp_out[idx])

        return IntraBarDataset(
            X=np.concatenate(all_X, axis=0),
            y=np.concatenate(all_y),
            market_probs=np.concatenate(all_mp),
            bar_indices=np.concatenate(all_bi),
            time_pcts=np.concatenate(all_tp),
            feature_names=list(ALL_FEATURE_NAMES),
        )

    def _empty_dataset(self) -> IntraBarDataset:
        return IntraBarDataset(
            X=np.empty((0, len(ALL_FEATURE_NAMES)), dtype=np.float64),
            y=np.empty(0, dtype=np.float64),
            market_probs=np.empty(0, dtype=np.float64),
            bar_indices=np.empty(0, dtype=np.int64),
            time_pcts=np.empty(0, dtype=np.float64),
            feature_names=list(ALL_FEATURE_NAMES),
        )


# Legacy: keep old simulated generator for backward compatibility with tests
class LegacySimulatedDataGenerator:
    """DEPRECATED: Uses synthetic OHLC path simulation. Causes target leakage.

    Kept only for legacy test compatibility. Do NOT use for training.
    """

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed

    def generate(self, *args, **kwargs) -> IntraBarDataset:
        msg = (
            "LegacySimulatedDataGenerator is deprecated due to target leakage. "
            "Use RealPathIntraBarDataGenerator with real 1m bar data."
        )
        raise DeprecationWarning(msg)
