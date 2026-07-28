"""Generation 4 touch detection, control selection and event assembly."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hvn.gen4_controls import (
    C01_NEUTRAL,
    C02_ACTIVITY_MATCHED,
    select_controls,
)
from hvn.gen4_pipeline import (
    events_for_interval,
    find_touches,
    measure_event,
    zone_population,
)
from hvn.models import Bar
from hvn.zones_v4 import classify_zones, profile_activity

from test_zones_v4 import _twin_peak_profile

LOW = Decimal("100.00")
HIGH = Decimal("103.00")
START = datetime(2019, 3, 4, 15, 0, tzinfo=UTC)


def bars(rows):
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


def test_consecutive_bars_inside_the_zone_are_one_touch():
    rows = [
        ("104", "105", "104"),   # outside, above
        ("101", "102", "101"),   # touch
        ("100", "102", "101"),   # still inside, same touch
        ("104", "105", "104"),   # left
        ("101", "102", "101"),   # a second, separate touch
    ]
    touches = find_touches(bars(rows), LOW, HIGH)
    assert len(touches) == 2
    assert [t.index for t in touches] == [1, 4]


def test_approach_side_comes_from_the_bar_before_the_touch():
    above = find_touches(bars([("104", "105", "104"), ("101", "102", "101")]), LOW, HIGH)
    assert above[0].approach_side == "APPROACH_FROM_ABOVE"
    below = find_touches(bars([("96", "97", "96"), ("101", "102", "101")]), LOW, HIGH)
    assert below[0].approach_side == "APPROACH_FROM_BELOW"


def test_a_bar_crossing_clean_through_is_not_a_close_inside():
    touches = find_touches(bars([("96", "97", "96"), ("99", "105", "105")]), LOW, HIGH)
    assert touches[0].touch_class == "CROSS_THROUGH"


def test_the_touch_bar_never_enters_a_forward_measurement():
    # The touch bar itself reaches 3 ATR up, but forward measurement starts at
    # the next bar, which does not.
    rows = [("96", "97", "96"), ("99", "109", "101")] + [("104", "104", "104")] * 90
    window = bars(rows)
    touch = find_touches(window, LOW, HIGH)[0]
    row = measure_event(window, touch, low=LOW, high=HIGH, atr=Decimal("2.00"))
    assert row["reached_3atr"] is False
    assert row["never_reached_3atr"] is True


def test_first_touch_and_retouches_are_separated():
    rows = (
        [("96", "97", "96"), ("101", "102", "101")]
        + [("104", "104", "104")] * 5
        + [("101", "102", "101")]
        + [("104", "104", "104")] * 80
    )
    window = bars(rows)
    events, summary = events_for_interval(
        window,
        interval_id="Z1",
        population="NONPOC",
        zone_class="NONPOC_HVN_ZONE",
        low=LOW,
        high=HIGH,
        atr=Decimal("2.00"),
        base={"year": 2019},
    )
    assert summary["touch_count"] == 2
    assert summary["retouch_count"] == 1
    assert summary["minutes_to_first_touch"] == 1
    assert [e["is_first_touch"] for e in events] == [True, False]


def test_an_untouched_interval_still_produces_a_summary_row():
    window = bars([("120", "121", "120")] * 30)
    events, summary = events_for_interval(
        window,
        interval_id="Z2",
        population="POC",
        zone_class="POC_HVN_ZONE",
        low=LOW,
        high=HIGH,
        atr=Decimal("2.00"),
        base={"year": 2019},
    )
    assert events == []
    assert summary["touched"] is False
    assert summary["touch_count"] == 0


def test_poc_and_nonpoc_populations_are_labelled_apart():
    assert zone_population("POC_HVN_ZONE") == "POC"
    assert zone_population("NONPOC_HVN_ZONE") == "NONPOC"
    assert zone_population("BROAD_ACTIVITY_DISTRIBUTION") == "OTHER"


# ---------------------------------------------------------------------------
# Controls


def test_controls_match_the_treated_zone_width_exactly():
    profile = _twin_peak_profile(10, 1)
    zones, activity = classify_zones(profile)
    accepted = [z for z in zones if z.accepted]
    treated = next(z for z in accepted if z.zone_class == "NONPOC_HVN_ZONE")
    controls = select_controls(profile, activity, accepted, treated, taken=set())
    assert controls, "expected at least one control"
    for control in controls:
        assert control.width_ticks == treated.width_ticks
        assert control.width_points == treated.width_points


def test_controls_never_overlap_an_accepted_zone_or_the_poc():
    profile = _twin_peak_profile(10, 1)
    zones, activity = classify_zones(profile)
    accepted = [z for z in zones if z.accepted]
    treated = next(z for z in accepted if z.zone_class == "NONPOC_HVN_ZONE")
    controls = select_controls(profile, activity, accepted, treated, taken=set())
    blocked = {profile.poc_index}
    for zone in accepted:
        blocked.update(range(zone.low_index, zone.high_index + 1))
    for control in controls:
        window = set(range(control.low_index, control.high_index + 1))
        assert not (window & blocked)


def test_an_activity_matched_control_sits_in_the_frozen_activity_band():
    profile = _twin_peak_profile(10, 1)
    zones, activity = classify_zones(profile)
    accepted = [z for z in zones if z.accepted]
    treated = next(z for z in accepted if z.zone_class == "NONPOC_HVN_ZONE")
    controls = select_controls(profile, activity, accepted, treated, taken=set())
    for control in controls:
        if control.control_family != C02_ACTIVITY_MATCHED:
            continue
        ratio = control.zone_activity_density / treated.zone_activity_density
        assert Decimal("0.80") <= ratio <= Decimal("1.25")


def test_control_families_are_labelled_and_do_not_reuse_ticks():
    profile = _twin_peak_profile(10, 1)
    zones, activity = classify_zones(profile)
    accepted = [z for z in zones if z.accepted]
    treated = next(z for z in accepted if z.zone_class == "NONPOC_HVN_ZONE")
    controls = select_controls(profile, activity, accepted, treated, taken=set())
    families = [c.control_family for c in controls]
    assert families[0] == C01_NEUTRAL
    assert len(set(families)) == len(families)
    seen: set[int] = set()
    for control in controls:
        window = set(range(control.low_index, control.high_index + 1))
        assert not (window & seen)
        seen |= window


def test_a_taken_window_is_not_reused_by_a_later_treated_zone():
    profile = _twin_peak_profile(10, 1)
    zones, activity = classify_zones(profile)
    accepted = [z for z in zones if z.accepted]
    treated = next(z for z in accepted if z.zone_class == "NONPOC_HVN_ZONE")
    first = select_controls(profile, activity, accepted, treated, taken=set())
    taken = set()
    for control in first:
        taken.update(range(control.low_index, control.high_index + 1))
    second = select_controls(profile, activity, accepted, treated, taken=taken)
    for control in second:
        window = set(range(control.low_index, control.high_index + 1))
        assert not (window & taken)


def test_control_selection_is_deterministic():
    profile = _twin_peak_profile(10, 1)
    zones, activity = classify_zones(profile)
    accepted = [z for z in zones if z.accepted]
    treated = next(z for z in accepted if z.zone_class == "NONPOC_HVN_ZONE")
    a = select_controls(profile, activity, accepted, treated, taken=set())
    b = select_controls(profile, activity, accepted, treated, taken=set())
    assert [(c.control_family, c.low_index, c.high_index) for c in a] == [
        (c.control_family, c.low_index, c.high_index) for c in b
    ]


def test_profile_activity_is_valid_for_the_fixture_used_here():
    activity = profile_activity(_twin_peak_profile(10, 1))
    assert activity.valid
