//! L2 orderbook with delta application for Polymarket.
//!
//! Maintains a sorted orderbook from WebSocket delta updates.
//! Computes mid-price, spread, and market impact in O(1).

use pyo3::prelude::*;
use std::collections::BTreeMap;

/// L2 orderbook with real-time spread and depth tracking.
///
/// Bids are stored highest-first, asks lowest-first (BTreeMap).
/// Updates via `apply_delta()` from WebSocket messages.
#[pyclass]
pub struct L2Orderbook {
    /// Bids: price → size (sorted descending by negated key)
    bids: BTreeMap<OrderedFloat, f64>,
    /// Asks: price → size (sorted ascending)
    asks: BTreeMap<OrderedFloat, f64>,
}

/// Wrapper for f64 that implements Ord (for BTreeMap).
/// NaN is treated as less than all values.
#[derive(Debug, Clone, Copy, PartialEq)]
struct OrderedFloat(f64);

impl Eq for OrderedFloat {}

impl PartialOrd for OrderedFloat {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for OrderedFloat {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.0.partial_cmp(&other.0).unwrap_or(std::cmp::Ordering::Equal)
    }
}

#[pymethods]
impl L2Orderbook {
    #[new]
    fn new() -> Self {
        Self {
            bids: BTreeMap::new(),
            asks: BTreeMap::new(),
        }
    }

    /// Apply a delta update from WebSocket.
    ///
    /// side: "bid" or "ask"
    /// price: price level
    /// size: new size at this level (0 = remove)
    fn apply_delta(&mut self, side: &str, price: f64, size: f64) {
        let book = match side {
            "bid" => &mut self.bids,
            "ask" => &mut self.asks,
            _ => return,
        };

        let key = if side == "bid" {
            // Negate bids so BTreeMap sorts highest first
            OrderedFloat(-price)
        } else {
            OrderedFloat(price)
        };

        if size <= 0.0 {
            book.remove(&key);
        } else {
            book.insert(key, size);
        }
    }

    /// Best bid price (highest).
    fn best_bid(&self) -> Option<f64> {
        self.bids.keys().next().map(|k| -k.0)
    }

    /// Best ask price (lowest).
    fn best_ask(&self) -> Option<f64> {
        self.asks.keys().next().map(|k| k.0)
    }

    /// Mid-price: (best_bid + best_ask) / 2.
    fn mid_price(&self) -> Option<f64> {
        match (self.best_bid(), self.best_ask()) {
            (Some(bid), Some(ask)) => Some((bid + ask) / 2.0),
            _ => None,
        }
    }

    /// Spread: best_ask - best_bid.
    fn spread(&self) -> Option<f64> {
        match (self.best_bid(), self.best_ask()) {
            (Some(bid), Some(ask)) => Some(ask - bid),
            _ => None,
        }
    }

    /// Total depth on bid side (sum of all bid sizes).
    fn bid_depth(&self) -> f64 {
        self.bids.values().sum()
    }

    /// Total depth on ask side (sum of all ask sizes).
    fn ask_depth(&self) -> f64 {
        self.asks.values().sum()
    }

    /// Order imbalance: (bid_depth - ask_depth) / (bid_depth + ask_depth).
    fn imbalance(&self) -> f64 {
        let bid_d = self.bid_depth();
        let ask_d = self.ask_depth();
        let total = bid_d + ask_d;
        if total < 1e-10 {
            return 0.0;
        }
        (bid_d - ask_d) / total
    }

    /// Square-root market impact estimate.
    ///
    /// impact = impact_bps/10000 * sqrt(order_size / total_depth)
    fn market_impact(&self, order_size: f64, impact_bps: f64) -> f64 {
        let total_depth = self.bid_depth() + self.ask_depth();
        if total_depth < 1e-10 {
            return impact_bps / 10_000.0;
        }
        (impact_bps / 10_000.0) * (order_size / total_depth).sqrt()
    }

    /// Number of price levels on each side.
    fn n_levels(&self) -> (usize, usize) {
        (self.bids.len(), self.asks.len())
    }

    /// Clear all levels.
    fn clear(&mut self) {
        self.bids.clear();
        self.asks.clear();
    }
}
