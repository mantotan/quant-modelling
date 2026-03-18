"""Tests for vol-scaled Kelly position sizing."""

from __future__ import annotations

import pytest

from qm.strategy.sizing.vol_kelly import VolScaledKellySizer


class TestVolScaleFactor:
    """Test vol_scale_factor() computation."""

    def test_no_vol_data_returns_one(self) -> None:
        """Without vol data, scale factor should be 1.0."""
        sizer = VolScaledKellySizer()
        assert sizer.vol_scale_factor() == 1.0

    def test_normal_vol_returns_one(self) -> None:
        """When current_vol == median_vol, scale factor should be 1.0."""
        sizer = VolScaledKellySizer(median_vol=0.02)
        sizer.update_vol(0.02)
        assert sizer.vol_scale_factor() == pytest.approx(1.0)

    def test_high_vol_reduces_factor(self) -> None:
        """High vol should produce scale factor < 1.0."""
        sizer = VolScaledKellySizer(median_vol=0.02)
        sizer.update_vol(0.06)  # 3x median
        factor = sizer.vol_scale_factor()
        assert factor == pytest.approx(0.02 / 0.06, abs=0.01)
        assert factor < 1.0

    def test_low_vol_increases_factor(self) -> None:
        """Low vol should produce scale factor > 1.0."""
        sizer = VolScaledKellySizer(median_vol=0.02)
        sizer.update_vol(0.01)  # half median
        factor = sizer.vol_scale_factor()
        assert factor == pytest.approx(2.0)
        assert factor > 1.0

    def test_clamped_to_min_scale(self) -> None:
        """Extreme high vol should be clamped at min_scale."""
        sizer = VolScaledKellySizer(median_vol=0.02, min_scale=0.25)
        sizer.update_vol(0.20)  # 10x median → raw=0.1 → clamped to 0.25
        assert sizer.vol_scale_factor() == pytest.approx(0.25)

    def test_clamped_to_max_scale(self) -> None:
        """Extreme low vol should be clamped at max_scale."""
        sizer = VolScaledKellySizer(median_vol=0.02, max_scale=2.0)
        sizer.update_vol(0.005)  # 0.25x median → raw=4.0 → clamped to 2.0
        assert sizer.vol_scale_factor() == pytest.approx(2.0)

    def test_zero_current_vol_returns_one(self) -> None:
        sizer = VolScaledKellySizer(median_vol=0.02)
        sizer.update_vol(0.0)
        assert sizer.vol_scale_factor() == 1.0

    def test_zero_median_vol_returns_one(self) -> None:
        sizer = VolScaledKellySizer(median_vol=0.0)
        sizer.update_vol(0.02)
        assert sizer.vol_scale_factor() == 1.0


class TestEffectiveFraction:
    """Test effective_fraction() after vol scaling."""

    def test_normal_vol_unchanged(self) -> None:
        sizer = VolScaledKellySizer(base_fraction=0.25, median_vol=0.02)
        sizer.update_vol(0.02)
        assert sizer.effective_fraction() == pytest.approx(0.25)

    def test_crisis_vol_reduced(self) -> None:
        """Crisis vol (3x) should reduce fraction to ~1/3."""
        sizer = VolScaledKellySizer(base_fraction=0.25, median_vol=0.02)
        sizer.update_vol(0.06)
        eff = sizer.effective_fraction()
        assert eff == pytest.approx(0.25 * (0.02 / 0.06), abs=0.01)
        assert eff < 0.25

    def test_calm_vol_increased(self) -> None:
        """Low vol (0.5x) should increase fraction to 2x."""
        sizer = VolScaledKellySizer(base_fraction=0.25, median_vol=0.02, max_scale=2.0)
        sizer.update_vol(0.01)
        eff = sizer.effective_fraction()
        assert eff == pytest.approx(0.50)


class TestVolKellySize:
    """Test the size() method with vol scaling."""

    def test_basic_sizing(self) -> None:
        """Should produce a valid bet size."""
        sizer = VolScaledKellySizer(base_fraction=0.25, median_vol=0.02)
        sizer.update_vol(0.02)
        bet = sizer.size(edge=0.05, market_price=0.50, bankroll=10000)
        assert bet > 0
        assert bet <= 500  # max_bet_usd default

    def test_high_vol_reduces_bet(self) -> None:
        """Higher vol should produce smaller bet than normal vol."""
        sizer = VolScaledKellySizer(base_fraction=0.25, median_vol=0.02)
        sizer.update_vol(0.02)
        normal_bet = sizer.size(edge=0.05, market_price=0.50, bankroll=10000)

        sizer.update_vol(0.06)
        crisis_bet = sizer.size(edge=0.05, market_price=0.50, bankroll=10000)

        assert crisis_bet < normal_bet

    def test_low_vol_increases_bet(self) -> None:
        """Lower vol should produce larger bet than normal vol."""
        sizer = VolScaledKellySizer(base_fraction=0.25, median_vol=0.02)
        sizer.update_vol(0.02)
        normal_bet = sizer.size(edge=0.05, market_price=0.50, bankroll=10000)

        sizer.update_vol(0.01)
        calm_bet = sizer.size(edge=0.05, market_price=0.50, bankroll=10000)

        assert calm_bet > normal_bet

    def test_zero_edge_returns_zero(self) -> None:
        sizer = VolScaledKellySizer()
        sizer.update_vol(0.02)
        assert sizer.size(edge=0.0, market_price=0.50, bankroll=10000) == 0.0

    def test_negative_edge_returns_zero(self) -> None:
        sizer = VolScaledKellySizer()
        sizer.update_vol(0.02)
        assert sizer.size(edge=-0.05, market_price=0.50, bankroll=10000) == 0.0

    def test_extreme_price_returns_zero(self) -> None:
        sizer = VolScaledKellySizer()
        sizer.update_vol(0.02)
        assert sizer.size(edge=0.05, market_price=0.005, bankroll=10000) == 0.0
        assert sizer.size(edge=0.05, market_price=0.995, bankroll=10000) == 0.0

    def test_max_bet_cap(self) -> None:
        """Bet should never exceed max_bet_usd."""
        sizer = VolScaledKellySizer(max_bet_usd=200)
        sizer.update_vol(0.005)  # very low vol → max scale
        bet = sizer.size(edge=0.10, market_price=0.50, bankroll=100000)
        assert bet <= 200

    def test_min_bet_filter(self) -> None:
        """Very small bets should be filtered to zero."""
        sizer = VolScaledKellySizer(min_bet_usd=5.0, base_fraction=0.01)
        sizer.update_vol(0.10)  # high vol → small fraction
        bet = sizer.size(edge=0.001, market_price=0.50, bankroll=100)
        assert bet == 0.0

    def test_zero_bankroll_returns_zero(self) -> None:
        sizer = VolScaledKellySizer()
        assert sizer.size(edge=0.05, market_price=0.50, bankroll=0) == 0.0


class TestUpdateVol:
    """Test vol state updates."""

    def test_update_current_vol(self) -> None:
        sizer = VolScaledKellySizer()
        assert sizer.current_vol is None
        sizer.update_vol(0.03)
        assert sizer.current_vol == 0.03

    def test_update_median_vol(self) -> None:
        sizer = VolScaledKellySizer(median_vol=0.02)
        sizer.update_vol(0.03, median_vol=0.025)
        assert sizer.median_vol == 0.025

    def test_keep_median_when_none(self) -> None:
        sizer = VolScaledKellySizer(median_vol=0.02)
        sizer.update_vol(0.03)
        assert sizer.median_vol == 0.02
