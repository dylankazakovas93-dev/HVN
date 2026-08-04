"""Rotation fixtures: distance and speed together, then persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hvn.models import Bar
from hvn.rotation import DOWN, UP, check_sustain, find_rotation, max_excursion

ATR = Decimal("2.00")
LOW = Decimal("100.00")
HIGH = Decimal("103.00")
START = datetime(2019, 3, 4, 15, 0, tzinfo=UTC)


def bars(rows):
    """(low, high, close) per bar, in order."""
    out = []
    for index, (low, high, close) in enumerate(rows):
        out.append(
            Bar(
                source_row_id=f"NQH9|{index}",
                close_time=START + timedelta(minutes=index + 1),
                open=Decimal(low),
                high=Decimal(high),
                low=Decimal(low),
                close=Decimal(close),
                volume=Decimal(10),
                symbol="NQH9",
            )
        )
    return out


def flat(price, count):
    return [(price, price, price)] * count


def rotate(**kwargs):
    return find_rotation(node_low=LOW, node_high=HIGH, atr=ATR, **kwargs)


# ---------------------------------------------------------------------------
# Distance and speed must hold together


def test_the_same_distance_counts_or_not_depending_on_the_deadline():
    # 2 ATR above the high edge is 103 + 4 = 107, reached on bar 5.
    rows = flat("104", 4) + [("106", "107", "107")] + flat("107", 20)
    forward = bars(rows)

    fast = rotate(forward=forward, distance_atr=Decimal(2), deadline_bars=3)
    slow = rotate(forward=forward, distance_atr=Decimal(2), deadline_bars=10)

    assert not fast.rotated, "five bars is not a three-bar rotation"
    assert slow.rotated and slow.bars_taken == 5


def test_a_small_drift_is_not_a_rotation_at_a_larger_distance():
    # 0.5 ATR above the edge is 104; price never exceeds it.
    forward = bars(flat("104", 20))
    small = rotate(forward=forward, distance_atr=Decimal("0.5"), deadline_bars=5)
    large = rotate(forward=forward, distance_atr=Decimal(3), deadline_bars=5)
    assert small.rotated
    assert not large.rotated and not large.censored


def test_the_rate_is_distance_reached_over_bars_taken():
    # 3 ATR above the edge is 109, reached on bar 3.
    rows = flat("104", 2) + [("108", "109", "109")] + flat("109", 20)
    result = rotate(forward=bars(rows), distance_atr=Decimal(3), deadline_bars=5)
    assert result.rotated and result.bars_taken == 3
    assert result.rate_atr_per_bar == Decimal(1)   # 3.00 ATR over 3 bars

    # The same distance taken in one bar is three times the rate.
    quick = rotate(
        forward=bars([("108", "109", "109")] + flat("109", 20)),
        distance_atr=Decimal(3),
        deadline_bars=5,
    )
    assert quick.rate_atr_per_bar == Decimal(3)


def test_a_downward_rotation_is_recorded_as_down():
    # 2 ATR below the low edge is 100 - 4 = 96.
    rows = [("96", "99", "96")] + flat("96", 20)
    result = rotate(forward=bars(rows), distance_atr=Decimal(2), deadline_bars=3)
    assert result.rotated and result.direction == DOWN


def test_a_bar_reaching_both_sides_takes_the_larger_excursion():
    rows = [("94", "110", "100")] + flat("100", 20)
    result = rotate(forward=bars(rows), distance_atr=Decimal(2), deadline_bars=3)
    # 110 is 3.5 ATR up, 94 is 3.0 ATR down.
    assert result.direction == UP


def test_too_few_bars_is_censoring_not_a_failed_rotation():
    short = rotate(forward=bars(flat("104", 2)), distance_atr=Decimal(2), deadline_bars=5)
    assert short.censored and not short.rotated

    complete = rotate(
        forward=bars(flat("104", 5)), distance_atr=Decimal(2), deadline_bars=5
    )
    assert not complete.censored and not complete.rotated


# ---------------------------------------------------------------------------
# Persistence


def test_a_rotation_that_holds_is_sustained():
    rows = [("108", "109", "109")] + flat("110", 20)
    forward = bars(rows)
    rotation = rotate(forward=forward, distance_atr=Decimal(3), deadline_bars=3)
    result = check_sustain(
        forward, rotation, node_low=LOW, node_high=HIGH, atr=ATR, horizon_bars=5
    )
    assert result.evaluated and result.sustained
    # 110 is 7 points above the 103 edge = 3.5 ATR, still beyond the 3 ATR mark.
    assert result.distance_at_horizon_atr == Decimal("3.5")


def test_a_rotation_that_gives_the_distance_back_is_not_sustained():
    rows = [("108", "109", "109")] + flat("104", 20)
    forward = bars(rows)
    rotation = rotate(forward=forward, distance_atr=Decimal(3), deadline_bars=3)
    result = check_sustain(
        forward, rotation, node_low=LOW, node_high=HIGH, atr=ATR, horizon_bars=5
    )
    assert result.evaluated and result.sustained is False
    assert result.distance_at_horizon_atr == Decimal("0.5")


def test_a_rotation_that_never_happened_has_nothing_to_sustain():
    forward = bars(flat("104", 30))
    rotation = rotate(forward=forward, distance_atr=Decimal(3), deadline_bars=5)
    result = check_sustain(
        forward, rotation, node_low=LOW, node_high=HIGH, atr=ATR, horizon_bars=5
    )
    assert not result.evaluated and result.sustained is None


def test_a_horizon_past_the_available_bars_is_not_evaluated():
    forward = bars([("108", "109", "109")] + flat("110", 2))
    rotation = rotate(forward=forward, distance_atr=Decimal(3), deadline_bars=3)
    result = check_sustain(
        forward, rotation, node_low=LOW, node_high=HIGH, atr=ATR, horizon_bars=20
    )
    assert not result.evaluated


def test_sustain_is_measured_from_the_rotation_bar_not_the_tap():
    # Rotation completes on bar 3; the horizon of 2 lands on bar 5, not bar 2.
    rows = flat("104", 2) + [("108", "109", "109")] + flat("104", 1) + flat("112", 10)
    forward = bars(rows)
    rotation = rotate(forward=forward, distance_atr=Decimal(3), deadline_bars=5)
    assert rotation.bars_taken == 3
    result = check_sustain(
        forward, rotation, node_low=LOW, node_high=HIGH, atr=ATR, horizon_bars=2
    )
    # Bar index 3 + 2 - 1 = 4, which closes at 112 -> 4.5 ATR above the edge.
    assert result.distance_at_horizon_atr == Decimal("4.5")
    assert result.sustained


# ---------------------------------------------------------------------------
# Continuous excursion, so the grid can be re-cut without recomputing


def test_max_excursion_records_the_furthest_point_and_its_speed():
    rows = flat("104", 2) + [("108", "111", "110")] + flat("104", 10)
    result = max_excursion(
        bars(rows), node_low=LOW, node_high=HIGH, atr=ATR, window_bars=10
    )
    assert result.evaluated
    # 111 is 8 points above the 103 edge = 4 ATR, on bar 3.
    assert result.max_distance_atr == Decimal(4)
    assert result.bars_to_max == 3
    assert result.rate_atr_per_bar == Decimal(4) / Decimal(3)
    assert result.direction == UP


def test_max_excursion_is_bounded_by_its_window():
    rows = flat("104", 5) + [("108", "115", "115")]
    inside = max_excursion(
        bars(rows), node_low=LOW, node_high=HIGH, atr=ATR, window_bars=5
    )
    outside = max_excursion(
        bars(rows), node_low=LOW, node_high=HIGH, atr=ATR, window_bars=6
    )
    assert inside.max_distance_atr == Decimal("0.5")
    assert outside.max_distance_atr == Decimal(6)


def test_an_empty_window_is_not_evaluated():
    assert not max_excursion(
        [], node_low=LOW, node_high=HIGH, atr=ATR, window_bars=5
    ).evaluated
