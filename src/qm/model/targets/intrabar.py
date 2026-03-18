"""Training data generator for the Pulse intra-bar model.

Generates synthetic partial-bar snapshots from completed OHLCV bars
using OHLC-aware path simulation. Produces 16 samples per bar with
dense early coverage for maximum early-bar ROI.

CRITICAL: Samples from the same bar share a target.
Split at BAR level using bar_indices, not sample level.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from qm.backtest.market_sim import MarketOddsSimulator
from qm.features.intrabar import (
    ALL_FEATURE_NAMES,
    CACHED_DEFAULTS,
    CACHED_FEATURE_NAMES,
)

# Dense early coverage: 16 samples per bar
DEFAULT_TIME_PCTS: list[float] = [
    0.003, 0.01, 0.03, 0.05, 0.10, 0.15, 0.20, 0.30,
    0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.98,
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


def _simulate_ohlc_path(
    open_price: float,
    high: float,
    low: float,
    close: float,
    time_pct: float,
    rng: np.random.Generator | None = None,
    noise_std: float = 0.0,
    realized_vol: float = 0.01,
) -> tuple[float, float, float]:
    """Simulate price at a given point along an OHLC-aware path.

    Path model (3 segments):
    - Up-bar (close >= open): open -> low -> high -> close
    - Down-bar (close < open): open -> high -> low -> close

    Returns:
        (current_price, high_so_far, low_so_far)
    """
    is_up = close >= open_price

    if is_up:
        # Segment 1: open -> low (0.0 to 0.25)
        # Segment 2: low -> high (0.25 to 0.75)
        # Segment 3: high -> close (0.75 to 1.0)
        if time_pct <= 0.25:
            frac = time_pct / 0.25
            price = open_price + (low - open_price) * frac
            h_so_far = max(open_price, price)
            l_so_far = min(open_price, price)
        elif time_pct <= 0.75:
            frac = (time_pct - 0.25) / 0.50
            price = low + (high - low) * frac
            h_so_far = max(open_price, price)
            l_so_far = low
        else:
            frac = (time_pct - 0.75) / 0.25
            price = high + (close - high) * frac
            h_so_far = high
            l_so_far = low
    else:
        # Down-bar: open -> high -> low -> close
        if time_pct <= 0.25:
            frac = time_pct / 0.25
            price = open_price + (high - open_price) * frac
            h_so_far = max(open_price, price)
            l_so_far = min(open_price, price)
        elif time_pct <= 0.75:
            frac = (time_pct - 0.25) / 0.50
            price = high + (low - high) * frac
            h_so_far = high
            l_so_far = min(open_price, price)
        else:
            frac = (time_pct - 0.75) / 0.25
            price = low + (close - low) * frac
            h_so_far = high
            l_so_far = low

    # Add noise to prevent overfitting to the deterministic path
    if noise_std > 0.0 and rng is not None:
        noise = rng.normal(0.0, noise_std * realized_vol * open_price)
        price = price + noise
        h_so_far = max(h_so_far, price)
        l_so_far = min(l_so_far, price)

    return price, h_so_far, l_so_far


class IntraBarTrainingDataGenerator:
    """Generate intra-bar training samples from completed OHLCV bars.

    For each bar, simulates partial bar states at configurable time points.
    Uses OHLC-aware path simulation with optional noise.

    Processes bars in chunks to limit peak memory usage.
    """

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed

    def generate(
        self,
        bars_df: pl.DataFrame,
        history_features: pl.DataFrame,
        market_sim: MarketOddsSimulator,
        time_pcts: list[float] | None = None,
        chunk_size: int = 50_000,
        path_noise_std: float = 0.1,
    ) -> IntraBarDataset:
        """Generate training data from completed bars.

        Args:
            bars_df: OHLCV bars with columns: open, high, low, close, volume, trade_count.
            history_features: Sentinel pipeline output aligned with bars_df
                (one row per bar, columns include CACHED_FEATURE_NAMES).
            market_sim: Market odds simulator for computing simulated market_prob.
            time_pcts: Elapsed fractions to sample. Defaults to 16-point dense-early.
            chunk_size: Process this many bars per chunk to limit memory.
            path_noise_std: Noise magnitude as fraction of realized_vol.

        Returns:
            IntraBarDataset with X, y, market_probs, bar_indices, time_pcts.
        """
        if time_pcts is None:
            time_pcts = DEFAULT_TIME_PCTS

        n_bars = len(bars_df)
        n_time_points = len(time_pcts)
        total_seconds = market_sim.total_seconds

        if n_bars == 0:
            return IntraBarDataset(
                X=np.empty((0, len(ALL_FEATURE_NAMES)), dtype=np.float64),
                y=np.empty(0, dtype=np.float64),
                market_probs=np.empty(0, dtype=np.float64),
                bar_indices=np.empty(0, dtype=np.int64),
                time_pcts=np.empty(0, dtype=np.float64),
                feature_names=list(ALL_FEATURE_NAMES),
            )

        # Convert to numpy for speed
        opens = bars_df["open"].to_numpy()
        highs = bars_df["high"].to_numpy()
        lows = bars_df["low"].to_numpy()
        closes = bars_df["close"].to_numpy()
        volumes = bars_df["volume"].to_numpy()
        trade_counts = bars_df["trade_count"].to_numpy() if "trade_count" in bars_df.columns else np.ones(n_bars)

        # Targets: close >= open for each bar
        targets = (closes >= opens).astype(np.float64)

        # Extract cached features from history_features
        hist_arrays: dict[str, np.ndarray] = {}
        for name in CACHED_FEATURE_NAMES:
            if name in history_features.columns:
                arr = history_features[name].to_numpy().astype(np.float64)
                # Fill NaN with defaults
                mask = np.isnan(arr)
                if mask.any():
                    arr[mask] = CACHED_DEFAULTS[name]
                hist_arrays[name] = arr
            else:
                hist_arrays[name] = np.full(n_bars, CACHED_DEFAULTS[name])

        rng = np.random.default_rng(self._seed)

        # Process in chunks
        all_chunks_X = []
        all_chunks_y = []
        all_chunks_mp = []
        all_chunks_bi = []
        all_chunks_tp = []

        time_pcts_arr = np.array(time_pcts, dtype=np.float64)

        for chunk_start in range(0, n_bars, chunk_size):
            chunk_end = min(chunk_start + chunk_size, n_bars)
            n_chunk = chunk_end - chunk_start
            n_samples = n_chunk * n_time_points

            X = np.empty((n_samples, len(ALL_FEATURE_NAMES)), dtype=np.float64)
            y = np.empty(n_samples, dtype=np.float64)
            mp = np.empty(n_samples, dtype=np.float64)
            bi = np.empty(n_samples, dtype=np.int64)
            tp = np.empty(n_samples, dtype=np.float64)

            for local_i in range(n_chunk):
                bar_i = chunk_start + local_i
                o = opens[bar_i]
                h = highs[bar_i]
                lo = lows[bar_i]
                c = closes[bar_i]
                vol_bar = volumes[bar_i]
                tc_bar = trade_counts[bar_i]
                target = targets[bar_i]

                # Get history from PREVIOUS bar (bar_i - 1), since the
                # Pulse model sees features from the last COMPLETED bar
                if bar_i > 0:
                    prev_i = bar_i - 1
                else:
                    prev_i = 0  # first bar uses its own features as fallback

                realized_vol = hist_arrays.get("realized_vol_10", np.full(n_bars, 0.01))[prev_i]
                vol_sma_10 = hist_arrays.get("volume_sma_10", np.full(n_bars, 1.0))[prev_i]

                for t_idx, t_pct in enumerate(time_pcts):
                    sample_idx = local_i * n_time_points + t_idx

                    # Simulate price path
                    price, h_so_far, l_so_far = _simulate_ohlc_path(
                        o, h, lo, c, t_pct,
                        rng=rng, noise_std=path_noise_std,
                        realized_vol=realized_vol,
                    )

                    elapsed = t_pct * total_seconds
                    remaining = total_seconds - elapsed
                    range_size = h_so_far - l_so_far

                    # Tick features
                    distance = (price - o) / (o + 1e-10)
                    vol_norm_dist = distance / (realized_vol + 1e-10)

                    if range_size < 1e-10:
                        bar_pos = 0.5
                    else:
                        bar_pos = (price - l_so_far) / range_size

                    if t_pct < 0.001:
                        vol_ratio_partial = 0.0
                    else:
                        expected_vol = vol_sma_10 * t_pct
                        vol_so_far = vol_bar * t_pct  # approximate
                        vol_ratio_partial = vol_so_far / (expected_vol + 1e-10)

                    trade_count_so_far = max(1, int(tc_bar * t_pct))
                    trade_intensity = trade_count_so_far / max(elapsed, 0.1)

                    X[sample_idx, 0] = distance
                    X[sample_idx, 1] = vol_norm_dist
                    X[sample_idx, 2] = t_pct
                    X[sample_idx, 3] = 1.0 - t_pct
                    X[sample_idx, 4] = range_size / (o + 1e-10)
                    X[sample_idx, 5] = bar_pos
                    X[sample_idx, 6] = vol_ratio_partial
                    X[sample_idx, 7] = trade_intensity

                    # Historical features from previous bar
                    for feat_idx, name in enumerate(CACHED_FEATURE_NAMES):
                        X[sample_idx, 8 + feat_idx] = hist_arrays[name][prev_i]

                    y[sample_idx] = target
                    bi[sample_idx] = bar_i
                    tp[sample_idx] = t_pct

                    # Market probability
                    mp[sample_idx] = market_sim.market_prob(
                        o, price, realized_vol, elapsed
                    )

            all_chunks_X.append(X)
            all_chunks_y.append(y)
            all_chunks_mp.append(mp)
            all_chunks_bi.append(bi)
            all_chunks_tp.append(tp)

        return IntraBarDataset(
            X=np.concatenate(all_chunks_X, axis=0),
            y=np.concatenate(all_chunks_y),
            market_probs=np.concatenate(all_chunks_mp),
            bar_indices=np.concatenate(all_chunks_bi),
            time_pcts=np.concatenate(all_chunks_tp),
            feature_names=list(ALL_FEATURE_NAMES),
        )
