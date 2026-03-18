"""Tests for signal generation and Kelly sizing."""

from datetime import datetime, timezone

import numpy as np
import pytest

from qm.core.types import Asset, MarketType, Outcome
from qm.model.signals import SignalGenerator
from qm.strategy.sizing.kelly import KellySizer


class TestSignalGenerator:
    def test_signal_generated_with_edge(self):
        gen = SignalGenerator(min_edge=0.03)
        sig = gen.generate(
            timestamp=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            asset=Asset.BTC,
            market_type=MarketType.FIVE_MIN,
            model_prob_up=0.65,
            market_prob_up=0.50,
            market_spread=0.02,
        )
        assert sig is not None
        assert sig.recommended_side == Outcome.UP
        assert sig.edge > 0

    def test_no_signal_when_no_edge(self):
        gen = SignalGenerator(min_edge=0.05)
        sig = gen.generate(
            timestamp=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            asset=Asset.BTC,
            market_type=MarketType.FIVE_MIN,
            model_prob_up=0.51,
            market_prob_up=0.50,
            market_spread=0.02,
        )
        assert sig is None  # edge too small

    def test_down_signal(self):
        gen = SignalGenerator(min_edge=0.03)
        sig = gen.generate(
            timestamp=datetime(2026, 3, 18, 12, 0, tzinfo=timezone.utc),
            asset=Asset.ETH,
            market_type=MarketType.FIVE_MIN,
            model_prob_up=0.35,
            market_prob_up=0.50,
            market_spread=0.02,
        )
        assert sig is not None
        assert sig.recommended_side == Outcome.DOWN

    def test_spread_reduces_edge(self):
        gen = SignalGenerator(min_edge=0.05)
        # Edge before spread: 0.60 - 0.50 = 0.10
        # Edge after spread: 0.10 - 0.02/2 = 0.09 > 0.05 ✓
        sig_narrow = gen.generate(
            timestamp=datetime.now(timezone.utc),
            asset=Asset.BTC, market_type=MarketType.FIVE_MIN,
            model_prob_up=0.60, market_prob_up=0.50, market_spread=0.02,
        )
        assert sig_narrow is not None

        # Wide spread eats the edge
        # Edge after spread: 0.10 - 0.20/2 = 0.00 < 0.05
        sig_wide = gen.generate(
            timestamp=datetime.now(timezone.utc),
            asset=Asset.BTC, market_type=MarketType.FIVE_MIN,
            model_prob_up=0.60, market_prob_up=0.50, market_spread=0.20,
        )
        assert sig_wide is None

    def test_batch_generation(self):
        gen = SignalGenerator(min_edge=0.03)
        n = 10
        timestamps = np.array([datetime(2026, 3, 18, 12, i * 5, tzinfo=timezone.utc) for i in range(n)])
        model_probs = np.array([0.65, 0.51, 0.35, 0.70, 0.48, 0.80, 0.52, 0.30, 0.55, 0.45])
        market_probs = np.full(n, 0.50)

        signals = gen.generate_batch(timestamps, Asset.BTC, MarketType.FIVE_MIN, model_probs, market_probs)
        # Should filter out low-edge predictions
        assert len(signals) < n
        assert all(s.edge >= 0.03 for s in signals)


class TestKellySizer:
    def test_positive_edge_gives_positive_size(self):
        sizer = KellySizer(fraction=0.25)
        size = sizer.size(edge=0.10, market_price=0.50, bankroll=10000)
        assert size > 0

    def test_no_edge_gives_zero(self):
        sizer = KellySizer()
        size = sizer.size(edge=0.0, market_price=0.50, bankroll=10000)
        assert size == 0.0

    def test_negative_edge_gives_zero(self):
        sizer = KellySizer()
        size = sizer.size(edge=-0.05, market_price=0.50, bankroll=10000)
        assert size == 0.0

    def test_respects_max_bet(self):
        sizer = KellySizer(fraction=1.0, max_bet_usd=100.0)  # full Kelly, capped
        size = sizer.size(edge=0.30, market_price=0.50, bankroll=100000)
        assert size <= 100.0

    def test_respects_max_pct(self):
        sizer = KellySizer(fraction=1.0, max_bet_pct=0.02, max_bet_usd=99999)
        size = sizer.size(edge=0.30, market_price=0.50, bankroll=10000)
        assert size <= 200.0  # 2% of 10000

    def test_below_min_returns_zero(self):
        sizer = KellySizer(fraction=0.01, min_bet_usd=5.0)
        size = sizer.size(edge=0.01, market_price=0.50, bankroll=100)
        # Very small edge * tiny fraction * small bankroll = below min
        assert size == 0.0

    def test_extreme_prices(self):
        sizer = KellySizer()
        assert sizer.size(edge=0.10, market_price=0.001, bankroll=1000) == 0.0
        assert sizer.size(edge=0.10, market_price=0.999, bankroll=1000) == 0.0

    def test_quarter_kelly_smaller_than_full(self):
        full = KellySizer(fraction=1.0, max_bet_usd=99999, max_bet_pct=1.0)
        quarter = KellySizer(fraction=0.25, max_bet_usd=99999, max_bet_pct=1.0)
        full_size = full.size(0.10, 0.50, 10000)
        quarter_size = quarter.size(0.10, 0.50, 10000)
        assert quarter_size < full_size
        assert abs(quarter_size - full_size * 0.25) < 1.0  # approximately 25%
