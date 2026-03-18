"""Tests for RegimeFeatures group (3 features for market regime detection)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl

from qm.features.groups.regime import RegimeFeatures

_VOL_COL = "realized_vol_10"

ALL_REGIME_FEATURES = [
    "regime_vol_state",
    "regime_vol_zscore",
    "regime_trend_state",
]


def _make_bars_with_vol(n: int = 200) -> pl.DataFrame:
    """Create OHLCV bars with realized_vol_10 column."""
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
        _VOL_COL: np.abs(rng.randn(n) * 0.01 + 0.02),
    })


def _make_plain_bars(n: int = 30) -> pl.DataFrame:
    """Create OHLCV bars WITHOUT vol column."""
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


class TestRegimeFeatures:
    """Test suite for RegimeFeatures group."""

    def test_graceful_noop_without_vol_column(self) -> None:
        """Should return bars unchanged when vol column is absent."""
        calc = RegimeFeatures()
        df = _make_plain_bars()
        result = calc.compute(df)

        for feat in ALL_REGIME_FEATURES:
            assert feat not in result.columns, f"Unexpected feature: {feat}"
        assert "close" in result.columns
        assert len(result) == len(df)

    def test_all_features_present(self) -> None:
        """All 3 regime features should be produced when vol exists."""
        calc = RegimeFeatures()
        df = _make_bars_with_vol()
        result = calc.compute(df)

        for feat in ALL_REGIME_FEATURES:
            assert feat in result.columns, f"Missing feature: {feat}"

    def test_vol_state_values(self) -> None:
        """regime_vol_state should only contain values 0, 1, 2, 3."""
        calc = RegimeFeatures()
        df = _make_bars_with_vol(300)
        result = calc.compute(df)

        states = result["regime_vol_state"].drop_nulls().unique().to_list()
        for s in states:
            assert s in [0, 1, 2, 3], f"Unexpected state: {s}"

    def test_vol_state_low_when_vol_low(self) -> None:
        """regime_vol_state should be 0 (low) when vol is at the bottom."""
        calc = RegimeFeatures()
        n = 200
        base = datetime(2026, 1, 1, tzinfo=UTC)
        # Vol starts high, then drops to very low
        vol = np.concatenate([
            np.full(150, 0.05),  # high vol period
            np.full(50, 0.001),  # very low vol
        ])
        rng = np.random.RandomState(42)
        df = pl.DataFrame({
            "time": [base + timedelta(minutes=5 * i) for i in range(n)],
            "open": rng.uniform(99, 101, n),
            "high": rng.uniform(100, 102, n),
            "low": rng.uniform(98, 100, n),
            "close": rng.uniform(99, 101, n),
            "volume": rng.uniform(100, 500, n),
            _VOL_COL: vol,
        })
        result = calc.compute(df)
        # Last rows should be low regime (0)
        assert result["regime_vol_state"][-1] == 0

    def test_vol_state_crisis_when_vol_extreme(self) -> None:
        """regime_vol_state should be 3 (crisis) when vol spikes."""
        calc = RegimeFeatures()
        n = 200
        base = datetime(2026, 1, 1, tzinfo=UTC)
        # Vol is normal then spikes
        vol = np.concatenate([
            np.full(180, 0.01),  # normal
            np.full(20, 0.10),   # crisis spike
        ])
        rng = np.random.RandomState(42)
        df = pl.DataFrame({
            "time": [base + timedelta(minutes=5 * i) for i in range(n)],
            "open": rng.uniform(99, 101, n),
            "high": rng.uniform(100, 102, n),
            "low": rng.uniform(98, 100, n),
            "close": rng.uniform(99, 101, n),
            "volume": rng.uniform(100, 500, n),
            _VOL_COL: vol,
        })
        result = calc.compute(df)
        # Last row should be crisis (3) or high (2)
        assert result["regime_vol_state"][-1] >= 2

    def test_vol_zscore_centered(self) -> None:
        """regime_vol_zscore should be roughly centered around 0."""
        calc = RegimeFeatures()
        df = _make_bars_with_vol(500)
        result = calc.compute(df)

        zscore = result["regime_vol_zscore"].drop_nulls()
        assert abs(zscore.mean()) < 1.5
        assert zscore.std() > 0.1

    def test_trend_state_values(self) -> None:
        """regime_trend_state should only contain -1, 0, or 1."""
        calc = RegimeFeatures()
        df = _make_bars_with_vol()
        result = calc.compute(df)

        states = result["regime_trend_state"].drop_nulls().unique().to_list()
        for s in states:
            assert s in [-1, 0, 1], f"Unexpected trend state: {s}"

    def test_trend_state_up_in_uptrend(self) -> None:
        """regime_trend_state should be 1 during a strong uptrend."""
        calc = RegimeFeatures()
        n = 50
        base = datetime(2026, 1, 1, tzinfo=UTC)
        # Clear uptrend: price goes from 100 to 150
        close = np.linspace(100, 150, n)
        df = pl.DataFrame({
            "time": [base + timedelta(minutes=5 * i) for i in range(n)],
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": [500.0] * n,
            _VOL_COL: [0.02] * n,
        })
        result = calc.compute(df)
        # Last row should detect uptrend
        assert result["regime_trend_state"][-1] == 1

    def test_trend_state_down_in_downtrend(self) -> None:
        """regime_trend_state should be -1 during a strong downtrend."""
        calc = RegimeFeatures()
        n = 50
        base = datetime(2026, 1, 1, tzinfo=UTC)
        close = np.linspace(150, 100, n)
        df = pl.DataFrame({
            "time": [base + timedelta(minutes=5 * i) for i in range(n)],
            "open": close + 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": [500.0] * n,
            _VOL_COL: [0.02] * n,
        })
        result = calc.compute(df)
        assert result["regime_trend_state"][-1] == -1

    def test_null_vol_handling(self) -> None:
        """Nulls in vol column should not crash computation."""
        calc = RegimeFeatures()
        df = _make_bars_with_vol(50)
        mask = pl.Series([True] * 25 + [False] * 25)
        df = df.with_columns(
            pl.when(mask).then(pl.col(_VOL_COL)).otherwise(None)
            .alias(_VOL_COL),
        )
        result = calc.compute(df)

        for feat in ALL_REGIME_FEATURES:
            assert feat in result.columns
        assert len(result) == 50

    def test_single_row(self) -> None:
        """Should handle single-row DataFrames without crashing."""
        calc = RegimeFeatures()
        df = pl.DataFrame({
            "time": [datetime(2026, 1, 1, tzinfo=UTC)],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.0],
            "volume": [500.0],
            _VOL_COL: [0.02],
        })
        result = calc.compute(df)
        assert len(result) == 1

    def test_empty_dataframe(self) -> None:
        """Should handle empty DataFrame gracefully."""
        calc = RegimeFeatures()
        df = pl.DataFrame({
            "time": pl.Series([], dtype=pl.Datetime("us", "UTC")),
            "open": pl.Series([], dtype=pl.Float64),
            "high": pl.Series([], dtype=pl.Float64),
            "low": pl.Series([], dtype=pl.Float64),
            "close": pl.Series([], dtype=pl.Float64),
            "volume": pl.Series([], dtype=pl.Float64),
            _VOL_COL: pl.Series([], dtype=pl.Float64),
        })
        result = calc.compute(df)
        assert result.is_empty()

    def test_specs_count(self) -> None:
        """Should register exactly 3 feature specs."""
        calc = RegimeFeatures()
        specs = calc.specs()
        assert len(specs) == 3
        spec_names = {s.name for s in specs}
        assert spec_names == set(ALL_REGIME_FEATURES)

    def test_no_rows_dropped(self) -> None:
        """Feature computation should never drop rows."""
        calc = RegimeFeatures()
        df = _make_bars_with_vol(150)
        result = calc.compute(df)
        assert len(result) == 150
