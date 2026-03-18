"""Tests for configurable HPO objective function."""

from __future__ import annotations

import pytest

from qm.model.objective import ObjectiveConfig, compute_objective


def _good_metrics() -> dict[str, float]:
    """Metrics representing a good model."""
    return {
        "brier": 0.20,
        "sharpe": 1.5,
        "n_trades": 100,
        "max_dd": 0.10,
        "accuracy": 0.55,
        "total_pnl": 500.0,
        "win_rate": 0.55,
        "avg_edge": 0.05,
    }


def _bad_metrics() -> dict[str, float]:
    """Metrics representing a bad model."""
    return {
        "brier": 0.35,
        "sharpe": -0.5,
        "n_trades": 10,
        "max_dd": 0.45,
        "accuracy": 0.45,
        "total_pnl": -200.0,
        "win_rate": 0.40,
        "avg_edge": -0.02,
    }


class TestObjectiveConfig:
    """Test ObjectiveConfig dataclass."""

    def test_default_primary_brier(self) -> None:
        cfg = ObjectiveConfig()
        assert cfg.primary == "brier"

    def test_sharpe_primary(self) -> None:
        cfg = ObjectiveConfig(primary="sharpe")
        assert cfg.primary == "sharpe"

    def test_invalid_primary_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown primary"):
            ObjectiveConfig(primary="accuracy")

    def test_frozen(self) -> None:
        cfg = ObjectiveConfig()
        with pytest.raises(AttributeError):
            cfg.primary = "sharpe"  # type: ignore[misc]

    def test_custom_thresholds(self) -> None:
        cfg = ObjectiveConfig(
            brier_threshold=0.22,
            min_trades=100,
            max_drawdown_threshold=0.20,
        )
        assert cfg.brier_threshold == 0.22
        assert cfg.min_trades == 100
        assert cfg.max_drawdown_threshold == 0.20


class TestComputeObjectiveBrierPrimary:
    """Test compute_objective with Brier primary."""

    def test_good_model_low_objective(self) -> None:
        """Good metrics should produce a low objective value."""
        metrics = _good_metrics()
        cfg = ObjectiveConfig(primary="brier")
        value = compute_objective(metrics, cfg)
        # Brier=0.20 < threshold=0.25, no penalty
        assert value == pytest.approx(0.20, abs=0.01)

    def test_bad_brier_adds_penalty(self) -> None:
        """Brier above threshold should add penalty."""
        metrics = _good_metrics()
        metrics["brier"] = 0.30
        cfg = ObjectiveConfig(primary="brier", brier_threshold=0.25,
                              brier_penalty_weight=10.0)
        value = compute_objective(metrics, cfg)
        # base=0.30, penalty=(0.30-0.25)*10=0.50 → total=0.80
        assert value == pytest.approx(0.80, abs=0.01)

    def test_low_trades_adds_penalty(self) -> None:
        """Too few trades should add penalty."""
        metrics = _good_metrics()
        metrics["n_trades"] = 25
        cfg = ObjectiveConfig(primary="brier", min_trades=50,
                              trade_penalty_weight=5.0)
        value = compute_objective(metrics, cfg)
        # shortfall = (50-25)/50 = 0.5, penalty = 0.5 * 5 = 2.5
        # base = 0.20, total = 0.20 + 2.5 = 2.70
        assert value == pytest.approx(2.70, abs=0.01)

    def test_high_drawdown_adds_penalty(self) -> None:
        """High drawdown should add penalty."""
        metrics = _good_metrics()
        metrics["max_dd"] = 0.40
        cfg = ObjectiveConfig(primary="brier", max_drawdown_threshold=0.30,
                              drawdown_penalty_weight=5.0)
        value = compute_objective(metrics, cfg)
        # penalty = (0.40-0.30)*5 = 0.50
        # base = 0.20, total = 0.20 + 0.50 = 0.70
        assert value == pytest.approx(0.70, abs=0.01)

    def test_multiple_penalties_stack(self) -> None:
        """Multiple penalty conditions should accumulate."""
        metrics = _bad_metrics()
        cfg = ObjectiveConfig(
            primary="brier",
            brier_threshold=0.25,
            brier_penalty_weight=10.0,
            min_trades=50,
            trade_penalty_weight=5.0,
            max_drawdown_threshold=0.30,
            drawdown_penalty_weight=5.0,
        )
        value = compute_objective(metrics, cfg)
        # base = 0.35
        # brier penalty = (0.35-0.25)*10 = 1.0
        # trade penalty = (50-10)/50 * 5 = 4.0
        # dd penalty = (0.45-0.30)*5 = 0.75
        # total = 0.35 + 1.0 + 4.0 + 0.75 = 6.10
        assert value == pytest.approx(6.10, abs=0.01)


