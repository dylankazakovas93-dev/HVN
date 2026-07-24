from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from hvn.acceptance_metrics import (
    close_path_efficiency,
    horizon_metrics,
    midpoint_crossings,
    range_overlap_share,
    residence_metrics,
)
from hvn.interactions import zone_from_prices
from hvn.models import Bar

NY = ZoneInfo("America/New_York")
ZONE = zone_from_prices("Z", Decimal("100"), Decimal("101"))


def bar(index: int, low: str, high: str, close: str) -> Bar:
    start = datetime(2025, 1, 7, 10, 0, tzinfo=NY) + timedelta(minutes=index)
    return Bar(
        f"M{index}-{low}-{high}-{close}",
        start + timedelta(minutes=1),
        Decimal(close),
        Decimal(high),
        Decimal(low),
        Decimal(close),
        Decimal(1),
        "NQH5",
    )


def test_inside_close_and_first_inside_probabilities():
    touch = bar(-1, "99.75", "100", "100")
    forward = [bar(i, "99.75", "100.25", "100" if i in {1, 7} else "99.75") for i in range(15)]
    result = horizon_metrics(touch, forward, ZONE)
    assert result.inside_close_share == Decimal(2) / Decimal(15)
    assert result.first_inside_close_5 is True
    assert result.first_inside_close_15 is True


def test_range_overlap_share_inclusive_tick_counts():
    assert range_overlap_share(bar(0, "99.75", "100.5", "100"), ZONE) == Decimal(3) / Decimal(4)


def test_zero_range_overlap_rule():
    assert range_overlap_share(bar(0, "100.25", "100.25", "100.25"), ZONE) == 1
    assert range_overlap_share(bar(0, "101", "101", "101"), ZONE) == 0


def test_midpoint_neutral_carry_and_crossing_count():
    sequence = [
        bar(0, "100.25", "100.25", "100.25"),
        bar(1, "100.5", "100.5", "100.5"),
        bar(2, "100.5", "100.5", "100.5"),
        bar(3, "100.75", "100.75", "100.75"),
        bar(4, "100.5", "100.5", "100.5"),
        bar(5, "100.25", "100.25", "100.25"),
    ]
    assert midpoint_crossings(sequence, ZONE) == 2


def test_path_efficiency_and_zero_denominator():
    touch = Decimal("100")
    moving = [bar(0, "101", "101", "101"), bar(1, "100", "100", "100"), bar(2, "102", "102", "102")]
    assert close_path_efficiency(touch, moving) == Decimal(2) / Decimal(4)
    flat = [bar(0, "100", "100", "100"), bar(1, "100", "100", "100")]
    assert close_path_efficiency(touch, flat) == 0


def test_continuous_residence_full_exit_and_reentry():
    forward = [
        bar(0, "99.75", "100.25", "100"),
        bar(1, "100", "100.75", "100.5"),
        bar(2, "101", "101.25", "101"),
        bar(3, "100.75", "101", "100.75"),
    ] + [bar(i, "101", "101", "101") for i in range(4, 63)]
    result = residence_metrics(
        forward, ZONE, atr_at_touch=Decimal(2), complete_followup_minutes=63
    )
    assert result.status == "OBSERVED"
    assert result.continuous_residence_minutes == 2
    assert result.continuous_residence_normalized == 4
    assert result.first_full_exit_side == "ABOVE"
    assert result.reentry_15 is True


def test_no_inside_close_and_right_censored_residence():
    none = residence_metrics(
        [bar(0, "99", "99.75", "99.75")],
        ZONE,
        atr_at_touch=Decimal(2),
        complete_followup_minutes=1,
    )
    assert none.status == "NO_INSIDE_CLOSE"
    assert none.continuous_residence_minutes is None
    censored = residence_metrics(
        [bar(0, "100", "100.5", "100"), bar(1, "100", "100.75", "100.5")],
        ZONE,
        atr_at_touch=Decimal(2),
        complete_followup_minutes=2,
    )
    assert censored.status == "RIGHT_CENSORED"
    assert censored.residence_censored

