"""Tests for risk limit checks."""

import pytest

from qm.core.types import Asset, MarketType, Outcome, Signal
from qm.risk.bankroll import Bankroll
from qm.risk.circuit_breaker import CircuitBreaker
from qm.risk.limits import (
    check_asset_concentration,
    check_concurrent_limit,
    check_correlated_exposure,
    check_daily_loss,
    check_drawdown,
    check_single_bet_size,
)
from qm.risk.manager import RiskManager
from datetime import datetime, timezone


def _signal(asset: Asset = Asset.BTC, edge: float = 0.10) -> Signal:
    return Signal(
        timestamp=datetime.now(timezone.utc),
        asset=asset,
        market_type=MarketType.FIVE_MIN,
        model_prob_up=0.60,
        market_prob_up=0.50,
        edge=edge,
        confidence=0.7,
        recommended_side=Outcome.UP,
        recommended_size=100.0,
    )


class TestConcurrentLimit:
    def test_allows_under_limit(self):
        ok, _ = check_concurrent_limit(5, 20)
        assert ok

    def test_rejects_at_limit(self):
        ok, reason = check_concurrent_limit(20, 20)
        assert not ok
        assert "concurrent" in reason


class TestSingleBetSize:
    def test_allows_small_bet(self):
        br = Bankroll(initial=10000)
        ok, _ = check_single_bet_size(100.0, br, 0.05)
        assert ok

    def test_rejects_large_bet(self):
        br = Bankroll(initial=10000)
        ok, _ = check_single_bet_size(600.0, br, 0.05)  # 6% > 5%
        assert not ok


class TestDailyLoss:
    def test_allows_when_no_loss(self):
        br = Bankroll(initial=10000)
        ok, _ = check_daily_loss(br, 0.10)
        assert ok

    def test_rejects_when_daily_loss_exceeded(self):
        br = Bankroll(initial=10000)
        br.on_pnl(-1100)  # 11% loss
        ok, _ = check_daily_loss(br, 0.10)
        assert not ok


class TestDrawdown:
    def test_allows_small_drawdown(self):
        br = Bankroll(initial=10000)
        br.on_pnl(2000)   # HWM = 12000
        br.on_pnl(-1000)  # Current = 11000, DD = 8.3%
        ok, _ = check_drawdown(br, 0.25)
        assert ok

    def test_rejects_large_drawdown(self):
        br = Bankroll(initial=10000)
        br.on_pnl(5000)   # HWM = 15000
        br.on_pnl(-5000)  # Current = 10000, DD = 33%
        ok, _ = check_drawdown(br, 0.25)
        assert not ok


class TestAssetConcentration:
    def test_allows_balanced(self):
        ok, _ = check_asset_concentration(
            Asset.BTC, 100, {Asset.BTC: 300, Asset.ETH: 300}, 1000, 0.40
        )
        assert ok  # BTC would be 400/1000 = 40%

    def test_rejects_concentrated(self):
        ok, _ = check_asset_concentration(
            Asset.BTC, 200, {Asset.BTC: 300}, 1000, 0.40
        )
        assert not ok  # BTC would be 500/1000 = 50%


class TestCorrelatedExposure:
    def test_allows_uncorrelated(self):
        sig = _signal(Asset.BTC)
        positions = [{"asset": Asset.XRP, "side": "Down", "size_usd": 200}]
        ok, _ = check_correlated_exposure(sig, 100, positions, 1000, 0.60)
        assert ok

    def test_rejects_highly_correlated_same_direction(self):
        sig = _signal(Asset.ETH)
        positions = [{"asset": Asset.BTC, "side": "Up", "size_usd": 500}]
        # ETH-BTC corr = 0.85, same direction: corr_exp = 100 + 500*0.85 = 525/1000 = 52.5%
        ok, _ = check_correlated_exposure(sig, 100, positions, 1000, 0.60)
        assert ok  # 52.5% < 60%

        # With larger size
        ok, _ = check_correlated_exposure(sig, 200, positions, 1000, 0.60)
        # 200 + 500*0.85 = 625/1000 = 62.5% > 60%
        assert not ok


class TestCircuitBreaker:
    def test_not_tripped_initially(self):
        cb = CircuitBreaker()
        ok, _ = cb.check()
        assert ok
        assert not cb.is_tripped

    def test_trips_on_drawdown(self):
        cb = CircuitBreaker(max_drawdown=0.25)
        ok, reason = cb.check(drawdown=0.30)
        assert not ok
        assert cb.is_tripped
        assert "drawdown" in reason

    def test_stays_tripped_after_trip(self):
        cb = CircuitBreaker(max_drawdown=0.25)
        cb.check(drawdown=0.30)
        # Even with good conditions, still tripped
        ok, _ = cb.check(drawdown=0.0)
        assert not ok

    def test_reset_clears_trip(self):
        cb = CircuitBreaker(max_drawdown=0.25)
        cb.check(drawdown=0.30)
        cb.reset()
        ok, _ = cb.check(drawdown=0.0)
        assert ok

    def test_consecutive_losses_trip(self):
        cb = CircuitBreaker(consecutive_losses=5)
        for _ in range(5):
            cb.record_trade_result(won=False)
        ok, _ = cb.check()
        assert not ok

    def test_win_resets_consecutive_counter(self):
        cb = CircuitBreaker(consecutive_losses=5)
        for _ in range(4):
            cb.record_trade_result(won=False)
        cb.record_trade_result(won=True)
        ok, _ = cb.check()
        assert ok


class TestRiskManager:
    def test_passes_all_checks(self):
        br = Bankroll(initial=10000)
        cb = CircuitBreaker()
        rm = RiskManager(bankroll=br, circuit_breaker=cb)
        sig = _signal()
        ok, reason = rm.pre_trade_check(sig, 100.0, [])
        assert ok
        assert reason == "OK"

    def test_rejects_when_circuit_breaker_tripped(self):
        br = Bankroll(initial=10000)
        cb = CircuitBreaker(max_drawdown=0.01)
        br.on_pnl(-200)  # 2% DD, trips 1% threshold
        rm = RiskManager(bankroll=br, circuit_breaker=cb)
        sig = _signal()
        ok, reason = rm.pre_trade_check(sig, 100.0, [])
        assert not ok
        assert "circuit_breaker" in reason