class TestComputeObjectiveSharpePrimary:
    """Test compute_objective with Sharpe primary."""

    def test_good_sharpe_negative_objective(self) -> None:
        """Good Sharpe ratio should produce negative objective (for minimisation)."""
        metrics = _good_metrics()
        cfg = ObjectiveConfig(primary="sharpe")
        value = compute_objective(metrics, cfg)
        # base = -1.5, no penalties → total = -1.5
        assert value == pytest.approx(-1.5, abs=0.01)

    def test_bad_sharpe_positive_objective(self) -> None:
        """Bad (negative) Sharpe should produce positive objective."""
        metrics = _bad_metrics()
        metrics["brier"] = 0.20  # no brier penalty
        metrics["n_trades"] = 100  # no trade penalty
        metrics["max_dd"] = 0.10  # no dd penalty
        cfg = ObjectiveConfig(primary="sharpe")
        value = compute_objective(metrics, cfg)
        # base = -(-0.5) = 0.5
        assert value == pytest.approx(0.5, abs=0.01)

    def test_sharpe_with_brier_penalty(self) -> None:
        """Sharpe primary should still penalise bad Brier."""
        metrics = _good_metrics()
        metrics["brier"] = 0.30
        cfg = ObjectiveConfig(
            primary="sharpe",
            brier_threshold=0.25,
            brier_penalty_weight=10.0,
        )
        value = compute_objective(metrics, cfg)
        # base = -1.5, penalty = (0.30-0.25)*10 = 0.5
        # total = -1.5 + 0.5 = -1.0
        assert value == pytest.approx(-1.0, abs=0.01)

    def test_lower_is_better_for_both(self) -> None:
        """Good model should always have lower objective than bad model."""
        good = compute_objective(_good_metrics(), ObjectiveConfig(primary="sharpe"))
        bad = compute_objective(_bad_metrics(), ObjectiveConfig(primary="sharpe"))
        assert good < bad

        good_b = compute_objective(_good_metrics(), ObjectiveConfig(primary="brier"))
        bad_b = compute_objective(_bad_metrics(), ObjectiveConfig(primary="brier"))
        assert good_b < bad_b


class TestComputeObjectiveDefaults:
    """Test default behavior and edge cases."""

    def test_none_config_uses_brier(self) -> None:
        """Passing None config should use Brier primary defaults."""
        metrics = _good_metrics()
        value = compute_objective(metrics, None)
        default_value = compute_objective(metrics, ObjectiveConfig())
        assert value == default_value

    def test_missing_metrics_keys(self) -> None:
        """Missing metric keys should use safe defaults."""
        metrics: dict[str, float] = {}
        value = compute_objective(metrics, ObjectiveConfig())
        # brier=1.0, n_trades=0, max_dd=0.0
        # base=1.0, brier_penalty=(1.0-0.25)*10=7.5,
        # trade_penalty=(50-0)/50*5=5.0, dd_penalty=0
        assert value == pytest.approx(13.5, abs=0.1)

    def test_zero_trades_no_division_error(self) -> None:
        """Zero trades should not cause division by zero."""
        metrics = _good_metrics()
        metrics["n_trades"] = 0
        cfg = ObjectiveConfig(min_trades=50)
        value = compute_objective(metrics, cfg)
        assert isinstance(value, float)

    def test_disabled_penalties(self) -> None:
        """Setting thresholds to extremes should disable penalties."""
        metrics = _bad_metrics()
        cfg = ObjectiveConfig(
            primary="brier",
            brier_threshold=1.0,     # never triggers
            min_trades=0,            # never triggers
            max_drawdown_threshold=1.0,  # never triggers
            brier_penalty_weight=0.0,
            trade_penalty_weight=0.0,
            drawdown_penalty_weight=0.0,
        )
        value = compute_objective(metrics, cfg)
        # Only base = brier = 0.35, no penalties
        assert value == pytest.approx(0.35, abs=0.01)
