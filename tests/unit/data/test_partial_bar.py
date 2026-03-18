"""Tests for PartialBar snapshot from BarBuilder."""

from datetime import datetime, timedelta, timezone

import pytest

from qm.core.types import Asset, PartialBar, Timeframe
from qm.data.ingestion.bar_builder import BarBuilder


@pytest.fixture
def builder() -> BarBuilder:
    return BarBuilder(
        assets=[Asset.BTC],
        timeframes=[Timeframe.M5],
    )


class TestGetPartialBar:
    def test_returns_none_before_any_trade(self, builder: BarBuilder):
        result = builder.get_partial_bar(Asset.BTC, Timeframe.M5)
        assert result is None

    def test_returns_partial_after_first_trade(self, builder: BarBuilder):
        ts = datetime(2026, 3, 18, 12, 0, 1, tzinfo=timezone.utc)
        builder.on_trade(Asset.BTC, 70000.0, 0.5, ts)
        partial = builder.get_partial_bar(Asset.BTC, Timeframe.M5, now=ts)
        assert partial is not None
        assert isinstance(partial, PartialBar)
        assert partial.open == 70000.0
        assert partial.current_price == 70000.0
        assert partial.high_so_far == 70000.0
        assert partial.low_so_far == 70000.0
        assert partial.volume_so_far == 0.5
        assert partial.trade_count == 1
        assert partial.asset == Asset.BTC
        assert partial.timeframe == Timeframe.M5

    def test_high_low_update_with_multiple_trades(self, builder: BarBuilder):
        base = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
        builder.on_trade(Asset.BTC, 70000.0, 1.0, base + timedelta(seconds=1))
        builder.on_trade(Asset.BTC, 70500.0, 0.5, base + timedelta(seconds=2))
        builder.on_trade(Asset.BTC, 69800.0, 0.3, base + timedelta(seconds=3))
        builder.on_trade(Asset.BTC, 70100.0, 0.2, base + timedelta(seconds=4))

        partial = builder.get_partial_bar(
            Asset.BTC, Timeframe.M5, now=base + timedelta(seconds=4)
        )
        assert partial is not None
        assert partial.open == 70000.0
        assert partial.high_so_far == 70500.0
        assert partial.low_so_far == 69800.0
        assert partial.current_price == 70100.0
        assert partial.volume_so_far == pytest.approx(2.0)
        assert partial.trade_count == 4

    def test_elapsed_and_remaining_seconds(self, builder: BarBuilder):
        base = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
        builder.on_trade(Asset.BTC, 70000.0, 1.0, base + timedelta(seconds=1))

        now = base + timedelta(seconds=120)  # 2 minutes into 5-min bar
        partial = builder.get_partial_bar(Asset.BTC, Timeframe.M5, now=now)
        assert partial is not None
        assert partial.elapsed_seconds == pytest.approx(120.0)
        assert partial.remaining_seconds == pytest.approx(180.0)

    def test_elapsed_clamped_to_total(self, builder: BarBuilder):
        """Clock skew: `now` is after window_end. Elapsed should be clamped."""
        base = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
        builder.on_trade(Asset.BTC, 70000.0, 1.0, base + timedelta(seconds=1))

        # now is 10 seconds past the window end
        now = base + timedelta(seconds=310)
        partial = builder.get_partial_bar(Asset.BTC, Timeframe.M5, now=now)
        assert partial is not None
        assert partial.elapsed_seconds == pytest.approx(300.0)
        assert partial.remaining_seconds == pytest.approx(0.0)

    def test_remaining_clamped_to_zero(self, builder: BarBuilder):
        """Now before window_start (edge case). Elapsed=0, remaining=total."""
        base = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
        builder.on_trade(Asset.BTC, 70000.0, 1.0, base + timedelta(seconds=1))

        now = base - timedelta(seconds=5)  # before window start
        partial = builder.get_partial_bar(Asset.BTC, Timeframe.M5, now=now)
        assert partial is not None
        assert partial.elapsed_seconds == pytest.approx(0.0)
        assert partial.remaining_seconds == pytest.approx(300.0)

    def test_returns_none_for_unknown_asset(self, builder: BarBuilder):
        result = builder.get_partial_bar(Asset.ETH, Timeframe.M5)
        assert result is None

    def test_returns_none_for_unknown_timeframe(self, builder: BarBuilder):
        ts = datetime(2026, 3, 18, 12, 0, 1, tzinfo=timezone.utc)
        builder.on_trade(Asset.BTC, 70000.0, 1.0, ts)
        result = builder.get_partial_bar(Asset.BTC, Timeframe.H1)
        assert result is None

    def test_partial_bar_is_frozen(self, builder: BarBuilder):
        ts = datetime(2026, 3, 18, 12, 0, 1, tzinfo=timezone.utc)
        builder.on_trade(Asset.BTC, 70000.0, 1.0, ts)
        partial = builder.get_partial_bar(Asset.BTC, Timeframe.M5, now=ts)
        assert partial is not None
        with pytest.raises(AttributeError):
            partial.current_price = 99999.0  # type: ignore[misc]

    def test_new_bar_after_window_boundary(self, builder: BarBuilder):
        """After a bar completes, get_partial_bar returns the NEW bar."""
        base = datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc)
        builder.on_trade(Asset.BTC, 70000.0, 1.0, base + timedelta(seconds=1))
        # This trade crosses the boundary -> completes old bar, starts new one
        new_bar_ts = base + timedelta(minutes=5, seconds=1)
        completed = builder.on_trade(Asset.BTC, 71000.0, 0.5, new_bar_ts)
        assert len(completed) >= 1

        partial = builder.get_partial_bar(Asset.BTC, Timeframe.M5, now=new_bar_ts)
        assert partial is not None
        assert partial.open == 71000.0  # new bar's open
        assert partial.current_price == 71000.0
