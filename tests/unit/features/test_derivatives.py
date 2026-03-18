"""Tests for derivatives feature computation."""

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest

from qm.features.groups.derivatives import DerivativesFeatures


def _make_bars_with_taker(n: int = 50) -> pl.DataFrame:
    """Create bars DataFrame with taker_buy_volume column."""
    rng = np.random.RandomState(42)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    times = [base + timedelta(minutes=5 * i) for i in range(n)]
    volume = rng.uniform(100, 1000, n)

    return pl.DataFrame({
        "time": times,
        "open": rng.uniform(90, 110, n),
        "high": rng.uniform(100, 120, n),
        "low": rng.uniform(80, 100, n),
        "close": rng.uniform(90, 110, n),
        "volume": volume,
        "taker_buy_volume": volume * rng.uniform(0.3, 0.7, n),
    })


def _make_bars_with_metrics(n: int = 50) -> pl.DataFrame:
    """Create bars DataFrame with metrics columns joined."""
    rng = np.random.RandomState(42)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    times = [base + timedelta(minutes=5 * i) for i in range(n)]

    return pl.DataFrame({
        "time": times,
        "open": rng.uniform(90, 110, n),
        "high": rng.uniform(100, 120, n),
        "low": rng.uniform(80, 100, n),
        "close": rng.uniform(90, 110, n),
        "volume": rng.uniform(100, 1000, n),
        "sum_open_interest": 50000.0 + np.cumsum(rng.randn(n) * 100),
        "sum_open_interest_value": rng.uniform(1e9, 5e9, n),
        "count_toptrader_long_short_ratio": rng.uniform(1.5, 2.5, n),
        "sum_toptrader_long_short_ratio": rng.uniform(1.0, 1.5, n),
        "count_long_short_ratio": rng.uniform(1.5, 2.0, n),
        "sum_taker_long_short_vol_ratio": rng.uniform(0.5, 2.0, n),
    })


class TestDerivativesFeatures:
    def test_taker_buy_ratio(self):
        """taker_buy_ratio should equal taker_buy_volume / volume."""
        calc = DerivativesFeatures()
        df = _make_bars_with_taker()

        result = calc.compute(df)
        assert "taker_buy_ratio" in result.columns

        # Verify arithmetic
        expected = df["taker_buy_volume"] / (df["volume"] + 1e-10)
        for i in range(len(result)):
            assert result["taker_buy_ratio"][i] == pytest.approx(expected[i], abs=1e-8)

    def test_graceful_noop_without_columns(self):
        """Should not crash when metrics/taker columns are absent."""
        calc = DerivativesFeatures()
        df = pl.DataFrame({
            "time": [datetime(2026, 1, 1, tzinfo=timezone.utc)],
            "open": [100.0], "high": [101.0], "low": [99.0],
            "close": [100.5], "volume": [500.0],
        })

        result = calc.compute(df)

        # No derivatives columns should be added
        assert "taker_buy_ratio" not in result.columns
        assert "oi_change" not in result.columns
        assert "ls_ratio" not in result.columns
        # Original columns preserved
        assert "close" in result.columns

    def test_oi_change(self):
        """oi_change should be pct_change of sum_open_interest."""
        calc = DerivativesFeatures()
        df = _make_bars_with_metrics()
        result = calc.compute(df)

        assert "oi_change" in result.columns
        assert "oi_change_5" in result.columns
        # First value should be null (no previous bar)
        assert result["oi_change"][0] is None

    def test_top_ls_divergence(self):
        """top_ls_divergence should be top_trader - retail L/S ratio."""
        calc = DerivativesFeatures()
        df = _make_bars_with_metrics()
        result = calc.compute(df)

        assert "top_ls_divergence" in result.columns
        expected = df["sum_toptrader_long_short_ratio"] - df["count_long_short_ratio"]
        for i in range(len(result)):
            assert result["top_ls_divergence"][i] == pytest.approx(expected[i], abs=1e-8)

    def test_null_handling(self):
        """Nulls in metrics columns should not crash computation."""
        calc = DerivativesFeatures()
        df = _make_bars_with_metrics(20)

        # Introduce nulls (simulating left join gaps)
        mask = pl.Series([True] * 10 + [False] * 10)
        df = df.with_columns(
            pl.when(mask).then(pl.col("sum_open_interest")).otherwise(None)
            .alias("sum_open_interest")
        )

        result = calc.compute(df)
        assert "oi_change" in result.columns
        assert len(result) == 20  # No rows dropped

    def test_all_metrics_features_present(self):
        """All 8 derivatives features should be present when all columns exist."""
        calc = DerivativesFeatures()
        df = _make_bars_with_metrics()
        df = df.with_columns(
            (pl.col("volume") * 0.5).alias("taker_buy_volume"),
        )
        result = calc.compute(df)

        expected_features = [
            "taker_buy_ratio", "oi_change", "oi_change_5",
            "ls_ratio", "ls_ratio_change", "top_ls_ratio",
            "top_ls_divergence", "taker_ls_vol_ratio",
        ]
        for feat in expected_features:
            assert feat in result.columns, f"Missing feature: {feat}"
