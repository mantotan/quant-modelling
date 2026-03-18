"""Tests for InteractionFeatures group (8 alpha × TA cross-products)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from qm.features.groups.interactions import INTERACTION_PAIRS, InteractionFeatures


def _make_bars_with_all_inputs(n: int = 50) -> pl.DataFrame:
    """Create bars with all possible interaction input columns."""
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
        # Funding features (from unit 3)
        "funding_rate": rng.uniform(-0.001, 0.001, n),
        "funding_rate_pctile": rng.uniform(0, 1, n),
        # TA features (from base pipeline)
        "rsi_14": rng.uniform(20, 80, n),
        "realized_vol_10": rng.uniform(0.01, 0.05, n),
        "roc_5": rng.uniform(-0.02, 0.02, n),
        "return_5": rng.uniform(-0.03, 0.03, n),
        # Liquidation features (from unit 4)
        "oi_price_divergence": rng.uniform(-0.01, 0.01, n),
        "leverage_proxy": rng.uniform(50, 200, n),
        "liquidation_proximity": rng.randn(n),
        # Regime features (from unit 5)
        "regime_vol_state": rng.choice([0, 1, 2, 3], n),
        # Cross-asset (from CrossAssetPipeline)
        "btc_return_1": rng.uniform(-0.01, 0.01, n),
        # Options IV (from unit 12 — future)
        "iv_skew": rng.uniform(-0.1, 0.1, n),
        # Polymarket (from unit 13 — future)
        "pm_order_imbalance": rng.uniform(-1, 1, n),
    })


def _make_partial_bars(n: int = 30) -> pl.DataFrame:
    """Create bars with only some interaction inputs (funding + TA only)."""
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
        "funding_rate": rng.uniform(-0.001, 0.001, n),
        "funding_rate_pctile": rng.uniform(0, 1, n),
        "rsi_14": rng.uniform(20, 80, n),
        "realized_vol_10": rng.uniform(0.01, 0.05, n),
    })


def _make_plain_bars(n: int = 20) -> pl.DataFrame:
    """Create plain OHLCV bars without any interaction inputs."""
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


class TestInteractionFeatures:
    """Test suite for InteractionFeatures group."""

    def test_graceful_noop_no_inputs(self) -> None:
        """Should return bars unchanged when no interaction inputs exist."""
        calc = InteractionFeatures()
        df = _make_plain_bars()
        result = calc.compute(df)

        for name, _, _ in INTERACTION_PAIRS:
            assert name not in result.columns
        assert len(result) == len(df)

    def test_all_features_with_all_inputs(self) -> None:
        """All 8 interactions should be computed when all inputs exist."""
        calc = InteractionFeatures()
        df = _make_bars_with_all_inputs()
        result = calc.compute(df)

        for name, _, _ in INTERACTION_PAIRS:
            assert name in result.columns, f"Missing interaction: {name}"

    def test_partial_inputs_only_available_pairs(self) -> None:
        """Only pairs with both inputs present should be computed."""
        calc = InteractionFeatures()
        df = _make_partial_bars()
        result = calc.compute(df)

        # These should be present (both inputs available)
        assert "funding_x_rsi" in result.columns
        assert "funding_x_vol" in result.columns

        # These should be absent (missing one or both inputs)
        assert "oi_div_x_momentum" not in result.columns
        assert "leverage_x_proximity" not in result.columns
        assert "iv_skew_x_return" not in result.columns
        assert "pm_imbalance_x_vol" not in result.columns

    def test_funding_x_rsi_arithmetic(self) -> None:
        """funding_x_rsi should equal funding_rate_pctile * rsi_14."""
        calc = InteractionFeatures()
        df = _make_bars_with_all_inputs()
        result = calc.compute(df)

        expected = df["funding_rate_pctile"] * df["rsi_14"]
        for i in range(len(result)):
            assert result["funding_x_rsi"][i] == pytest.approx(
                expected[i], abs=1e-10
            )

    def test_leverage_x_proximity_arithmetic(self) -> None:
        """leverage_x_proximity = leverage_proxy * liquidation_proximity."""
        calc = InteractionFeatures()
        df = _make_bars_with_all_inputs()
        result = calc.compute(df)

        expected = df["leverage_proxy"] * df["liquidation_proximity"]
        for i in range(len(result)):
            assert result["leverage_x_proximity"][i] == pytest.approx(
                expected[i], abs=1e-10
            )

    def test_regime_x_funding_includes_zero(self) -> None:
        """regime_x_funding should be 0 when regime_vol_state is 0 (low)."""
        calc = InteractionFeatures()
        df = pl.DataFrame({
            "time": [datetime(2026, 1, 1, h, tzinfo=UTC) for h in range(3)],
            "open": [100.0] * 3,
            "high": [101.0] * 3,
            "low": [99.0] * 3,
            "close": [100.0] * 3,
            "volume": [500.0] * 3,
            "regime_vol_state": [0, 2, 3],
            "funding_rate": [0.001, 0.001, 0.001],
        })
        result = calc.compute(df)

        assert result["regime_x_funding"][0] == pytest.approx(0.0, abs=1e-10)
        assert result["regime_x_funding"][1] == pytest.approx(0.002, abs=1e-10)
        assert result["regime_x_funding"][2] == pytest.approx(0.003, abs=1e-10)

    def test_null_handling(self) -> None:
        """Nulls in inputs should produce null outputs, not crash."""
        calc = InteractionFeatures()
        df = _make_bars_with_all_inputs(20)
        mask = pl.Series([True] * 10 + [False] * 10)
        df = df.with_columns(
            pl.when(mask).then(pl.col("funding_rate_pctile")).otherwise(None)
            .alias("funding_rate_pctile"),
        )
        result = calc.compute(df)

        assert "funding_x_rsi" in result.columns
        assert len(result) == 20
        # Last 10 should be null
        assert result["funding_x_rsi"][15] is None

    def test_single_row(self) -> None:
        """Should handle single-row DataFrames."""
        calc = InteractionFeatures()
        df = _make_bars_with_all_inputs(1)
        result = calc.compute(df)
        assert len(result) == 1
        for name, _, _ in INTERACTION_PAIRS:
            assert name in result.columns

    def test_empty_dataframe(self) -> None:
        """Should handle empty DataFrame gracefully."""
        calc = InteractionFeatures()
        df = pl.DataFrame({
            "time": pl.Series([], dtype=pl.Datetime("us", "UTC")),
            "close": pl.Series([], dtype=pl.Float64),
            "funding_rate_pctile": pl.Series([], dtype=pl.Float64),
            "rsi_14": pl.Series([], dtype=pl.Float64),
        })
        result = calc.compute(df)
        assert result.is_empty()
        assert "funding_x_rsi" in result.columns

    def test_specs_count(self) -> None:
        """Should register exactly 8 feature specs."""
        calc = InteractionFeatures()
        specs = calc.specs()
        assert len(specs) == 8

    def test_no_rows_dropped(self) -> None:
        """Feature computation should never drop rows."""
        calc = InteractionFeatures()
        df = _make_bars_with_all_inputs(100)
        result = calc.compute(df)
        assert len(result) == 100

    def test_interaction_pairs_constant(self) -> None:
        """INTERACTION_PAIRS should have 8 entries."""
        assert len(INTERACTION_PAIRS) == 8
