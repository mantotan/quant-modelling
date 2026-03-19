//! QM Fast Path — Rust hot path for real-time trading.
//!
//! Modules:
//! - `features`: Intra-bar feature computation (port of IntraBarFeatureCalculator)
//! - `orderbook`: L2 orderbook management with delta application
//!
//! All modules are exposed to Python via PyO3.

#![forbid(unsafe_code)]

mod features;
mod orderbook;

use pyo3::prelude::*;

/// QM Fast Path Python module.
#[pymodule]
fn qm_fast(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<features::FeatureCalculator>()?;
    m.add_class::<features::RingBuffer>()?;
    m.add_class::<orderbook::L2Orderbook>()?;
    Ok(())
}
