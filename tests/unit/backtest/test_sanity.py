"""Tests for BacktestSanityChecker."""

from __future__ import annotations

import pytest

from qm.backtest.sanity import AcceptanceCriteria, BacktestSanityChecker, CheckResult


def _good_metrics() -> dict[str, float]:
    """Metrics that pass all default acceptance criteria."""
    return {
        "brier": 0.20,
        "ece": 0.03,
        "sharpe": 1.5,
        "max_dd": 0.15,
        "total_pnl": 500.0,
        "pbo": 0.30,
        "n_trades": 100,
        "win_rate": 0.55,
    }


def _bad_metrics() -> dict[str, float]:
    """Metrics that fail most acceptance criteria."""
    return {
        "brier": 0.30,
        "ece": 0.08,
        "sharpe": -0.5,
        "max_dd": 0.45,
        "total_pnl": -200.0,
        "pbo": 0.60,
        "n_trades": 10,
        "win_rate": 0.40,
    }


class TestAcceptanceCriteria:
    def test_default_values(self) -> None:
        c = AcceptanceCriteria()
        assert c.max_brier == 0.25
        assert c.max_ece == 0.05
        assert c.min_sharpe == 0.0
        assert c.max_drawdown == 0.30
        assert c.min_trades == 50

    def test_custom_values(self) -> None:
        c = AcceptanceCriteria(max_brier=0.22, min_trades=100)
        assert c.max_brier == 0.22
        assert c.min_trades == 100

    def test_frozen(self) -> None:
        c = AcceptanceCriteria()
        with pytest.raises(AttributeError):
            c.max_brier = 0.30  # type: ignore[misc]


class TestCheckResult:
    def test_passed_result(self) -> None:
        r = CheckResult("brier", True, 0.20, 0.25, "Brier 0.20 <= 0.25")
        assert r.passed
        assert r.name == "brier"

    def test_failed_result(self) -> None:
        r = CheckResult("brier", False, 0.30, 0.25, "Brier 0.30 > 0.25")
        assert not r.passed


class TestBacktestSanityChecker:
    def test_good_metrics_all_pass(self) -> None:
        checker = BacktestSanityChecker()
        results = checker.check(_good_metrics())
        assert checker.all_passed(results)
        assert len(checker.failures(results)) == 0

    def test_bad_metrics_multiple_failures(self) -> None:
        checker = BacktestSanityChecker()
        results = checker.check(_bad_metrics())
        assert not checker.all_passed(results)
        failures = checker.failures(results)
        assert len(failures) >= 5  # brier, ece, sharpe, dd, pnl, pbo, trades

    def test_brier_check(self) -> None:
        checker = BacktestSanityChecker()
        metrics = _good_metrics()
        metrics["brier"] = 0.26  # just above threshold
        results = checker.check(metrics)
        brier_result = next(r for r in results if r.name == "brier")
        assert not brier_result.passed

    def test_ece_check(self) -> None:
        checker = BacktestSanityChecker()
        metrics = _good_metrics()
        metrics["ece"] = 0.06
        results = checker.check(metrics)
        ece_result = next(r for r in results if r.name == "ece")
        assert not ece_result.passed

    def test_sharpe_check(self) -> None:
        checker = BacktestSanityChecker()
        metrics = _good_metrics()
        metrics["sharpe"] = -0.1
        results = checker.check(metrics)
        sharpe_result = next(r for r in results if r.name == "sharpe")
        assert not sharpe_result.passed

    def test_drawdown_check(self) -> None:
        checker = BacktestSanityChecker()
        metrics = _good_metrics()
        metrics["max_dd"] = 0.35
        results = checker.check(metrics)
        dd_result = next(r for r in results if r.name == "max_dd")
        assert not dd_result.passed

    def test_pnl_check(self) -> None:
        checker = BacktestSanityChecker()
        metrics = _good_metrics()
        metrics["total_pnl"] = -10.0
        results = checker.check(metrics)
        pnl_result = next(r for r in results if r.name == "pnl")
        assert not pnl_result.passed

    def test_pbo_check_when_present(self) -> None:
        checker = BacktestSanityChecker()
        metrics = _good_metrics()
        metrics["pbo"] = 0.50  # above 0.40 threshold
        results = checker.check(metrics)
        pbo_result = next(r for r in results if r.name == "pbo")
        assert not pbo_result.passed

    def test_pbo_check_skipped_when_absent(self) -> None:
        checker = BacktestSanityChecker()
        metrics = _good_metrics()
        del metrics["pbo"]
        results = checker.check(metrics)
        pbo_results = [r for r in results if r.name == "pbo"]
        assert len(pbo_results) == 0

    def test_trade_count_check(self) -> None:
        checker = BacktestSanityChecker()
        metrics = _good_metrics()
        metrics["n_trades"] = 30
        results = checker.check(metrics)
        trade_result = next(r for r in results if r.name == "n_trades")
        assert not trade_result.passed

    def test_win_rate_leakage_check(self) -> None:
        """Suspiciously high win rate should fail sanity check."""
        checker = BacktestSanityChecker()
        metrics = _good_metrics()
        metrics["win_rate"] = 0.90  # too good to be true
        results = checker.check(metrics)
        wr_result = next(r for r in results if r.name == "win_rate_sanity")
        assert not wr_result.passed

    def test_sharpe_leakage_check(self) -> None:
        """Suspiciously high Sharpe should fail sanity check."""
        checker = BacktestSanityChecker()
        metrics = _good_metrics()
        metrics["sharpe"] = 6.0  # unrealistic
        results = checker.check(metrics)
        sharpe_result = next(r for r in results if r.name == "sharpe_sanity")
        assert not sharpe_result.passed

    def test_custom_criteria(self) -> None:
        """Custom tighter criteria should produce more failures."""
        strict = AcceptanceCriteria(max_brier=0.15, min_sharpe=1.0, min_trades=200)
        checker = BacktestSanityChecker(criteria=strict)
        metrics = _good_metrics()
        results = checker.check(metrics)
        # brier=0.20 > 0.15, trades=100 < 200 → should fail
        assert not checker.all_passed(results)

    def test_summary_format(self) -> None:
        checker = BacktestSanityChecker()
        results = checker.check(_good_metrics())
        summary = checker.summary(results)
        assert "Sanity check:" in summary
        assert "PASS" in summary

    def test_missing_metrics_use_defaults(self) -> None:
        """Missing keys should use safe defaults (worst case)."""
        checker = BacktestSanityChecker()
        results = checker.check({})
        # Should fail most checks with default worst-case values
        assert not checker.all_passed(results)

    def test_boundary_values_pass(self) -> None:
        """Metrics exactly at thresholds should pass."""
        checker = BacktestSanityChecker()
        metrics = {
            "brier": 0.25,
            "ece": 0.05,
            "sharpe": 0.0,
            "max_dd": 0.30,
            "total_pnl": 0.0,
            "n_trades": 50,
            "win_rate": 0.55,
        }
        results = checker.check(metrics)
        assert checker.all_passed(results)
