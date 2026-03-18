"""Tests for core types and clock alignment."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from qm.core.clock import align_to_window
from qm.core.types import Asset, Bar, Timeframe


def test_asset_enum():
    assert Asset.BTC.value == "BTC"
    assert Asset("ETH") == Asset.ETH


def test_timeframe_enum():
    assert Timeframe.M5.value == "5m"
    assert Timeframe.H1.value == "1h"


def test_bar_is_frozen(sample_bar: Bar):
    """Bars must be immutable."""
    import pytest

    with pytest.raises(AttributeError):
        sample_bar.close = 99999.0  # type: ignore[misc]


def test_bar_slots(sample_bar: Bar):
    """Frozen + slots prevent accidental attribute creation."""
    import pytest

    with pytest.raises((AttributeError, TypeError)):
        sample_bar.foo = "bar"  # type: ignore[attr-defined]


def test_align_to_5m_window():
    ts = datetime(2026, 3, 18, 12, 7, 33, tzinfo=timezone.utc)
    aligned = align_to_window(ts, 5)
    et = aligned.astimezone(ZoneInfo("America/New_York"))
    assert et.second == 0
    assert et.microsecond == 0
    assert et.minute % 5 == 0


def test_align_to_15m_window():
    ts = datetime(2026, 3, 18, 12, 22, 0, tzinfo=timezone.utc)
    aligned = align_to_window(ts, 15)
    et = aligned.astimezone(ZoneInfo("America/New_York"))
    assert et.minute % 15 == 0


def test_align_to_1h_window():
    ts = datetime(2026, 3, 18, 12, 45, 0, tzinfo=timezone.utc)
    aligned = align_to_window(ts, 60)
    et = aligned.astimezone(ZoneInfo("America/New_York"))
    assert et.minute == 0


def test_align_dst_transition():
    """Verify alignment works across DST spring-forward (March)."""
    # March 9, 2025: DST spring forward at 2:00 AM ET
    ts = datetime(2025, 3, 9, 7, 8, 0, tzinfo=timezone.utc)  # 2:08 AM ET -> 3:08 AM ET
    aligned = align_to_window(ts, 5)
    et = aligned.astimezone(ZoneInfo("America/New_York"))
    assert et.minute % 5 == 0
    assert et.second == 0
