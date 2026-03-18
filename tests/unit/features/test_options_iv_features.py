"""Tests for OptionsIVFeatures group (5 features from Deribit IV index)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from qm.features.groups.options_iv import OptionsIVFeatures

_SRC_COL = "options_iv_iv_index"

ALL_IV_FEATURES = [
    "iv_atm",
    "iv_skew",
    "iv_term_spread",
    "iv_change_1h",
    "iv_percentile_30d",
]


def _make_bars_with_iv(n: int = 50) -> pl.DataFrame:
    """Create OHLCV bars with IV index and realised vol columns."""
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
        _SRC_COL: np.abs(rng.randn(n) * 0.1 + 0.6),  # ~60% IV
        "realized_vol_10": np.abs(rng.randn(n) * 0.005 + 0.02),
    })


def _make_plain_bars(n: int = 30) -> pl.DataFrame:
    """Create OHLCV bars WITHOUT IV column."""
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


class TestOptionsIVFeatures:
    def test_graceful_noop_without_iv_column(self) -> None:
        calc = OptionsIVFeatures()
        df = _make_plain_bars()
        result = calc.compute(df)
        for feat in ALL_IV_FEATURES:
            assert feat not in result.columns
        assert len(result) == len(df)

    def test_all_features_present(self) -> None:
        calc = OptionsIVFeatures()
        df = _make_bars_with_iv()
        result = calc.compute(df)
        for feat in ALL_IV_FEATURES:
            assert feat in result.columns, f"Missing: {feat}"

    def test_iv_atm_passthrough(self) -> None:
        calc = OptionsIVFeatures()
        df = _make_bars_with_iv()
        result = calc.compute(df)
        for i in range(len(result)):
            assert result["iv_atm"][i] == pytest.approx(
                result[_SRC_COL][i], abs=1e-12
            )

    def test_iv_skew_is_iv_minus_rvol(self) -> None:
        calc = OptionsIVFeatures()
        df = _make_bars_with_iv()
        result = calc.compute(df)
        for i in range(len(result)):
            expected = df[_SRC_COL][i] - df["realized_vol_10"][i]
            assert result["iv_skew"][i] == pytest.approx(expected, abs=1e-10)

    def test_iv_skew_null_without_rvol(self) -> None:
        """iv_skew should be null when realized_vol_10 is absent."""
        calc = OptionsIVFeatures()
        df = _make_bars_with_iv().drop("realized_vol_10")
        result = calc.compute(df)
        assert "iv_skew" in result.columns
        assert result["iv_skew"][0] is None

    def test_iv_percentile_range(self) -> None:
        calc = OptionsIVFeatures()
        df = _make_bars_with_iv(200)
        result = calc.compute(df)
        pctile = result["iv_percentile_30d"].drop_nulls()
        assert pctile.min() >= -0.01
        assert pctile.max() <= 1.01

    def test_null_iv_handling(self) -> None:
        calc = OptionsIVFeatures()
        df = _make_bars_with_iv(30)
        mask = pl.Series([True] * 15 + [False] * 15)
        df = df.with_columns(
            pl.when(mask).then(pl.col(_SRC_COL)).otherwise(None)
            .alias(_SRC_COL),
        )
        result = calc.compute(df)
        for feat in ALL_IV_FEATURES:
            assert feat in result.columns
        assert len(result) == 30

    def test_single_row(self) -> None:
        calc = OptionsIVFeatures()
        df = pl.DataFrame({
            "time": [datetime(2026, 1, 1, tzinfo=UTC)],
            "open": [100.0], "high": [101.0], "low": [99.0],
            "close": [100.0], "volume": [500.0],
            _SRC_COL: [0.65],
            "realized_vol_10": [0.02],
        })
        result = calc.compute(df)
        assert len(result) == 1
        assert result["iv_atm"][0] == pytest.approx(0.65, abs=1e-10)

    def test_empty_dataframe(self) -> None:
        calc = OptionsIVFeatures()
        df = pl.DataFrame({
            "time": pl.Series([], dtype=pl.Datetime("us", "UTC")),
            "close": pl.Series([], dtype=pl.Float64),
            _SRC_COL: pl.Series([], dtype=pl.Float64),
            "realized_vol_10": pl.Series([], dtype=pl.Float64),
        })
        result = calc.compute(df)
        assert result.is_empty()

    def test_specs_count(self) -> None:
        calc = OptionsIVFeatures()
        specs = calc.specs()
        assert len(specs) == 5

    def test_no_rows_dropped(self) -> None:
        calc = OptionsIVFeatures()
        df = _make_bars_with_iv(100)
        result = calc.compute(df)
        assert len(result) == 100
