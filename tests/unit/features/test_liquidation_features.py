"""Tests for LiquidationFeatures group (4 features from OI + price data)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl

from qm.features.groups.liquidation import LiquidationFeatures

_OI_COL = "sum_open_interest"

ALL_LIQUIDATION_FEATURES = [
    "liquidation_proximity",
    "oi_price_divergence",
    "oi_momentum",
    "leverage_proxy",
]


def _make_bars_with_oi(n: int = 50) -> pl.DataFrame:
    """Create OHLCV bars with sum_open_interest column."""
    rng = np.random.RandomState(42)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    times = [base + timedelta(minutes=5 * i) for i in range(n)]
    close = 100.0 + np.cumsum(rng.randn(n) * 0.5)

    return pl.DataFrame({
        "time": times,
        "open": close - rng.uniform(0, 1, n),
        "high": close + rng.uniform(0, 2, n),
        "low": close - rng.uniform(0, 2, n),
        "close": close,
        "volume": rng.uniform(100, 1000, n),
        _OI_COL: 50000.0 + np.cumsum(rng.randn(n) * 100),
    })


def _make_plain_bars(n: int = 30) -> pl.DataFrame:
    """Create OHLCV bars WITHOUT OI column."""
    rng = np.random.RandomState(42)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    times = [base + timedelta(minutes=5 * i) for i in range(n)]

    return pl.DataFrame({
        "time": times,
        "open": rng.uniform(90, 110, n),
        "high": rng.uniform(100, 120, n),
        "low": rng.uniform(80, 100, n),
        "close": rng.uniform(90, 110, n),
        "volume": rng.uniform(100, 1000, n),
    })


class TestLiquidationFeatures:
    """Test suite for LiquidationFeatures group."""

    def test_graceful_noop_without_oi_column(self) -> None:
        """Should return bars unchanged when OI column is absent."""
        calc = LiquidationFeatures()
        df = _make_plain_bars()
        result = calc.compute(df)

        for feat in ALL_LIQUIDATION_FEATURES:
            assert feat not in result.columns, f"Unexpected feature: {feat}"
        assert "close" in result.columns
        assert len(result) == len(df)

    def test_all_features_present(self) -> None:
        """All 4 liquidation features should be produced when OI exists."""
        calc = LiquidationFeatures()
        df = _make_bars_with_oi()
        result = calc.compute(df)

        for feat in ALL_LIQUIDATION_FEATURES:
            assert feat in result.columns, f"Missing feature: {feat}"

    def test_liquidation_proximity_is_zscore(self) -> None:
        """liquidation_proximity should behave like a z-score (mean ~0)."""
        calc = LiquidationFeatures()
        df = _make_bars_with_oi(200)
        result = calc.compute(df)

        prox = result["liquidation_proximity"].drop_nulls()
        # Z-scores should be roughly centered around 0 with std ~1
        assert abs(prox.mean()) < 1.0
        assert prox.std() > 0.1  # should have variance

    def test_oi_price_divergence_sign(self) -> None:
        """Rising OI + falling price should produce positive divergence."""
        calc = LiquidationFeatures()
        # Construct scenario: price drops, OI rises
        df = pl.DataFrame({
            "time": [datetime(2026, 1, 1, h, tzinfo=UTC) for h in range(5)],
            "open": [100.0, 99.0, 98.0, 97.0, 96.0],
            "high": [101.0, 100.0, 99.0, 98.0, 97.0],
            "low": [99.0, 98.0, 97.0, 96.0, 95.0],
            "close": [100.0, 99.0, 98.0, 97.0, 96.0],
            "volume": [500.0] * 5,
            _OI_COL: [50000.0, 51000.0, 52000.0, 53000.0, 54000.0],
        })
        result = calc.compute(df)

        # OI rising ~2%/bar while price falling ~1%/bar → divergence > 0
        div = result["oi_price_divergence"]
        # Index 1+: OI pct_change positive, price pct_change negative → diff > 0
        assert div[1] is not None
        assert div[1] > 0
        assert div[2] > 0

    def test_oi_momentum_detects_acceleration(self) -> None:
        """oi_momentum should be positive when OI growth accelerates."""
        calc = LiquidationFeatures()
        # OI grows at increasing rate
        oi_vals = [50000.0 + i**2 * 10 for i in range(30)]
        rng = np.random.RandomState(42)
        df = pl.DataFrame({
            "time": [
                datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=5 * i)
                for i in range(30)
            ],
            "open": rng.uniform(99, 101, 30),
            "high": rng.uniform(100, 102, 30),
            "low": rng.uniform(98, 100, 30),
            "close": rng.uniform(99, 101, 30),
            "volume": rng.uniform(100, 500, 30),
            _OI_COL: oi_vals,
        })
        result = calc.compute(df)

        mom = result["oi_momentum"].drop_nulls()
        # With accelerating OI, later values of momentum should be positive
        assert mom[-1] > 0

    def test_leverage_proxy_positive(self) -> None:
        """leverage_proxy should always be non-negative (OI/volume ≥ 0)."""
        calc = LiquidationFeatures()
        df = _make_bars_with_oi(100)
        result = calc.compute(df)

        lev = result["leverage_proxy"].drop_nulls()
        assert lev.min() >= 0

    def test_leverage_proxy_high_when_oi_high_volume_low(self) -> None:
        """leverage_proxy should be higher when OI is large relative to volume."""
        calc = LiquidationFeatures()
        # Scenario: high OI, low volume
        df = pl.DataFrame({
            "time": [
                datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=5 * i)
                for i in range(15)
            ],
            "open": [100.0] * 15,
            "high": [101.0] * 15,
            "low": [99.0] * 15,
            "close": [100.0] * 15,
            "volume": [10.0] * 15,  # very low volume
            _OI_COL: [100000.0] * 15,  # very high OI
        })
        result = calc.compute(df)
        # OI/volume = 100000/10 = 10000 — should be a large number
        assert result["leverage_proxy"][-1] > 1000

    def test_null_oi_handling(self) -> None:
        """Nulls in OI should not crash computation."""
        calc = LiquidationFeatures()
        df = _make_bars_with_oi(30)
        mask = pl.Series([True] * 15 + [False] * 15)
        df = df.with_columns(
            pl.when(mask).then(pl.col(_OI_COL)).otherwise(None)
            .alias(_OI_COL),
        )
        result = calc.compute(df)

        for feat in ALL_LIQUIDATION_FEATURES:
            assert feat in result.columns
        assert len(result) == 30

    def test_single_row(self) -> None:
        """Should handle single-row DataFrames without crashing."""
        calc = LiquidationFeatures()
        df = pl.DataFrame({
            "time": [datetime(2026, 1, 1, tzinfo=UTC)],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.0],
            "volume": [500.0],
            _OI_COL: [50000.0],
        })
        result = calc.compute(df)
        assert len(result) == 1
        for feat in ALL_LIQUIDATION_FEATURES:
            assert feat in result.columns

    def test_empty_dataframe(self) -> None:
        """Should handle empty DataFrame gracefully."""
        calc = LiquidationFeatures()
        df = pl.DataFrame({
            "time": pl.Series([], dtype=pl.Datetime("us", "UTC")),
            "open": pl.Series([], dtype=pl.Float64),
            "high": pl.Series([], dtype=pl.Float64),
            "low": pl.Series([], dtype=pl.Float64),
            "close": pl.Series([], dtype=pl.Float64),
            "volume": pl.Series([], dtype=pl.Float64),
            _OI_COL: pl.Series([], dtype=pl.Float64),
        })
        result = calc.compute(df)
        assert result.is_empty()

    def test_specs_count(self) -> None:
        """Should register exactly 4 feature specs."""
        calc = LiquidationFeatures()
        specs = calc.specs()
        assert len(specs) == 4
        spec_names = {s.name for s in specs}
        assert spec_names == set(ALL_LIQUIDATION_FEATURES)

    def test_no_rows_dropped(self) -> None:
        """Feature computation should never drop rows."""
        calc = LiquidationFeatures()
        df = _make_bars_with_oi(100)
        result = calc.compute(df)
        assert len(result) == 100
