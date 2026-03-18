"""Shared test fixtures."""

from datetime import datetime, timezone

import pytest

from qm.core.types import Asset, Bar, Timeframe


@pytest.fixture
def sample_bar() -> Bar:
    return Bar(
        timestamp=datetime(2026, 3, 18, 12, 0, 0, tzinfo=timezone.utc),
        asset=Asset.BTC,
        timeframe=Timeframe.M5,
        open=84000.0,
        high=84200.0,
        low=83900.0,
        close=84100.0,
        volume=125.5,
        trade_count=1432,
        vwap=84050.0,
    )


@pytest.fixture
def sample_bars() -> list[Bar]:
    """Generate a sequence of 20 sample bars for testing."""
    bars = []
    base_price = 84000.0
    for i in range(20):
        price = base_price + i * 10
        bars.append(
            Bar(
                timestamp=datetime(2026, 3, 18, 12, i * 5, 0, tzinfo=timezone.utc),
                asset=Asset.BTC,
                timeframe=Timeframe.M5,
                open=price,
                high=price + 50,
                low=price - 30,
                close=price + 20,
                volume=100.0 + i,
                trade_count=1000 + i * 10,
                vwap=price + 10,
            )
        )
    return bars
