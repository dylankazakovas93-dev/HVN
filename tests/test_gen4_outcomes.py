"""Generation 4 displacement, envelope and continuation fixtures.

Every expectation is hand-derived from
`research/hvn/STAGE_02_GENERATION_4_AMENDMENT_02.md`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hvn.gen4_outcomes import (
    DOWN,
    UP,
    bar_count_distribution,
    continuation,
    displacement,
    distance_from_zone_atr,
    envelope_residence,
    interaction_session,
    median_bars,
    returned_inside,
)
from hvn.models import Bar

ATR = Decimal("2.00")
ZONE_LOW = Decimal("100.00")
ZONE_HIGH = Decimal("103.00")
START = datetime(2019, 3, 4, 15, 0, tzinfo=UTC)


def bars(rows: list[tuple[str, str, str]]) -> list[Bar]:
    """(low, high, close) per minute, in order."""
    out = []
    for minute, (low, high, close) in enumerate(rows):
        out.append(
            Bar(
                source_row_id=f"NQH9|{minute}",
                close_time=START + timedelta(minutes=minute + 1),
                open=Decimal(low),
                high=Decimal(high),
                low=Decimal(low),
                close=Decimal(close),
                volume=Decimal(10),
                symbol="NQH9",
            )
        )
    return out


def flat(price: str, count: int) -> list[tuple[str, str, str]]:
    return [(price, price, price)] * count


# ---------------------------------------------------------------------------
# Session labelling


def test_every_session_bucket_is_reachable_and_disjoint():
    ny = datetime(2019, 3, 4, tzinfo=UTC)

    def at(hour, minute=0):
        from zoneinfo import ZoneInfo

        return datetime(2019, 3, 4, hour, minute, tzinfo=ZoneInfo("America/New_York"))

    assert interaction_session(at(19)) == "ETH_EVENING"
    assert interaction_session(at(3)) == "ETH_OVERNIGHT"
    assert interaction_session(at(9, 30)) == "RTH_OPEN"
    assert interaction_session(at(10, 29)) == "RTH_OPEN"
    assert interaction_session(at(10, 30)) == "RTH_MORNING"
    assert interaction_session(at(12)) == "RTH_MIDDAY"
    assert interaction_session(at(14)) == "RTH_AFTERNOON"
    assert interaction_session(at(16)) == "OUT_OF_SESSION"
    assert ny.tzinfo is UTC


# ---------------------------------------------------------------------------
# Distance


def test_distance_is_zero_inside_the_zone_and_measured_from_the_nearest_edge():
    assert distance_from_zone_atr(Decimal("101"), ZONE_LOW, ZONE_HIGH, ATR) == 0
    # 2 points above the high edge, ATR 2.00 -> 1.00 ATR.
    assert distance_from_zone_atr(Decimal("105"), ZONE_LOW, ZONE_HIGH, ATR) == 1
    # 4 points below the low edge -> 2.00 ATR.
    assert distance_from_zone_atr(Decimal("96"), ZONE_LOW, ZONE_HIGH, ATR) == 2
    # The half-open convention: the high edge itself is outside.
    assert distance_from_zone_atr(Decimal("103"), ZONE_LOW, ZONE_HIGH, ATR) == 0


# ---------------------------------------------------------------------------
# Displacement


def test_bars_to_threshold_counts_from_the_first_bar_after_the_touch():
    # 3 ATR above the high edge is 103 + 6 = 109.
    rows = flat("104", 3) + [("108", "109", "109")]
    result = displacement(
        bars(rows),
        zone_low=ZONE_LOW,
        zone_high=ZONE_HIGH,
        atr=ATR,
        threshold_atr=Decimal("3"),
        window_complete=True,
    )
    assert result.reached
    assert result.bars_to_threshold == 4
    assert result.direction == UP
    assert not result.censored


def test_a_threshold_reached_downward_is_recorded_as_down():
    # 3 ATR below the low edge is 100 - 6 = 94.
    rows = [("94", "99", "94")]
    result = displacement(
        bars(rows),
        zone_low=ZONE_LOW,
        zone_high=ZONE_HIGH,
        atr=ATR,
        threshold_atr=Decimal("3"),
        window_complete=True,
    )
    assert result.reached and result.direction == DOWN
    assert result.bars_to_threshold == 1


def test_a_bar_reaching_both_sides_resolves_to_the_larger_excursion():
    # High 110 is 3.5 ATR up; low 94 is exactly 3.0 ATR down. Up is larger.
    result = displacement(
        bars([("94", "110", "100")]),
        zone_low=ZONE_LOW,
        zone_high=ZONE_HIGH,
        atr=ATR,
        threshold_atr=Decimal("3"),
        window_complete=True,
    )
    assert result.direction == UP

    # An exact tie resolves DOWN, deterministically: 109 up and 94 down are both
    # exactly 3.00 ATR.
    tie = displacement(
        bars([("94", "109", "100")]),
        zone_low=ZONE_LOW,
        zone_high=ZONE_HIGH,
        atr=ATR,
        threshold_atr=Decimal("3"),
        window_complete=True,
    )
    assert tie.direction == DOWN


def test_never_reached_and_censored_are_different_facts():
    complete = displacement(
        bars(flat("104", 30)),
        zone_low=ZONE_LOW,
        zone_high=ZONE_HIGH,
        atr=ATR,
        threshold_atr=Decimal("3"),
        window_complete=True,
    )
    assert complete.never_reached and not complete.censored

    cut_short = displacement(
        bars(flat("104", 3)),
        zone_low=ZONE_LOW,
        zone_high=ZONE_HIGH,
        atr=ATR,
        threshold_atr=Decimal("3"),
        window_complete=False,
    )
    assert cut_short.censored and not cut_short.never_reached


def test_five_atr_is_not_reached_by_a_three_atr_move():
    rows = [("108", "109", "109")]
    three = displacement(
        bars(rows), zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        threshold_atr=Decimal("3"), window_complete=True,
    )
    five = displacement(
        bars(rows), zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        threshold_atr=Decimal("5"), window_complete=True,
    )
    assert three.reached and not five.reached


# ---------------------------------------------------------------------------
# Envelope residence


def test_envelope_eligibility_uses_the_touch_close_only():
    forward = bars(flat("104", 10))
    far = envelope_residence(
        forward,
        touch_close=Decimal("110"),  # 3.5 ATR from the edge
        zone_low=ZONE_LOW,
        zone_high=ZONE_HIGH,
        atr=ATR,
        window_complete=True,
    )
    assert not far.eligible

    near = envelope_residence(
        forward,
        touch_close=Decimal("104"),  # 0.5 ATR from the edge
        zone_low=ZONE_LOW,
        zone_high=ZONE_HIGH,
        atr=ATR,
        window_complete=True,
    )
    assert near.eligible


def test_envelope_minutes_count_until_the_three_atr_boundary_is_crossed():
    rows = flat("104", 5) + [("108", "109", "109")]
    result = envelope_residence(
        bars(rows),
        touch_close=Decimal("104"),
        zone_low=ZONE_LOW,
        zone_high=ZONE_HIGH,
        atr=ATR,
        window_complete=True,
    )
    assert result.left_envelope
    assert result.minutes_inside == 5


def test_an_event_that_never_leaves_the_envelope_is_censored_when_cut_short():
    result = envelope_residence(
        bars(flat("104", 4)),
        touch_close=Decimal("104"),
        zone_low=ZONE_LOW,
        zone_high=ZONE_HIGH,
        atr=ATR,
        window_complete=False,
    )
    assert result.eligible and not result.left_envelope
    assert result.censored and result.minutes_inside == 4


# ---------------------------------------------------------------------------
# Continuation


def test_continuation_is_measured_from_the_crossing_bar_close():
    # Bar 1 crosses 3 ATR up at 109; price keeps going to 113 fifteen bars later.
    rows = [("108", "109", "109")] + flat("110", 14) + [("113", "113", "113")]
    forward = bars(rows)
    crossing = displacement(
        forward, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        threshold_atr=Decimal("3"), window_complete=True,
    )
    result = continuation(
        forward, crossing, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        horizon_minutes=15,
    )
    assert result.evaluated and result.continued
    # 113 is 10 points above the 103 edge = 5.00 ATR.
    assert result.displacement_atr == Decimal(5)


def test_a_reversal_is_not_counted_as_continuation():
    rows = [("108", "109", "109")] + flat("104", 15)
    forward = bars(rows)
    crossing = displacement(
        forward, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        threshold_atr=Decimal("3"), window_complete=True,
    )
    result = continuation(
        forward, crossing, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        horizon_minutes=15,
    )
    assert result.evaluated and result.continued is False


def test_a_horizon_past_the_available_bars_is_not_evaluated():
    forward = bars([("108", "109", "109")] + flat("110", 3))
    crossing = displacement(
        forward, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        threshold_atr=Decimal("3"), window_complete=True,
    )
    result = continuation(
        forward, crossing, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        horizon_minutes=15,
    )
    assert not result.evaluated
    assert result.continued is None


def test_an_event_that_never_crossed_is_not_evaluated_for_continuation():
    forward = bars(flat("104", 30))
    crossing = displacement(
        forward, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        threshold_atr=Decimal("3"), window_complete=True,
    )
    result = continuation(
        forward, crossing, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        horizon_minutes=15,
    )
    assert not result.evaluated


def test_a_return_inside_the_zone_is_detected_after_the_crossing():
    rows = [("108", "109", "109")] + flat("110", 3) + [("101", "102", "101")]
    forward = bars(rows)
    crossing = displacement(
        forward, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        threshold_atr=Decimal("3"), window_complete=True,
    )
    came_back, minutes = returned_inside(
        forward, crossing, zone_low=ZONE_LOW, zone_high=ZONE_HIGH
    )
    assert came_back and minutes == 4


# ---------------------------------------------------------------------------
# Distribution reporting


def test_the_bar_distribution_is_exhaustive_and_sums_to_one_hundred_percent():
    results = []
    for bar_count in (1, 1, 2, 7, 45):
        rows = flat("104", bar_count - 1) + [("108", "109", "109")]
        results.append(
            displacement(
                bars(rows), zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
                threshold_atr=Decimal("3"), window_complete=True,
            )
        )
    results.append(
        displacement(
            bars(flat("104", 30)), zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
            threshold_atr=Decimal("3"), window_complete=True,
        )
    )
    results.append(
        displacement(
            bars(flat("104", 2)), zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
            threshold_atr=Decimal("3"), window_complete=False,
        )
    )
    rows = bar_count_distribution(results)
    assert sum(r["events"] for r in rows) == 7
    assert sum(r["share_pct"] for r in rows) == Decimal("100.00")
    by_label = {r["bars"]: r["events"] for r in rows}
    assert by_label["1"] == 2
    assert by_label["2"] == 1
    assert by_label["6-10"] == 1
    assert by_label["21-60"] == 1
    assert by_label["never_reached"] == 1
    assert by_label["censored"] == 1
    assert median_bars(results) == 2


def test_an_empty_population_produces_no_distribution_rows():
    assert bar_count_distribution([]) == []
    assert median_bars([]) is None


# ---------------------------------------------------------------------------
# Amendment 03: capped-window displacement and band residence

from hvn.gen4_outcomes import (  # noqa: E402
    band_residence,
    continuation_after_exit,
    excursion_at_horizon,
)


def test_a_capped_window_cannot_saturate_the_way_an_open_window_does():
    """Price reaches 3 ATR at bar 40, so a 15-minute window must not see it."""
    rows = flat("104", 39) + [("108", "109", "109")] + flat("109", 40)
    forward = bars(rows)
    short = excursion_at_horizon(
        forward, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR, horizon_minutes=15
    )
    assert short.evaluated
    assert short.max_abs_atr == Decimal("0.5")   # 104 is 1 point above 103
    long = excursion_at_horizon(
        forward, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR, horizon_minutes=60
    )
    assert long.max_abs_atr == Decimal(3)


def test_excursion_reports_both_sides_and_the_signed_close():
    rows = [("96", "105", "104")] + flat("104", 14)
    result = excursion_at_horizon(
        bars(rows), zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR, horizon_minutes=15
    )
    assert result.max_up_atr == Decimal(1)      # 105 is 2 points above 103
    assert result.max_down_atr == Decimal(2)    # 96 is 4 points below 100
    assert result.max_abs_atr == Decimal(2)
    assert result.net_close_atr == Decimal("0.5")


def test_a_close_inside_the_zone_has_zero_net_displacement():
    result = excursion_at_horizon(
        bars(flat("101", 15)),
        zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR, horizon_minutes=15,
    )
    assert result.net_close_atr == 0


def test_a_short_window_is_not_evaluated_rather_than_scored_early():
    result = excursion_at_horizon(
        bars(flat("104", 9)),
        zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR, horizon_minutes=15,
    )
    assert not result.evaluated
    assert result.max_abs_atr is None


def test_band_residence_counts_minutes_until_the_five_atr_boundary():
    # 5 ATR above the high edge is 103 + 10 = 113.
    rows = flat("104", 6) + [("112", "113", "113")]
    result = band_residence(
        bars(rows), zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        window_complete=True,
    )
    assert result.left_band
    assert result.minutes_inside == 6
    assert result.exit_direction == UP


def test_band_residence_applies_to_every_touch_not_only_near_closes():
    """Unlike the envelope metric there is no closeness precondition."""
    rows = flat("110", 3) + [("112", "113", "113")]
    result = band_residence(
        bars(rows), zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        window_complete=True,
    )
    assert result.left_band and result.minutes_inside == 3


def test_an_event_that_never_leaves_the_band_is_censored_when_cut_short():
    result = band_residence(
        bars(flat("104", 5)), zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        window_complete=False,
    )
    assert not result.left_band and result.censored
    assert result.minutes_inside == 5
    assert result.breakout_volume_ratio is None


def test_the_breakout_volume_ratio_compares_the_exit_bar_to_the_band():
    quiet = bars(flat("104", 4))
    loud = Bar(
        source_row_id="NQH9|4",
        close_time=START + timedelta(minutes=5),
        open=Decimal("112"), high=Decimal("113"),
        low=Decimal("112"), close=Decimal("113"),
        volume=Decimal(50), symbol="NQH9",
    )
    result = band_residence(
        quiet + [loud], zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        window_complete=True,
    )
    # The four band bars each carry volume 10, so the median is 10.
    assert result.breakout_volume_ratio == Decimal(5)


def test_continuation_after_exit_is_measured_from_the_exit_bar():
    rows = flat("104", 3) + [("112", "113", "113")] + flat("116", 15)
    forward = bars(rows)
    residence = band_residence(
        forward, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR, window_complete=True
    )
    result = continuation_after_exit(
        forward, residence, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        horizon_minutes=15,
    )
    assert result.evaluated and result.continued
    # 116 is 13 points above the 103 edge = 6.5 ATR.
    assert result.displacement_atr == Decimal("6.5")


def test_an_event_that_never_left_the_band_has_no_continuation():
    forward = bars(flat("104", 30))
    residence = band_residence(
        forward, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR, window_complete=True
    )
    result = continuation_after_exit(
        forward, residence, zone_low=ZONE_LOW, zone_high=ZONE_HIGH, atr=ATR,
        horizon_minutes=15,
    )
    assert not result.evaluated
