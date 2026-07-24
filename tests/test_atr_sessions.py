from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from hvn.atr import atr_before, wilder_atr
from hvn.models import ProfileFamily
from hvn.sessions import NEW_YORK, profile_window

from conftest import make_bar


def test_wilder_atr_24_completed_bars_only(base_time):
    bars = [
        make_bar(i, base_time + timedelta(minutes=i), "100", "102", "1")
        for i in range(1, 26)
    ]
    points = wilder_atr(bars)
    assert len(points) == 2
    assert points[0].available_time == bars[23].close_time
    assert points[0].value == Decimal(2)
    assert atr_before(points, bars[23].close_time) == points[0]


def test_wilder_atr_rejects_mixed_contracts(base_time):
    bars = [
        make_bar(i, base_time + timedelta(minutes=i), "100", "102", "1")
        for i in range(1, 25)
    ]
    bar = bars[-1]
    bars[-1] = type(bar)(
        bar.source_row_id,
        bar.close_time,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
        "NQM5",
    )
    with pytest.raises(ValueError, match="one contract symbol"):
        wilder_atr(bars)


@pytest.mark.parametrize(
    ("family", "start", "end"),
    [
        (ProfileFamily.PRIOR_RTH, "2025-01-08T09:30:00-05:00", "2025-01-08T16:00:00-05:00"),
        (ProfileFamily.FULL_OVERNIGHT, "2025-01-07T18:00:00-05:00", "2025-01-08T09:30:00-05:00"),
        (ProfileFamily.MIDNIGHT, "2025-01-08T00:00:00-05:00", "2025-01-08T09:30:00-05:00"),
        (ProfileFamily.OPENING_HOUR, "2025-01-08T09:30:00-05:00", "2025-01-08T10:30:00-05:00"),
    ],
)
def test_all_session_family_boundaries(family, start, end):
    window = profile_window(family, date(2025, 1, 8))
    assert window.source_start.isoformat() == start
    assert window.source_end.isoformat() == end
    assert window.freeze_time == window.source_end


def test_eth_crosses_midnight():
    window = profile_window(ProfileFamily.FULL_OVERNIGHT, date(2025, 1, 8))
    assert window.source_start.date() < window.source_end.date()


def test_spring_dst_elapsed_time_and_offsets():
    window = profile_window(ProfileFamily.FULL_OVERNIGHT, date(2025, 3, 9))
    assert window.source_start.utcoffset() == timedelta(hours=-5)
    assert window.source_end.utcoffset() == timedelta(hours=-4)
    assert (
        window.source_end.astimezone(ZoneInfo("UTC"))
        - window.source_start.astimezone(ZoneInfo("UTC"))
    ) == timedelta(hours=14, minutes=30)


def test_autumn_dst_elapsed_time_and_offsets():
    window = profile_window(ProfileFamily.FULL_OVERNIGHT, date(2025, 11, 2))
    assert window.source_start.utcoffset() == timedelta(hours=-4)
    assert window.source_end.utcoffset() == timedelta(hours=-5)
    assert (
        window.source_end.astimezone(ZoneInfo("UTC"))
        - window.source_start.astimezone(ZoneInfo("UTC"))
    ) == timedelta(hours=16, minutes=30)
