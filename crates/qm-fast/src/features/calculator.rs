//! Intra-bar feature calculator — Rust port of IntraBarFeatureCalculator.
//!
//! Computes the same 8 tick features + 42 cached historical features
//! in the same order as the Python implementation. Parity tests ensure
//! outputs match within 1e-9.

use pyo3::prelude::*;
use std::collections::HashMap;

/// Number of tick features (computed from PartialBar state).
const N_TICK: usize = 8;

/// Cached feature names in exact order matching Python CACHED_FEATURE_NAMES.
const CACHED_NAMES: &[&str] = &[
    // Core TA (15)
    "rsi_14", "rsi_7", "stoch_k", "macd_histogram", "williams_r",
    "roc_5", "realized_vol_10", "vol_ratio", "parkinson_vol_10",
    "bar_position", "body_ratio", "return_5", "volume_sma_10",
    "hour_sin", "hour_cos",
    // Alpha: funding (6)
    "funding_rate", "funding_rate_sma3", "funding_rate_pctile",
    "funding_rate_direction", "funding_cumulative_24h", "funding_hours_since",
    // Alpha: liquidation (4)
    "liquidation_proximity", "oi_price_divergence", "oi_momentum", "leverage_proxy",
    // Alpha: regime (3)
    "regime_vol_state", "regime_vol_zscore", "regime_trend_state",
    // Alpha: options IV (5)
    "iv_atm", "iv_skew", "iv_term_spread", "iv_change_1h", "iv_percentile_30d",
    // Alpha: polymarket (4)
    "pm_bid_ask_spread", "pm_order_imbalance", "pm_trade_flow", "pm_mid_momentum",
    // Interactions (5)
    "funding_x_rsi", "funding_x_vol", "oi_div_x_momentum",
    "leverage_x_proximity", "regime_x_funding",
];

/// Default values for cached features (matches Python CACHED_DEFAULTS).
fn cached_default(name: &str) -> f64 {
    match name {
        "rsi_14" | "rsi_7" | "stoch_k" => 50.0,
        "williams_r" => -50.0,
        "realized_vol_10" | "parkinson_vol_10" => 0.01,
        "vol_ratio" | "volume_sma_10" | "hour_cos" | "regime_vol_state" => 1.0,
        "bar_position" | "body_ratio" | "funding_rate_pctile"
        | "iv_atm" | "iv_percentile_30d" => 0.5,
        "leverage_proxy" => 100.0,
        "funding_hours_since" => 4.0,
        "pm_bid_ask_spread" => 0.02,
        _ => 0.0,
    }
}

/// Rust port of Python IntraBarFeatureCalculator.
///
/// Computes 50 features (8 tick + 42 cached) from a partial bar snapshot.
/// The output array has the exact same order as the Python implementation.
#[pyclass]
pub struct FeatureCalculator {
    /// Historical feature cache per asset (keyed by asset name string).
    cache: HashMap<String, HashMap<String, f64>>,
}

#[pymethods]
impl FeatureCalculator {
    #[new]
    fn new() -> Self {
        Self {
            cache: HashMap::new(),
        }
    }

    /// Cache historical features from the last completed bar.
    ///
    /// Called once per bar completion from Python.
    fn update_cache(&mut self, asset: &str, features: HashMap<String, f64>) {
        self.cache.insert(asset.to_string(), features);
    }

    /// Check if cache has been populated for an asset.
    fn is_ready(&self, asset: &str) -> bool {
        self.cache.contains_key(asset)
    }

    /// Compute features from a partial bar snapshot.
    ///
    /// Args:
    ///   asset: Asset name ("BTC", "ETH", etc.)
    ///   open_price: Bar open price
    ///   high_so_far: Highest price so far in this bar
    ///   low_so_far: Lowest price so far in this bar
    ///   current_price: Latest trade price
    ///   volume_so_far: Cumulative volume in this bar
    ///   trade_count: Number of trades in this bar
    ///   elapsed_seconds: Seconds since bar start
    ///   remaining_seconds: Seconds until bar end
    ///
    /// Returns:
    ///   Vec<f64> of length 50 (8 tick + 42 cached) matching Python output.
    #[pyo3(signature = (
        asset, open_price, high_so_far, low_so_far, current_price,
        volume_so_far, trade_count, elapsed_seconds, remaining_seconds
    ))]
    fn compute(
        &self,
        asset: &str,
        open_price: f64,
        high_so_far: f64,
        low_so_far: f64,
        current_price: f64,
        volume_so_far: f64,
        trade_count: i64,
        elapsed_seconds: f64,
        remaining_seconds: f64,
    ) -> Vec<f64> {
        let empty = HashMap::new();
        let cache = self.cache.get(asset).unwrap_or(&empty);

        let total_sec = elapsed_seconds + remaining_seconds;
        let elapsed_pct = elapsed_seconds / (total_sec + 1e-10);
        let range_size = high_so_far - low_so_far;

        let vol = self.get_cached(cache, "realized_vol_10");
        let vol_sma_10 = self.get_cached(cache, "volume_sma_10");

        // Bar position: where is current price within the range?
        let bar_pos = if range_size < 1e-10 {
            0.5
        } else {
            (current_price - low_so_far) / range_size
        };

        // Volume ratio: actual vs expected volume at this elapsed point
        let vol_ratio_partial = if elapsed_pct < 0.001 {
            0.0
        } else {
            let expected = vol_sma_10 * elapsed_pct;
            volume_so_far / (expected + 1e-10)
        };

        // Trade intensity: trades per second
        let trade_intensity = trade_count as f64
            / if elapsed_seconds < 0.1 { 0.1 } else { elapsed_seconds };

        let n_cached = CACHED_NAMES.len();
        let total = N_TICK + n_cached;
        let mut out = Vec::with_capacity(total);

        // 8 tick features (same order as Python TICK_FEATURE_NAMES)
        out.push((current_price - open_price) / (open_price + 1e-10)); // distance_from_open
        out.push((current_price - open_price) / (open_price * vol + 1e-10)); // vol_norm_distance
        out.push(elapsed_pct); // elapsed_pct
        out.push(1.0 - elapsed_pct); // time_remaining_pct
        out.push(range_size / (open_price + 1e-10)); // partial_range
        out.push(bar_pos); // partial_bar_position
        out.push(vol_ratio_partial); // volume_ratio_partial
        out.push(trade_intensity); // trade_intensity

        // 42 cached historical features (same order as Python CACHED_FEATURE_NAMES)
        for &name in CACHED_NAMES {
            out.push(self.get_cached(cache, name));
        }

        out
    }

    /// Number of features returned by compute().
    fn n_features(&self) -> usize {
        N_TICK + CACHED_NAMES.len()
    }

    /// Feature names in order matching compute() output.
    fn feature_names(&self) -> Vec<String> {
        let mut names = vec![
            "distance_from_open".to_string(),
            "vol_norm_distance".to_string(),
            "elapsed_pct".to_string(),
            "time_remaining_pct".to_string(),
            "partial_range".to_string(),
            "partial_bar_position".to_string(),
            "volume_ratio_partial".to_string(),
            "trade_intensity".to_string(),
        ];
        for &name in CACHED_NAMES {
            names.push(name.to_string());
        }
        names
    }
}

impl FeatureCalculator {
    /// Get a cached feature value, falling back to default.
    fn get_cached(&self, cache: &HashMap<String, f64>, name: &str) -> f64 {
        cache
            .get(name)
            .copied()
            .unwrap_or_else(|| cached_default(name))
    }
}
