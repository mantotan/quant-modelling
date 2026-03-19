"""Intra-bar feature calculator for the Pulse model.

Computes 23 features (8 tick + 15 historical) in < 0.05ms.
Pure arithmetic on PartialBar + cached history from the Sentinel pipeline.

At t=0, all tick features are ~0. The model relies entirely on
the 15 historical features (RSI, Stochastic, MACD, etc.) which
LightGBM learns to weight heavily at low elapsed_pct.
"""

from __future__ import annotations

import numpy as np

from qm.core.types import Asset, PartialBar

# Historical features cached from the Sentinel pipeline output
CACHED_FEATURE_NAMES: list[str] = [
    # --- Core TA features ---
    "rsi_14",
    "rsi_7",
    "stoch_k",
    "macd_histogram",
    "williams_r",
    "roc_5",
    "realized_vol_10",
    "vol_ratio",
    "parkinson_vol_10",
    "bar_position",
    "body_ratio",
    "return_5",
    "volume_sma_10",
    "hour_sin",
    "hour_cos",
    # --- Alpha features (graceful: absent columns are skipped) ---
    "funding_rate",
    "funding_rate_sma3",
    "funding_rate_pctile",
    "funding_rate_direction",
    "funding_cumulative_24h",
    "funding_hours_since",
    "liquidation_proximity",
    "oi_price_divergence",
    "oi_momentum",
    "leverage_proxy",
    "regime_vol_state",
    "regime_vol_zscore",
    "regime_trend_state",
    "iv_atm",
    "iv_skew",
    "iv_term_spread",
    "iv_change_1h",
    "iv_percentile_30d",
    "pm_bid_ask_spread",
    "pm_order_imbalance",
    "pm_trade_flow",
    "pm_mid_momentum",
    # --- Interaction features ---
    "funding_x_rsi",
    "funding_x_vol",
    "oi_div_x_momentum",
    "leverage_x_proximity",
    "regime_x_funding",
]

# Sensible mid-range defaults for the first bar before cache is populated
CACHED_DEFAULTS: dict[str, float] = {
    # Core TA
    "rsi_14": 50.0,
    "rsi_7": 50.0,
    "stoch_k": 50.0,
    "macd_histogram": 0.0,
    "williams_r": -50.0,
    "roc_5": 0.0,
    "realized_vol_10": 0.01,
    "vol_ratio": 1.0,
    "parkinson_vol_10": 0.01,
    "bar_position": 0.5,
    "body_ratio": 0.5,
    "return_5": 0.0,
    "volume_sma_10": 1.0,
    "hour_sin": 0.0,
    "hour_cos": 1.0,
    # Alpha features (neutral defaults — LightGBM handles nulls natively)
    "funding_rate": 0.0,
    "funding_rate_sma3": 0.0,
    "funding_rate_pctile": 0.5,
    "funding_rate_direction": 0.0,
    "funding_cumulative_24h": 0.0,
    "funding_hours_since": 4.0,
    "liquidation_proximity": 0.0,
    "oi_price_divergence": 0.0,
    "oi_momentum": 0.0,
    "leverage_proxy": 100.0,
    "regime_vol_state": 1.0,
    "regime_vol_zscore": 0.0,
    "regime_trend_state": 0.0,
    "iv_atm": 0.5,
    "iv_skew": 0.0,
    "iv_term_spread": 0.0,
    "iv_change_1h": 0.0,
    "iv_percentile_30d": 0.5,
    "pm_bid_ask_spread": 0.02,
    "pm_order_imbalance": 0.0,
    "pm_trade_flow": 0.0,
    "pm_mid_momentum": 0.0,
    # Interactions (neutral = 0)
    "funding_x_rsi": 0.0,
    "funding_x_vol": 0.0,
    "oi_div_x_momentum": 0.0,
    "leverage_x_proximity": 0.0,
    "regime_x_funding": 0.0,
}

TICK_FEATURE_NAMES: list[str] = [
    "distance_from_open",
    "vol_norm_distance",
    "elapsed_pct",
    "time_remaining_pct",
    "partial_range",
    "partial_bar_position",
    "volume_ratio_partial",
    "trade_intensity",
]

ALL_FEATURE_NAMES: list[str] = TICK_FEATURE_NAMES + CACHED_FEATURE_NAMES


class IntraBarFeatureCalculator:
    """23 features in < 0.05ms. Pure arithmetic on PartialBar + cached history.

    Usage:
        calc = IntraBarFeatureCalculator()
        # On each bar completion, cache Sentinel features:
        calc.update_cache(asset, {"rsi_14": 35.2, "stoch_k": 22.5, ...})
        # On each tick:
        features = calc.compute(partial_bar)  # np.ndarray shape (23,)
    """

    def __init__(self) -> None:
        self._history_cache: dict[Asset, dict[str, float]] = {}
        self._cache_populated: set[Asset] = set()

    def update_cache(self, asset: Asset, features: dict[str, float]) -> None:
        """Cache historical features from the last completed bar.

        Called once per bar completion. Extracts the 15 required features
        from the Sentinel pipeline output.
        """
        self._history_cache[asset] = features
        self._cache_populated.add(asset)

    def is_ready(self, asset: Asset) -> bool:
        """True when cache has real data (not just defaults) for this asset."""
        return asset in self._cache_populated

    def compute(self, partial: PartialBar) -> np.ndarray:
        """Compute 23 features from a PartialBar snapshot.

        Returns:
            np.ndarray of shape (23,) with dtype float64.
        """
        cache = self._history_cache.get(partial.asset, {})
        total_sec = partial.elapsed_seconds + partial.remaining_seconds
        elapsed_pct = partial.elapsed_seconds / (total_sec + 1e-10)
        range_size = partial.high_so_far - partial.low_so_far
        vol = cache.get("realized_vol_10", CACHED_DEFAULTS["realized_vol_10"])
        vol_sma_10 = cache.get("volume_sma_10", CACHED_DEFAULTS["volume_sma_10"])

        # Handle range_size=0 (first tick: high == low == open)
        if range_size < 1e-10:
            bar_pos = 0.5
        else:
            bar_pos = (partial.current_price - partial.low_so_far) / range_size

        # Volume ratio: cumulative volume vs expected volume at this point
        if elapsed_pct < 0.001:
            vol_ratio_partial = 0.0
        else:
            expected_so_far = vol_sma_10 * elapsed_pct
            vol_ratio_partial = partial.volume_so_far / (expected_so_far + 1e-10)

        tick_features = [
            (partial.current_price - partial.open) / (partial.open + 1e-10),
            (partial.current_price - partial.open) / (partial.open * vol + 1e-10),
            elapsed_pct,
            1.0 - elapsed_pct,
            range_size / (partial.open + 1e-10),
            bar_pos,
            vol_ratio_partial,
            partial.trade_count / max(partial.elapsed_seconds, 0.1),
        ]
        hist_features = [
            cache.get(name, CACHED_DEFAULTS[name]) for name in CACHED_FEATURE_NAMES
        ]
        return np.array(tick_features + hist_features, dtype=np.float64)

    @property
    def feature_names(self) -> list[str]:
        """Ordered list of 23 feature names matching compute() output."""
        return list(ALL_FEATURE_NAMES)

    @property
    def n_features(self) -> int:
        return len(ALL_FEATURE_NAMES)
