from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from hvn.models import AtrPoint, Bar, ProfileFamily, ProfileWindow

NY = ZoneInfo("America/New_York")


@pytest.fixture
def base_time() -> datetime:
    return datetime(2025, 1, 6, 9, 30, tzinfo=NY)


def make_bar(
    row: int,
    close_time: datetime,
    low: str,
    high: str,
    volume: str = "10",
    *,
    open_: str | None = None,
    close: str | None = None,
) -> Bar:
    low_d, high_d = Decimal(low), Decimal(high)
    return Bar(
        f"row-{row}",
        close_time + timedelta(minutes=1),
        Decimal(open_) if open_ else low_d,
        high_d,
        low_d,
        Decimal(close) if close else high_d,
        Decimal(volume),
    )


def simple_window(base: datetime, minutes: int = 5) -> ProfileWindow:
    end = base + timedelta(minutes=minutes)
    return ProfileWindow(ProfileFamily.OPENING_HOUR, base.date().isoformat(), base, end, end)


def fixed_atr(base: datetime, value: str = "10") -> tuple[AtrPoint, ...]:
    return (AtrPoint(base, Decimal(value)),)
