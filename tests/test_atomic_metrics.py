"""Generation 3 behaviour metrics, against hand-calculated bar paths.

Profiles here use 10-point bins starting at 1000 with ATR 40, so 0.25 ATR is
exactly 10 points and 0.10/0.50 ATR are 4 and 20 points. The atomic zone in the
standard fixture is bin 2, i.e. [1020, 1030).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from hvn.atomic import extract_atomic_hvns
from hvn.atomic_controls import C01_NEUTRAL, C02_MASS_MATCHED, select_controls
from hvn.atomic_departure import (
    ABOVE,
    BELOW,
    confirmed_departure,
    excursion_metrics,
)
from hvn.atomic_interactions import (
    APPROACH_FROM_ABOVE,
    APPROACH_FROM_BELOW,
    CLOSE_INSIDE,
    CROSS_THROUGH,
    START_INSIDE,
    WICK_ONLY_SAME_SIDE,
    first_interaction,
)
from hvn.atomic_proximity import proximity_metrics
from hvn.atomic_residence import residence_bucket, residence_metrics
from hvn.models import Bar

from test_atomic_extraction import build_profile

ATR = Decimal(40)
BASE = datetime(2021, 3, 1, 10, 0, tzinfo=timezone.utc)


def bar(minute: int, o, h, l, c) -> Bar:
    return Bar(
        f"row-{minute}",
        BASE + timedelta(minutes=minute + 1),
        Decimal(o), Decimal(h), Decimal(l), Decimal(c), Decimal(1), "NQH1",
    )


def flat(minute: int, price) -> Bar:
    return bar(minute, price, price, price, price)


def standard_atomic():
    return extract_atomic_hvns(build_profile([10, 10, 40, 10, 10]), Decimal("2.0"))[0]


# --- first interaction -------------------------------------------------------

def test_first_touch_from_below():
    atomic = standard_atomic()
    bars = (flat(0, 1000), flat(1, 1010), bar(2, 1015, 1022, 1015, 1018))
    result = first_interaction(atomic, bars, atr_value=ATR)
    assert result.touched
    assert result.approach_side == APPROACH_FROM_BELOW
    assert result.touch_bar_id == "row-2"
    assert result.forward_start_index == 3       # measurement starts after touch
    assert result.minute_from_interaction_start == 2


def test_first_touch_from_above():
    atomic = standard_atomic()
    bars = (flat(0, 1060), flat(1, 1045), bar(2, 1040, 1040, 1028, 1035))
    result = first_interaction(atomic, bars, atr_value=ATR)
    assert result.touched
    assert result.approach_side == APPROACH_FROM_ABOVE


def test_start_inside_when_first_bar_touches():
    atomic = standard_atomic()
    bars = (bar(0, 1025, 1026, 1024, 1025), flat(1, 1050))
    result = first_interaction(atomic, bars, atr_value=ATR)
    assert result.approach_side == START_INSIDE
    assert result.touch_class == CLOSE_INSIDE


def test_wick_only_touch_returns_to_the_approach_side():
    atomic = standard_atomic()
    bars = (flat(0, 1000), bar(1, 1010, 1023, 1008, 1012))
    result = first_interaction(atomic, bars, atr_value=ATR)
    assert result.approach_side == APPROACH_FROM_BELOW
    assert result.touch_class == WICK_ONLY_SAME_SIDE


def test_close_inside_touch():
    atomic = standard_atomic()
    bars = (flat(0, 1000), bar(1, 1010, 1026, 1008, 1025))
    assert first_interaction(atomic, bars, atr_value=ATR).touch_class == CLOSE_INSIDE


def test_cross_through_touch():
    atomic = standard_atomic()
    bars = (flat(0, 1000), bar(1, 1010, 1040, 1008, 1038))
    result = first_interaction(atomic, bars, atr_value=ATR)
    assert result.touch_class == CROSS_THROUGH
    assert result.approach_side == APPROACH_FROM_BELOW


def test_untouched_atomic_is_preserved_as_an_opportunity():
    atomic = standard_atomic()
    result = first_interaction(atomic, (flat(0, 1000), flat(1, 1005)), atr_value=ATR)
    assert not result.touched
    assert result.exclusion_reason == "never_touched"


def test_only_the_first_touch_is_used():
    atomic = standard_atomic()
    bars = (flat(0, 1000), flat(1, 1025), flat(2, 1000), flat(3, 1025))
    assert first_interaction(atomic, bars, atr_value=ATR).touch_bar_id == "row-1"


# --- proximity ---------------------------------------------------------------

def test_proximity_bands_and_distances():
    atomic = standard_atomic()
    # 1025 inside; 1032 is 2 pts outside (0.05 ATR); 1036 is 6 pts (0.15 ATR);
    # 1045 is 15 pts (0.375 ATR); 1060 is 30 pts (0.75 ATR).
    forward = (flat(0, 1025), flat(1, 1032), flat(2, 1036), flat(3, 1045), flat(4, 1060))
    result = proximity_metrics(atomic, forward, ATR, horizons=(5,))[0]
    assert result.complete and result.bars_observed == 5
    assert result.close_share["exact"] == Decimal(1) / Decimal(5)
    assert result.close_share["b010"] == Decimal(2) / Decimal(5)   # 1025, 1032
    assert result.close_share["b025"] == Decimal(3) / Decimal(5)   # + 1036
    assert result.close_share["b050"] == Decimal(4) / Decimal(5)   # + 1045
    assert result.median_distance_atr == Decimal("0.15")
    # (0 + 0.05 + 0.15 + 0.375 + 0.75) / 5
    assert result.mean_distance_atr == Decimal("0.265")
    assert result.p75_distance_atr == Decimal("0.375")
    assert result.p90_distance_atr == Decimal("0.60")


def test_distance_to_peak_centre_is_separate_from_distance_to_zone():
    atomic = standard_atomic()
    forward = (flat(0, 1025), flat(1, 1035))
    result = proximity_metrics(atomic, forward, ATR, horizons=(2,))[0]
    # zone distances 0 and 5/40; peak-centre distances 0 and 10/40
    assert result.mean_distance_atr == Decimal("0.0625")
    assert result.mean_peak_distance_atr == Decimal("0.125")


def test_incomplete_horizon_is_marked_censored_not_partial():
    atomic = standard_atomic()
    result = proximity_metrics(atomic, (flat(0, 1025),), ATR, horizons=(5,))[0]
    assert not result.complete
    assert result.bars_observed == 1


def test_peak_crossings_and_side_changes():
    atomic = standard_atomic()          # peak price 1025
    forward = (flat(0, 1030), flat(1, 1020), flat(2, 1030), flat(3, 1031))
    result = proximity_metrics(atomic, forward, ATR, horizons=(4,))[0]
    assert result.peak_crossings == 2
    assert result.side_changes == 2


def test_revisit_after_leaving_a_band():
    atomic = standard_atomic()
    # inside, outside, inside -> revisited
    forward = (flat(0, 1025), flat(1, 1090), flat(2, 1025))
    assert proximity_metrics(atomic, forward, ATR, horizons=(3,))[0] \
        .revisit_after_leaving["b025"] is True
    # inside then gone -> not revisited
    forward = (flat(0, 1025), flat(1, 1090), flat(2, 1090))
    assert proximity_metrics(atomic, forward, ATR, horizons=(3,))[0] \
        .revisit_after_leaving["b025"] is False
    # never entered -> undefined
    forward = (flat(0, 1090), flat(1, 1090))
    assert proximity_metrics(atomic, forward, ATR, horizons=(2,))[0] \
        .revisit_after_leaving["b025"] is None


# --- residence ---------------------------------------------------------------

def test_total_and_longest_residence():
    atomic = standard_atomic()
    # b025 band is [1010, 1040): in, in, out, in, in, in
    forward = (flat(0, 1025), flat(1, 1030), flat(2, 1090),
               flat(3, 1025), flat(4, 1026), flat(5, 1027))
    band = {r.band: r for r in residence_metrics(atomic, forward, ATR)}["b025"]
    assert band.total_minutes == 5
    assert band.longest_run_minutes == 3
    assert band.continuous_residence_minutes == 2      # first run only
    assert band.first_entry_minute == 0
    assert band.first_exit_minute == 2
    assert band.reentry_count == 1
    assert band.first_reentry_delay_minutes == 1
    assert band.right_censored                          # still inside at the end
    assert not band.never_entered and not band.never_left


def test_never_entered_and_never_left():
    atomic = standard_atomic()
    away = (flat(0, 1200), flat(1, 1200))
    band = {r.band: r for r in residence_metrics(atomic, away, ATR)}["b025"]
    assert band.never_entered and band.total_minutes == 0
    assert band.residence_bucket == "B0"

    stayed = (flat(0, 1025), flat(1, 1026), flat(2, 1027))
    band = {r.band: r for r in residence_metrics(atomic, stayed, ATR)}["b025"]
    assert band.never_left and band.right_censored
    assert band.continuous_residence_minutes == 3


def test_residence_buckets():
    assert residence_bucket(0) == "B0"
    assert residence_bucket(2) == "B0"
    assert residence_bucket(3) == "B1"
    assert residence_bucket(5) == "B1"
    assert residence_bucket(6) == "B2"
    assert residence_bucket(10) == "B2"
    assert residence_bucket(11) == "B3"
    assert residence_bucket(20) == "B3"
    assert residence_bucket(21) == "B4"
    assert residence_bucket(500) == "B4"


def test_normalized_residence_is_preserved():
    atomic = standard_atomic()
    forward = (flat(0, 1025), flat(1, 1026), flat(2, 1090))
    band = {r.band: r for r in residence_metrics(atomic, forward, ATR)}["b025"]
    # 2 minutes * ATR 40 / width 10 points
    assert band.normalized_residence == Decimal(8)


# --- departure ---------------------------------------------------------------

def test_two_consecutive_same_side_closes_confirm_departure():
    atomic = standard_atomic()          # b025 band [1010, 1040)
    forward = (flat(0, 1025), flat(1, 1050), flat(2, 1055), flat(3, 1060))
    result = confirmed_departure(atomic, forward, ATR)
    assert result.departed and result.side == ABOVE
    assert result.confirm_index == 2                 # second confirming bar
    assert result.excursion_start_index == 3
    assert result.departed_boundary == Decimal(1040)
    assert result.minutes_to_departure == 3


def test_opposite_side_closes_do_not_confirm_a_departure():
    atomic = standard_atomic()
    # above, below, above, below -> never two consecutive on one side
    forward = (flat(0, 1050), flat(1, 1000), flat(2, 1050), flat(3, 1000))
    result = confirmed_departure(atomic, forward, ATR)
    assert not result.departed and result.right_censored


def test_returning_inside_resets_the_streak():
    atomic = standard_atomic()
    forward = (flat(0, 1050), flat(1, 1025), flat(2, 1050), flat(3, 1055))
    result = confirmed_departure(atomic, forward, ATR)
    assert result.departed and result.confirm_index == 3


def test_one_close_sensitivity_departure_is_earlier():
    atomic = standard_atomic()
    forward = (flat(0, 1050), flat(1, 1025), flat(2, 1050), flat(3, 1055))
    single = confirmed_departure(atomic, forward, ATR, consecutive=1)
    assert single.departed and single.confirm_index == 0
    assert single.side == ABOVE


def test_departure_below():
    atomic = standard_atomic()
    forward = (flat(0, 1000), flat(1, 995))
    result = confirmed_departure(atomic, forward, ATR)
    assert result.departed and result.side == BELOW
    assert result.departed_boundary == Decimal(1010)


def test_wider_band_departs_later_than_narrower_band():
    atomic = standard_atomic()
    # 1036 is outside +/-0.10 (1034) but inside +/-0.25 (1040)
    forward = (flat(0, 1036), flat(1, 1036), flat(2, 1050), flat(3, 1055))
    narrow = confirmed_departure(atomic, forward, ATR, expansion=Decimal("0.10"))
    primary = confirmed_departure(atomic, forward, ATR)
    assert narrow.confirm_index == 1
    assert primary.confirm_index == 3


# --- excursion ---------------------------------------------------------------

def test_excursion_starts_after_confirmation_and_measures_direction():
    atomic = standard_atomic()
    # confirm ABOVE at index 2; excursion path starts at index 3
    forward = (
        flat(0, 1025), flat(1, 1050), flat(2, 1055),
        bar(3, 1060, 1070, 1058, 1065),
        bar(4, 1065, 1080, 1060, 1075),
    )
    departure = confirmed_departure(atomic, forward, ATR)
    assert departure.excursion_start_index == 3
    result = excursion_metrics(atomic, forward, ATR, departure, horizons=(2,))[0]
    assert result.bars_observed == 2
    # boundary 1040; last close 1075 -> 35 points -> 0.875 ATR
    assert result.directional_displacement_atr == Decimal("0.875")
    # best high 1080 -> 40 points -> 1.0 ATR
    assert result.mfe_atr == Decimal(1)
    # worst low 1058 -> 18 points above boundary, still favourable -> +0.45
    assert result.mae_atr == Decimal("0.45")
    assert result.average_speed_atr_per_minute == Decimal("0.875") / Decimal(2)
    assert result.average_speed_points_per_minute == Decimal("17.5")


def test_adverse_excursion_is_negative_when_price_returns_past_the_boundary():
    atomic = standard_atomic()
    forward = (
        flat(0, 1050), flat(1, 1055),
        bar(2, 1050, 1060, 1030, 1035),
    )
    departure = confirmed_departure(atomic, forward, ATR)
    result = excursion_metrics(atomic, forward, ATR, departure, horizons=(1,))[0]
    # low 1030 is 10 points below the 1040 boundary -> -0.25 ATR
    assert result.mae_atr == Decimal("-0.25")


def test_time_to_thresholds():
    atomic = standard_atomic()
    forward = (
        flat(0, 1050), flat(1, 1055),
        bar(2, 1041, 1050, 1041, 1050),   # +10 pts  = 0.25 ATR
        bar(3, 1050, 1060, 1050, 1060),   # +20 pts  = 0.50 ATR
        bar(4, 1060, 1120, 1060, 1120),   # +80 pts  = 2.00 ATR
    )
    departure = confirmed_departure(atomic, forward, ATR)
    result = excursion_metrics(atomic, forward, ATR, departure, horizons=(3,))[0]
    times = result.minutes_to_threshold
    assert times["0.25"] == 1
    assert times["0.50"] == 2
    assert times["1.00"] == 3
    assert times["2.00"] == 3


def test_reclaim_revisit_and_opposite_side_traversal():
    atomic = standard_atomic()
    forward = (
        flat(0, 1050), flat(1, 1055),
        flat(2, 1035),      # back inside the +/-0.25 band -> reclaim
        flat(3, 1025),      # inside the exact zone -> revisit
        flat(4, 1005),      # below the band -> opposite-side traversal
    )
    departure = confirmed_departure(atomic, forward, ATR)
    result = excursion_metrics(atomic, forward, ATR, departure, horizons=(3,))[0]
    assert result.reclaimed_band
    assert result.revisited_exact_zone
    assert result.crossed_to_opposite_side


def test_max_rolling_five_minute_speed():
    atomic = standard_atomic()
    forward = (
        flat(0, 1050), flat(1, 1055),
        flat(2, 1060), flat(3, 1060), flat(4, 1060), flat(5, 1060),
        flat(6, 1100),
    )
    departure = confirmed_departure(atomic, forward, ATR)
    result = excursion_metrics(atomic, forward, ATR, departure, horizons=(5,))[0]
    # the only 5-bar window runs 1060 -> 1100 = 40 pts = 1 ATR over 5 minutes
    assert result.max_rolling_5m_speed_atr_per_minute == Decimal(1) / Decimal(5)


def test_no_departure_yields_no_excursion():
    atomic = standard_atomic()
    departure = confirmed_departure(atomic, (flat(0, 1025),), ATR)
    assert excursion_metrics(atomic, (flat(0, 1025),), ATR, departure) == ()


# --- controls ----------------------------------------------------------------

def test_neutral_and_mass_matched_controls_are_distinct_families():
    profile = build_profile([9, 10, 40, 11, 9, 10, 30, 9, 10, 12], atr="40")
    atomics = extract_atomic_hvns(profile, Decimal("2.0"))
    atomic = next(a for a in atomics if a.start_bin_index == 2)
    controls = select_controls(profile, atomic, atomics)
    families = {c.control_family for c in controls}
    assert families == {C01_NEUTRAL, C02_MASS_MATCHED}
    for control in controls:
        assert control.width_bins == atomic.width_bins
        span = range(control.start_bin_index, control.end_bin_index + 1)
        assert profile.poc_bin_index not in span
        for other in atomics:
            assert not (
                control.start_bin_index <= other.end_bin_index
                and other.start_bin_index <= control.end_bin_index
            )


def test_mass_matched_control_is_the_closest_eligible_weight():
    profile = build_profile([9, 10, 40, 11, 9, 10, 38, 9, 10, 12], atr="40")
    atomics = extract_atomic_hvns(profile, Decimal("2.0"))
    atomic = next(a for a in atomics if a.start_bin_index == 2)
    controls = {c.control_family: c for c in select_controls(profile, atomic, atomics)}
    mass = controls[C02_MASS_MATCHED]
    eligible = [
        b.profile_weight for b in profile.bins
        if b.bin_index not in {1, 2, 3, 5, 6, 7} and b.bin_index != profile.poc_bin_index
    ]
    assert all(
        abs(mass.window_weight - atomic.peak_weight) <= abs(w - atomic.peak_weight)
        for w in eligible
    )


def test_control_zone_supports_the_same_geometry_as_an_atomic_zone():
    profile = build_profile([9, 10, 40, 11, 9, 10, 12, 9], atr="40")
    atomics = extract_atomic_hvns(profile, Decimal("2.0"))
    control = select_controls(profile, atomics[0], atomics)[0]
    assert control.contains(control.control_low)
    assert not control.contains(control.control_high)
    assert control.distance_atr(control.control_low - Decimal(10), ATR) == Decimal("0.25")
    low, high = control.band(Decimal("0.25"), ATR)
    assert high - low == control.width_points + Decimal(20)


# --- causality ---------------------------------------------------------------

def test_no_future_bar_can_change_event_classification():
    """Classification must depend only on bars up to and including the touch."""
    atomic = standard_atomic()
    prefix = (flat(0, 1000), bar(1, 1010, 1023, 1008, 1012))
    for suffix in ((), (flat(2, 1200),), (flat(2, 900), flat(3, 1025))):
        result = first_interaction(atomic, prefix + suffix, atr_value=ATR)
        assert result.touch_bar_id == "row-1"
        assert result.approach_side == APPROACH_FROM_BELOW
        assert result.touch_class == WICK_ONLY_SAME_SIDE
        assert result.forward_start_index == 2
