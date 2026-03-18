"""Tests for PolymarketMicroFeatures group (4 features)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from qm.features.groups.polymarket import PolymarketMicroFeatures

_MID_UP = "polymarket_mid_up"
_MID_DOWN = "polymarket_mid_down"
_VOLUME = "polymarket_volume"

ALL_PM_FEATURES = [
    "pm_bid_ask_spread",
    "pm_order_imbalance",
    "pm_trade_flow",
    "pm_mid_momentum",
]


def _make_bars_with_pm(n: int = 30) -> pl.DataFrame:
    """Create OHLCV bars with Polymarket snapshot columns."""
    rng = np.random.RandomState(42)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    times = [base + timedelta(minutes=5 * i) for i in range(n)]
    mid_up = rng.uniform(0.40, 0.60, n)

    return pl.DataFrame({
        "time": times,
        "open": rng.uniform(99, 101, n),
        "high": rng.uniform(100, 102, n),
        "low": rng.uniform(98, 100, n),
        "close": rng.uniform(99, 101, n),
        "volume": rng.uniform(100, 500, n),
        _MID_UP: mid_up,
        _MID_DOWN: 1.0 - mid_up + rng.uniform(-0.02, 0.02, n),  # ~spread
        _VOLUME: rng.uniform(1000, 10000, n),
    })


def _make_plain_bars(n: int = 20) -> pl.DataFrame:
    """Create OHLCV bars WITHOUT Polymarket columns."""
    rng = np.random.RandomState(42)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    times = [base + timedelta(minutes=5 * i) for i in range(n)]

    return pl.DataFrame({
        "time": times,
        "open": rng.uniform(99, 101, n),
        "high": rng.uniform(100, 102, n),
        "low": rng.uniform(98, 100, n),
        "close": rng.uniform(99, 101, n),
        "volume": rng.uniform(100, 500, n),
    })


class TestPolymarketMicroFeatures:
    def test_graceful_noop_without_pm_columns(self) -> None:
        calc = PolymarketMicroFeatures()
        df = _make_plain_bars()
        result = calc.compute(df)
        for feat in ALL_PM_FEATURES:
            assert feat not in result.columns
        assert len(result) == len(df)

    def test_all_features_present(self) -> None:
        calc = PolymarketMicroFeatures()
        df = _make_bars_with_pm()
        result = calc.compute(df)
        for feat in ALL_PM_FEATURES:
            assert feat in result.columns, f"Missing: {feat}"

    def test_spread_computation(self) -> None:
        """Spread should be |1 - mid_up - mid_down|."""
        calc = PolymarketMicroFeatures()
        df = pl.DataFrame({
            "time": [datetime(2026, 1, 1, h, tzinfo=UTC) for h in range(3)],
            "open": [100.0] * 3,
            "high": [101.0] * 3,
            "low": [99.0] * 3,
            "close": [100.0] * 3,
            "volume": [500.0] * 3,
            _MID_UP: [0.55, 0.50, 0.60],
            _MID_DOWN: [0.45, 0.50, 0.38],
            _VOLUME: [5000.0] * 3,
        })
        result = calc.compute(df)
        # |1 - 0.55 - 0.45| = 0.0
        assert result["pm_bid_ask_spread"][0] == pytest.approx(0.0, abs=1e-10)
        # |1 - 0.50 - 0.50| = 0.0
        assert result["pm_bid_ask_spread"][1] == pytest.approx(0.0, abs=1e-10)
        # |1 - 0.60 - 0.38| = 0.02
        assert result["pm_bid_ask_spread"][2] == pytest.approx(0.02, abs=1e-10)

    def test_order_imbalance(self) -> None:
        """pm_order_imbalance = mid_up - 0.5."""
        calc = PolymarketMicroFeatures()
        df = pl.DataFrame({
            "time": [datetime(2026, 1, 1, h, tzinfo=UTC) for h in range(3)],
            "open": [100.0] * 3,
            "high": [101.0] * 3,
            "low": [99.0] * 3,
            "close": [100.0] * 3,
            "volume": [500.0] * 3,
            _MID_UP: [0.55, 0.50, 0.40],
            _MID_DOWN: [0.45, 0.50, 0.60],
            _VOLUME: [5000.0] * 3,
        })
        result = calc.compute(df)
        assert result["pm_order_imbalance"][0] == pytest.approx(0.05, abs=1e-10)
        assert result["pm_order_imbalance"][1] == pytest.approx(0.0, abs=1e-10)
        assert result["pm_order_imbalance"][2] == pytest.approx(-0.10, abs=1e-10)

    def test_trade_flow_is_pct_change(self) -> None:
        """pm_trade_flow should be volume pct_change."""
        calc = PolymarketMicroFeatures()
        df = _make_bars_with_pm()
        result = calc.compute(df)
        assert "pm_trade_flow" in result.columns
        # First value should be null (no previous)
        assert result["pm_trade_flow"][0] is None

    def test_mid_momentum(self) -> None:
        """pm_mid_momentum should track rolling mid_up changes."""
        calc = PolymarketMicroFeatures()
        df = _make_bars_with_pm(20)
        result = calc.compute(df)
        assert "pm_mid_momentum" in result.columns
        assert len(result) == 20

    def test_null_handling(self) -> None:
        calc = PolymarketMicroFeatures()
        df = _make_bars_with_pm(20)
        mask = pl.Series([True] * 10 + [False] * 10)
        df = df.with_columns(
            pl.when(mask).then(pl.col(_MID_UP)).otherwise(None)
            .alias(_MID_UP),
        )
        result = calc.compute(df)
        for feat in ALL_PM_FEATURES:
            assert feat in result.columns
        assert len(result) == 20

    def test_single_row(self) -> None:
        calc = PolymarketMicroFeatures()
        df = pl.DataFrame({
            "time": [datetime(2026, 1, 1, tzinfo=UTC)],
            "open": [100.0], "high": [101.0], "low": [99.0],
            "close": [100.0], "volume": [500.0],
            _MID_UP: [0.55],
            _MID_DOWN: [0.45],
            _VOLUME: [5000.0],
        })
        result = calc.compute(df)
        assert len(result) == 1

    def test_empty_dataframe(self) -> None:
        calc = PolymarketMicroFeatures()
        df = pl.DataFrame({
            "time": pl.Series([], dtype=pl.Datetime("us", "UTC")),
            "close": pl.Series([], dtype=pl.Float64),
            _MID_UP: pl.Series([], dtype=pl.Float64),
            _MID_DOWN: pl.Series([], dtype=pl.Float64),
            _VOLUME: pl.Series([], dtype=pl.Float64),
        })
        result = calc.compute(df)
        assert result.is_empty()

    def test_specs_count(self) -> None:
        calc = PolymarketMicroFeatures()
        specs = calc.specs()
        assert len(specs) == 4

    def test_no_rows_dropped(self) -> None:
        calc = PolymarketMicroFeatures()
        df = _make_bars_with_pm(50)
        result = calc.compute(df)
        assert len(result) == 50
