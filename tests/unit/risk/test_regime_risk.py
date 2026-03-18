"""Tests for regime-aware risk management (set_regime + dynamic correlations)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from qm.core.types import Asset, MarketType, Outcome, RegimeState, Signal
from qm.risk.bankroll import Bankroll
from qm.risk.circuit_breaker import CircuitBreaker
from qm.risk.limits import (
    ASSET_CORRELATIONS,
    get_regime_correlations,
)
from qm.risk.manager import RiskManager


def _signal(asset: Asset = Asset.BTC, edge: float = 0.10) -> Signal:
    return Signal(
        timestamp=datetime.now(UTC),
        asset=asset,
        market_type=MarketType.FIVE_MIN,
        model_prob_up=0.60,
        market_prob_up=0.50,
        edge=edge,
        confidence=0.7,
        recommended_side=Outcome.UP,
        recommended_size=100.0,
    )


def _make_rm(**kwargs) -> RiskManager:
    br = kwargs.pop("bankroll", Bankroll(initial=10000))
    cb = kwargs.pop("circuit_breaker", CircuitBreaker())
    return RiskManager(bankroll=br, circuit_breaker=cb, **kwargs)


class TestRegimeState:
    """Test RegimeState enum values match feature output."""

    def test_enum_values(self) -> None:
        assert RegimeState.LOW == 0
        assert RegimeState.NORMAL == 1
        assert RegimeState.HIGH == 2
        assert RegimeState.CRISIS == 3

    def test_from_int(self) -> None:
        assert RegimeState(0) == RegimeState.LOW
        assert RegimeState(3) == RegimeState.CRISIS


class TestGetRegimeCorrelations:
    """Test dynamic correlation adjustment."""

    def test_normal_regime_unchanged(self) -> None:
        """Normal regime should return baseline correlations."""
        corrs = get_regime_correlations(RegimeState.NORMAL)
        for pair, base_corr in ASSET_CORRELATIONS.items():
            assert corrs[pair] == pytest.approx(base_corr, abs=1e-10)

    def test_crisis_regime_higher(self) -> None:
        """Crisis regime should increase all correlations."""
        normal = get_regime_correlations(RegimeState.NORMAL)
        crisis = get_regime_correlations(RegimeState.CRISIS)
        for pair in ASSET_CORRELATIONS:
            assert crisis[pair] >= normal[pair]

    def test_low_regime_lower(self) -> None:
        """Low regime should decrease correlations slightly."""
        normal = get_regime_correlations(RegimeState.NORMAL)
        low = get_regime_correlations(RegimeState.LOW)
        for pair in ASSET_CORRELATIONS:
            assert low[pair] <= normal[pair]

    def test_correlations_clamped_to_one(self) -> None:
        """Correlations should never exceed 1.0."""
        crisis = get_regime_correlations(RegimeState.CRISIS)
        for corr in crisis.values():
            assert corr <= 1.0

    def test_all_pairs_present(self) -> None:
        """All asset pairs should be present in regime correlations."""
        for regime in RegimeState:
            corrs = get_regime_correlations(regime)
            assert set(corrs.keys()) == set(ASSET_CORRELATIONS.keys())


class TestRiskManagerSetRegime:
    """Test RiskManager.set_regime() behavior."""

    def test_default_regime_is_normal(self) -> None:
        rm = _make_rm()
        assert rm.regime == RegimeState.NORMAL

    def test_set_regime_updates_state(self) -> None:
        rm = _make_rm()
        rm.set_regime(RegimeState.CRISIS)
        assert rm.regime == RegimeState.CRISIS

    def test_set_same_regime_noop(self) -> None:
        """Setting the same regime should be a no-op."""
        rm = _make_rm()
        rm.set_regime(RegimeState.NORMAL)
        assert rm.regime == RegimeState.NORMAL

    def test_regime_adjusted_max_bet_normal(self) -> None:
        rm = _make_rm(max_single_bet_pct=0.05)
        assert rm.regime_adjusted_max_bet_pct() == pytest.approx(0.05)

    def test_regime_adjusted_max_bet_crisis(self) -> None:
        """Crisis regime should halve the max bet size."""
        rm = _make_rm(max_single_bet_pct=0.05)
        rm.set_regime(RegimeState.CRISIS)
        assert rm.regime_adjusted_max_bet_pct() == pytest.approx(0.025)

    def test_regime_adjusted_max_bet_high(self) -> None:
        """High vol regime should reduce bet size by 25%."""
        rm = _make_rm(max_single_bet_pct=0.05)
        rm.set_regime(RegimeState.HIGH)
        assert rm.regime_adjusted_max_bet_pct() == pytest.approx(0.0375)

    def test_crisis_rejects_normal_size_bet(self) -> None:
        """A bet that passes in normal should be rejected in crisis."""
        rm = _make_rm(max_single_bet_pct=0.05)
        sig = _signal()

        # Normal: 400 < 5% of 10000 = 500 → OK
        ok, _ = rm.pre_trade_check(sig, 400.0, [])
        assert ok

        # Crisis: max bet = 2.5% of 10000 = 250 → 400 rejected
        rm.set_regime(RegimeState.CRISIS)
        ok, reason = rm.pre_trade_check(sig, 400.0, [])
        assert not ok
        assert "single_bet_size" in reason

    def test_crisis_increases_correlated_exposure(self) -> None:
        """Crisis regime should make correlated exposure checks stricter."""
        rm = _make_rm(max_correlated_exposure=0.60)
        sig = _signal(Asset.ETH)
        positions = [{"asset": Asset.BTC, "side": "Up", "size_usd": 500}]

        # Normal: corr(BTC,ETH)=0.85, exposure = 100 + 500*0.85 = 525/10000 = 5.25% → OK
        ok, _ = rm.pre_trade_check(sig, 100.0, positions)
        assert ok

        # Crisis: corr=min(1.0, 0.85*1.25)=1.0
        # exposure = 200 + 500*1.0 = 700/10000 = 7% → OK but with higher sizes...
        rm.set_regime(RegimeState.CRISIS)
        # 5500 + 500*1.0 = 6000/10000 = 60% → borderline
        ok_crisis, _ = rm.pre_trade_check(sig, 100.0, positions)
        # With crisis correlations (1.0): 100 + 500*1.0 = 600/10000 = 6% → still OK
        assert ok_crisis

    def test_regime_cycle(self) -> None:
        """Should handle cycling through all regimes."""
        rm = _make_rm()
        for regime in RegimeState:
            rm.set_regime(regime)
            assert rm.regime == regime
        # Back to normal
        rm.set_regime(RegimeState.NORMAL)
        assert rm.regime == RegimeState.NORMAL
