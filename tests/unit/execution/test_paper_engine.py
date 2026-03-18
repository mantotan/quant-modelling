"""Tests for paper executor and trading loop."""

import pytest
from datetime import datetime, timezone

from qm.core.types import Asset, MarketType, Outcome, Signal
from qm.execution.paper.engine import PaperExecutor
from qm.execution.loop import Fill


def _signal(edge: float = 0.10) -> Signal:
    return Signal(
        timestamp=datetime.now(timezone.utc),
        asset=Asset.BTC,
        market_type=MarketType.FIVE_MIN,
        model_prob_up=0.60,
        market_prob_up=0.50,
        edge=edge,
        confidence=0.7,
        recommended_side=Outcome.UP,
        recommended_size=100.0,
    )


class TestPaperExecutor:
    @pytest.mark.asyncio
    async def test_fill_is_pessimistic(self):
        executor = PaperExecutor()
        sig = _signal()
        fill = await executor.execute(sig, 100.0)

        assert fill.status == "filled"
        assert fill.size_usd == 100.0
        # Pessimistic: fill_price > market_prob (crossed spread)
        assert fill.price > sig.market_prob_up

    @pytest.mark.asyncio
    async def test_fill_for_down_side(self):
        sig = Signal(
            timestamp=datetime.now(timezone.utc),
            asset=Asset.ETH,
            market_type=MarketType.FIVE_MIN,
            model_prob_up=0.35,
            market_prob_up=0.50,
            edge=0.14,
            confidence=0.7,
            recommended_side=Outcome.DOWN,
            recommended_size=50.0,
        )
        executor = PaperExecutor()
        fill = await executor.execute(sig, 50.0)

        assert fill.status == "filled"
        # Down side: base_price = 1 - 0.50 = 0.50, + spread/2
        assert fill.price > 0.50

    @pytest.mark.asyncio
    async def test_fill_counter_increments(self):
        executor = PaperExecutor()
        sig = _signal()
        await executor.execute(sig, 100.0)
        await executor.execute(sig, 200.0)
        assert executor.total_fills == 2

    @pytest.mark.asyncio
    async def test_fill_price_clamped(self):
        """Fill price should never exceed [0.01, 0.99]."""
        sig = Signal(
            timestamp=datetime.now(timezone.utc),
            asset=Asset.BTC,
            market_type=MarketType.FIVE_MIN,
            model_prob_up=0.99,
            market_prob_up=0.99,
            edge=0.05,
            confidence=0.9,
            recommended_side=Outcome.UP,
            recommended_size=100.0,
        )
        executor = PaperExecutor()
        fill = await executor.execute(sig, 100.0)
        assert 0.01 <= fill.price <= 0.99


class TestBacktestReport:
    def test_acceptance_pass(self):
        from qm.backtest.report import check_acceptance
        metrics = {
            "sharpe": 1.5, "brier": 0.20, "total_pnl": 500,
            "max_dd": 0.15, "accuracy": 0.55, "n_trades": 100,
        }
        passed, failures = check_acceptance(metrics)
        assert passed
        assert len(failures) == 0

    def test_acceptance_fail_brier(self):
        from qm.backtest.report import check_acceptance
        metrics = {"sharpe": 1.0, "brier": 0.30, "total_pnl": 100, "max_dd": 0.10}
        passed, failures = check_acceptance(metrics)
        assert not passed
        assert any("Brier" in f for f in failures)

    def test_acceptance_fail_pnl(self):
        from qm.backtest.report import check_acceptance
        metrics = {"sharpe": -0.5, "brier": 0.20, "total_pnl": -100, "max_dd": 0.05}
        passed, failures = check_acceptance(metrics)
        assert not passed
        assert any("PnL" in f for f in failures)
