"""Live feature computation with automatic Rust/Python fallback.

Uses the Rust FeatureCalculator from qm_fast when available (< 0.01ms).
Falls back to Python IntraBarFeatureCalculator if Rust module not built.

Usage:
    from qm.features.live_cache import get_feature_calculator
    calc = get_feature_calculator()  # Rust or Python, transparent
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from qm_fast import FeatureCalculator as RustFeatureCalculator
    from qm_fast import L2Orderbook as RustL2Orderbook
    from qm_fast import RingBuffer as RustRingBuffer

    RUST_AVAILABLE = True
    logger.info("qm_fast Rust module loaded — using Rust hot path")
except ImportError:
    RUST_AVAILABLE = False
    logger.info("qm_fast not available — using Python fallback")


def get_feature_calculator():
    """Return the best available feature calculator.

    Returns Rust FeatureCalculator if qm_fast is installed,
    otherwise returns Python IntraBarFeatureCalculator.
    """
    if RUST_AVAILABLE:
        return RustFeatureCalculator()

    from qm.features.intrabar import IntraBarFeatureCalculator
    return IntraBarFeatureCalculator()


def get_orderbook():
    """Return the best available orderbook implementation."""
    if RUST_AVAILABLE:
        return RustL2Orderbook()
    return None  # no Python fallback for orderbook


def get_ring_buffer(capacity: int):
    """Return Rust RingBuffer if available."""
    if RUST_AVAILABLE:
        return RustRingBuffer(capacity)
    return None
