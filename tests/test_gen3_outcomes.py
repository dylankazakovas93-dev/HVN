"""Generation 3 outcome metrics — hand-calculated fixtures.

Node is [1000, 1010) throughout: 10 points wide, 40 ticks. ATR is 40, so
+/- 1 ATR gives the band [960, 1050).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from hvn.gen3_outcomes import (
    ABOVE,
    APPROACH_FROM_ABOVE,
    APPROACH_FROM_BELOW,
    BELOW,
    INSIDE,
    OPPOSITE_SIDE_TRAVERSAL,
    SAME_SIDE_REJECTION,
    acceptance_metrics,
    activity_metrics,
    close_state,
    confirmed_departure,
    excursion_metrics,
    market_rate_metrics,
    overlap_share,
    residence_metrics,
)
from hvn.models import Bar

LOW, HIGH, ATR = Decimal(1000), Decimal(1010), Decimal(40)
BASE = datetime(2019, 3, 1, 10, 0, tzinfo=timezone.utc)


def bar(i, o, h, l, c, volume="10") -> Bar:
    return Bar(f"r{i}", BASE + timedelta(minutes=i + 1), Decimal(o), Decimal(h),
               Decimal(l), Decimal(c), Decimal(volume), "NQH9")


def flat(i, price, volume="10") -> Bar:
    return bar(i, price, price, price, price, volume)


# --- state and overlap -------------------------------------------------------

def test_close_state_uses_half_open_bounds():
    assert close_state(Decimal(999), LOW, HIGH) == BELOW
    assert close_state(Decimal(1000), LOW, HIGH) == INSIDE     # inclusive low
    assert close_state(Decimal(1009), LOW, HIGH) == INSIDE
    assert close_state(Decimal(1010), LOW, HIGH) == ABOVE      # exclusive high


def test_range_overlap_share_including_zero_range_bars():
    assert overlap_share(bar(0, 1000, 1010, 1000, 1005), LOW, HIGH) == 1
    # half the bar's 20-point range lies inside
    assert overlap_share(bar(1, 1000, 1010, 990, 1005), LOW, HIGH) == Decimal("0.5")
    assert overlap_share(bar(2, 1020, 1030, 1020, 1025), LOW, HIGH) == 0
    assert overlap_share(flat(3, 1005), LOW, HIGH) == 1        # zero range inside
    assert overlap_share(flat(4, 1020), LOW, HIGH) == 0        # zero range outside


# --- acceptance --------------------------------------------------------------

def test_inside_close_share_and_first_inside_close():
    forward = (flat(0, 1020), flat(1, 1005), flat(2, 1006), flat(3, 1030), flat(4, 1002))
    r = acceptance_metrics(forward, LOW, HIGH, horizons=(5,))[0]
    assert r.complete and r.bars_observed == 5
    assert r.inside_close_share == Decimal(3) / Decimal(5)
    assert r.first_inside_close_minute == 2          # 1-indexed forward minute


def test_incomplete_horizon_is_flagged():
    r = acceptance_metrics((flat(0, 1005),), LOW, HIGH, horizons=(30,))[0]
    assert not r.complete and r.bars_observed == 1


def test_midpoint_crossings_carry_neutral_closes_forward():
    # midpoint 1005; sequence above, exactly-at, below -> one crossing
    forward = (flat(0, 1008), flat(1, 1005), flat(2, 1002))
    assert acceptance_metrics(forward, LOW, HIGH, horizons=(3,))[0].midpoint_crossings == 1
    forward = (flat(0, 1008), flat(1, 1002), flat(2, 1008), flat(3, 1002))
    assert acceptance_metrics(forward, LOW, HIGH, horizons=(4,))[0].midpoint_crossings == 3


def test_full_rotation_requires_an_intervening_node_interaction():
    # below, inside, above -> one completed rotation
    forward = (flat(0, 990), flat(1, 1005), flat(2, 1020))
    r = acceptance_metrics(forward, LOW, HIGH, horizons=(3,))[0]
    assert r.full_rotation_count == 1 and r.any_rotation
    # below then straight above with no node interaction -> not a rotation
    forward = (flat(0, 990), flat(1, 1020))
    r = acceptance_metrics(forward, LOW, HIGH, horizons=(2,))[0]
    assert r.full_rotation_count == 0 and not r.any_rotation


def test_close_path_efficiency():
    # straight line: net 20 over travel 20 -> 1
    forward = (flat(0, 1000), flat(1, 1010), flat(2, 1020))
    assert acceptance_metrics(forward, LOW, HIGH, horizons=(3,))[0].close_path_efficiency == 1
    # out and back: net 0 -> 0
    forward = (flat(0, 1000), flat(1, 1020), flat(2, 1000))
    assert acceptance_metrics(forward, LOW, HIGH, horizons=(3,))[0].close_path_efficiency == 0
    # no movement at all -> 0, never a division error
    forward = (flat(0, 1005), flat(1, 1005))
    assert acceptance_metrics(forward, LOW, HIGH, horizons=(2,))[0].close_path_efficiency == 0


# --- residence ---------------------------------------------------------------

def test_residence_runs_reentries_and_normalization():
    forward = (flat(0, 1005), flat(1, 1006), flat(2, 1030),
               flat(3, 1004), flat(4, 1003), flat(5, 1002))
    r = residence_metrics(forward, LOW, HIGH, ATR, horizons=(6,))[0]
    assert r.inside_residence_minutes == 5
    assert r.continuous_residence_after_first_inside_close == 2   # first run only
    assert r.longest_inside_close_run == 3
    assert r.reentry_count == 1
    # 5 minutes * ATR 40 / width 10
    assert r.normalized_residence == Decimal(20)


def test_local_band_occupancy_uses_the_atr_band():
    # band is [960, 1050); 1100 is outside it
    forward = (flat(0, 1005), flat(1, 1040), flat(2, 1100), flat(3, 970))
    r = residence_metrics(forward, LOW, HIGH, ATR, horizons=(4,))[0]
    assert r.local_band_occupancy_share == Decimal(3) / Decimal(4)


# --- activity concentration --------------------------------------------------

def test_activity_concentration_is_one_when_evenly_spread():
    """A bar spanning the whole band gives ratio 1 for volume AND for TPO.

    Bin-level TPO: the bar adds one TPO to each of the band's 360 bins, 40 of
    which are node bins, so the capture share equals the width share exactly.
    """
    band_low, band_high = LOW - ATR, HIGH + ATR
    forward = (bar(0, 960, Decimal(band_high) - Decimal("0.25"), 960, 1005, "100"),)
    r = activity_metrics(forward, LOW, HIGH, band_low, band_high,
                         band_name="atr", horizons=(1,))[0]
    assert r.undefined_reason == ""
    assert r.node_width_share == Decimal(40) / Decimal(360)
    assert r.node_tpo == 40 and r.band_tpo == 360
    assert r.node_tpo_capture_share == Decimal(40) / Decimal(360)
    assert r.volume_concentration_ratio == 1
    assert r.tpo_concentration_ratio == 1
    assert r.activity_concentration_ratio == 1
    # The binary zone-touch counts are preserved separately.
    assert r.bars_touching_node == 1 and r.bars_touching_band == 1
    assert r.node_touch_bar_share == 1


def test_activity_concentration_exceeds_one_when_price_sits_in_the_node():
    band_low, band_high = LOW - ATR, HIGH + ATR
    forward = (flat(0, 1005, "100"), flat(1, 1006, "100"))
    r = activity_metrics(forward, LOW, HIGH, band_low, band_high,
                         band_name="atr", horizons=(2,))[0]
    # all volume and all TPO inside a node holding 40/360 of the band
    assert r.node_volume_capture_share == 1
    assert r.node_tpo_capture_share == 1
    assert r.activity_concentration_ratio == Decimal(360) / Decimal(40)
    assert r.tpo_concentration_ratio == Decimal(360) / Decimal(40)


def test_activity_zero_denominators_are_reported_not_discarded():
    band_low, band_high = LOW - ATR, HIGH + ATR
    r = activity_metrics((), LOW, HIGH, band_low, band_high,
                         band_name="atr", horizons=(5,))[0]
    assert r.activity_concentration_ratio is None
    assert r.undefined_reason == "NO_FORWARD_BARS"
    # bars entirely outside the band leave the band empty
    forward = (flat(0, 2000, "100"),)
    r = activity_metrics(forward, LOW, HIGH, band_low, band_high,
                         band_name="atr", horizons=(1,))[0]
    assert r.undefined_reason == "ZERO_BAND_VOLUME"


def test_market_rate_ratios_compare_to_the_pre_touch_window():
    pre = tuple(bar(i, 1000, 1002, 998, 1000, "10") for i in range(15))
    forward = tuple(bar(i, 1000, 1004, 996, 1000, "20") for i in range(5))
    r = market_rate_metrics(forward, pre, horizons=(5,))[0]
    assert r.volume_rate_ratio == 2          # 20 vs 10
    assert r.range_rate_ratio == 2           # 8 vs 4
    r = market_rate_metrics(forward, (), horizons=(5,))[0]
    assert r.volume_rate_ratio is None and r.undefined_reason == "ZERO_PRE_TOUCH_VOLUME"


# --- departure ---------------------------------------------------------------

def test_two_consecutive_outside_closes_confirm_departure():
    forward = (flat(0, 1005), flat(1, 1020), flat(2, 1030), flat(3, 1040))
    d = confirmed_departure(forward, LOW, HIGH, APPROACH_FROM_BELOW)
    assert d.departed and d.side == ABOVE
    assert d.confirm_index == 2 and d.excursion_start_index == 3
    assert d.minutes_to_departure == 3
    assert d.departure_class == OPPOSITE_SIDE_TRAVERSAL


def test_same_side_rejection_classification():
    forward = (flat(0, 990), flat(1, 985))
    d = confirmed_departure(forward, LOW, HIGH, APPROACH_FROM_BELOW)
    assert d.departed and d.side == BELOW
    assert d.departure_class == SAME_SIDE_REJECTION
    d = confirmed_departure(forward, LOW, HIGH, APPROACH_FROM_ABOVE)
    assert d.departure_class == OPPOSITE_SIDE_TRAVERSAL


def test_alternating_and_interrupted_closes_do_not_confirm():
    forward = (flat(0, 1020), flat(1, 990), flat(2, 1020), flat(3, 990))
    assert not confirmed_departure(forward, LOW, HIGH, APPROACH_FROM_BELOW).departed
    # returning inside resets the streak
    forward = (flat(0, 1020), flat(1, 1005), flat(2, 1020), flat(3, 1030))
    d = confirmed_departure(forward, LOW, HIGH, APPROACH_FROM_BELOW)
    assert d.departed and d.confirm_index == 3


# --- excursion ---------------------------------------------------------------

def test_excursion_starts_after_the_confirmation_bar():
    forward = (
        flat(0, 1005), flat(1, 1020), flat(2, 1030),      # confirm at index 2
        bar(3, 1030, 1050, 1028, 1045),
        bar(4, 1045, 1070, 1040, 1065),
    )
    d = confirmed_departure(forward, LOW, HIGH, APPROACH_FROM_BELOW)
    assert d.excursion_start_index == 3
    r = excursion_metrics(forward, LOW, HIGH, ATR, d, horizons=(2,))[0]
    assert r.bars_observed == 2
    # edge is node_high 1010; best high 1070 -> 60 points -> 1.5 ATR -> 6 widths
    assert r.directional_excursion_points == 60
    assert r.directional_excursion_atr == Decimal("1.5")
    assert r.directional_excursion_widths == 6
    # worst low 1028 -> still 18 points beyond the edge
    assert r.adverse_excursion_points == 18


def test_adverse_excursion_is_negative_when_price_returns_through_the_node():
    forward = (flat(0, 1020), flat(1, 1030), bar(2, 1030, 1035, 995, 1000))
    d = confirmed_departure(forward, LOW, HIGH, APPROACH_FROM_BELOW)
    r = excursion_metrics(forward, LOW, HIGH, ATR, d, horizons=(1,))[0]
    # low 995 is 15 points below the 1010 edge
    assert r.adverse_excursion_points == -15
    assert r.reentered and r.minutes_to_reentry == 1


def test_no_departure_yields_no_excursion_rows():
    forward = (flat(0, 1005), flat(1, 1006))
    d = confirmed_departure(forward, LOW, HIGH, APPROACH_FROM_BELOW)
    assert not d.departed
    assert excursion_metrics(forward, LOW, HIGH, ATR, d) == ()


# --- causality ---------------------------------------------------------------

def test_no_metric_reads_beyond_its_horizon():
    """Extending the tail must not change a completed shorter horizon."""
    head = (flat(0, 1005), flat(1, 1006), flat(2, 1030), flat(3, 1004), flat(4, 1003))
    tail = (flat(5, 5000), flat(6, 5000), flat(7, 5000))
    a = acceptance_metrics(head, LOW, HIGH, horizons=(5,))[0]
    b = acceptance_metrics(head + tail, LOW, HIGH, horizons=(5,))[0]
    assert a == b
    ra = residence_metrics(head, LOW, HIGH, ATR, horizons=(5,))[0]
    rb = residence_metrics(head + tail, LOW, HIGH, ATR, horizons=(5,))[0]
    assert ra == rb


# --- bin-level TPO occupancy (pre-empirical defect D-G3-001) ------------------

def band_of(node_low, node_high, pad):
    return node_low - pad, node_high + pad


def test_bar_spanning_the_whole_band_gives_tpo_concentration_exactly_one():
    """The authorization's worked example, at its stated scale.

    band 12 bins, node 4 bins, one bar occupying all 12:
    T_node 4, T_band 12, capture 4/12, width 4/12, ratio 1.
    """
    node_low, node_high = Decimal(1000), Decimal(1001)          # 4 ticks
    band_low, band_high = Decimal(999), Decimal(1002)           # 12 ticks
    spanning = bar(0, 999, Decimal("1001.75"), 999, 1000, "120")
    r = activity_metrics((spanning,), node_low, node_high, band_low, band_high,
                         band_name="atr", horizons=(1,))[0]
    assert r.node_tpo == 4
    assert r.band_tpo == 12
    assert r.node_tpo_capture_share == Decimal(4) / Decimal(12)
    assert r.node_width_share == Decimal(4) / Decimal(12)
    assert r.tpo_concentration_ratio == 1


def test_bar_occupying_only_the_node_gives_band_over_node_bins():
    node_low, node_high = Decimal(1000), Decimal(1001)          # 4 ticks
    band_low, band_high = Decimal(999), Decimal(1002)           # 12 ticks
    inside_only = bar(0, 1000, Decimal("1000.75"), 1000, 1000, "40")
    r = activity_metrics((inside_only,), node_low, node_high, band_low, band_high,
                         band_name="atr", horizons=(1,))[0]
    assert r.node_tpo == 4 and r.band_tpo == 4
    assert r.tpo_concentration_ratio == Decimal(12) / Decimal(4)


def test_bar_occupying_only_a_non_node_part_of_the_band_gives_zero():
    node_low, node_high = Decimal(1000), Decimal(1001)
    band_low, band_high = Decimal(999), Decimal(1002)
    outside_node = bar(0, 999, Decimal("999.75"), 999, 999, "40")
    r = activity_metrics((outside_node,), node_low, node_high, band_low, band_high,
                         band_name="atr", horizons=(1,))[0]
    assert r.node_tpo == 0 and r.band_tpo == 4
    assert r.node_tpo_capture_share == 0
    assert r.tpo_concentration_ratio == 0
    assert r.activity_concentration_ratio == 0


def test_multiple_bars_reconcile_against_a_hand_built_occupancy_matrix():
    """Three bars over a 12-bin band, counted by hand.

    bins  999.00 999.25 999.50 999.75 | 1000.00 1000.25 1000.50 1000.75 | ...
    b0 spans 999.00-999.75          -> 4 band bins, 0 node bins
    b1 spans 1000.00-1000.50        -> 3 band bins, 3 node bins
    b2 spans 999.75-1000.25         -> 3 band bins, 2 node bins
    totals: T_band = 10, T_node = 5
    """
    node_low, node_high = Decimal(1000), Decimal(1001)
    band_low, band_high = Decimal(999), Decimal(1002)
    bars = (
        bar(0, 999, Decimal("999.75"), 999, 999, "10"),
        bar(1, 1000, Decimal("1000.50"), 1000, 1000, "10"),
        bar(2, Decimal("999.75"), Decimal("1000.25"), Decimal("999.75"), 1000, "10"),
    )
    r = activity_metrics(bars, node_low, node_high, band_low, band_high,
                         band_name="atr", horizons=(3,))[0]
    assert r.band_tpo == 10
    assert r.node_tpo == 5
    assert r.node_tpo_capture_share == Decimal(5) / Decimal(10)
    assert r.tpo_concentration_ratio == (Decimal(5) / Decimal(10)) / (
        Decimal(4) / Decimal(12)
    )
    # Binary counts differ from bin-level counts and are kept separate.
    assert r.bars_touching_node == 2
    assert r.bars_touching_band == 3


def test_zero_range_bar_occupies_exactly_one_bin():
    node_low, node_high = Decimal(1000), Decimal(1001)
    band_low, band_high = Decimal(999), Decimal(1002)
    r = activity_metrics((flat(0, 1000, "10"),), node_low, node_high,
                         band_low, band_high, band_name="atr", horizons=(1,))[0]
    assert r.node_tpo == 1 and r.band_tpo == 1
    r = activity_metrics((flat(0, 999, "10"),), node_low, node_high,
                         band_low, band_high, band_name="atr", horizons=(1,))[0]
    assert r.node_tpo == 0 and r.band_tpo == 1


def test_boundary_bins_follow_the_frozen_half_open_convention():
    """[low, high): the high edge belongs to the next zone, not this one."""
    node_low, node_high = Decimal(1000), Decimal(1001)
    band_low, band_high = Decimal(999), Decimal(1002)
    # exactly at node_high -> band bin, not a node bin
    r = activity_metrics((flat(0, 1001, "10"),), node_low, node_high,
                         band_low, band_high, band_name="atr", horizons=(1,))[0]
    assert r.node_tpo == 0 and r.band_tpo == 1
    # exactly at node_low -> a node bin
    r = activity_metrics((flat(0, 1000, "10"),), node_low, node_high,
                         band_low, band_high, band_name="atr", horizons=(1,))[0]
    assert r.node_tpo == 1
    # exactly at band_high -> outside the band entirely
    r = activity_metrics((flat(0, 1002, "10"),), node_low, node_high,
                         band_low, band_high, band_name="atr", horizons=(1,))[0]
    assert r.band_tpo == 0 and r.undefined_reason == "ZERO_BAND_VOLUME"


def test_composite_uses_the_corrected_bin_level_tpo_ratio():
    node_low, node_high = Decimal(1000), Decimal(1001)
    band_low, band_high = Decimal(999), Decimal(1002)
    bars = (
        bar(0, 1000, Decimal("1000.75"), 1000, 1000, "90"),      # node only
        bar(1, 999, Decimal("999.75"), 999, 999, "10"),          # band only
    )
    r = activity_metrics(bars, node_low, node_high, band_low, band_high,
                         band_name="atr", horizons=(2,))[0]
    expected_tpo = (Decimal(4) / Decimal(8)) / (Decimal(4) / Decimal(12))
    expected_volume = (Decimal(90) / Decimal(100)) / (Decimal(4) / Decimal(12))
    assert r.tpo_concentration_ratio == expected_tpo
    assert r.volume_concentration_ratio == expected_volume
    from hvn.gen3_outcomes import _sqrt
    assert r.activity_concentration_ratio == _sqrt(expected_volume * expected_tpo)


def test_binary_touch_counts_never_enter_the_composite():
    import ast
    import inspect

    from hvn.gen3_outcomes import activity_metrics as fn

    tree = ast.parse(inspect.getsource(fn).lstrip())
    source = ast.unparse(tree)
    # The composite is built from v_ratio and t_ratio only.
    assert "activity_concentration_ratio=_sqrt(v_ratio * t_ratio)" in source
    assert "bars_touching_node" in source          # recorded
    for forbidden in ("_sqrt(bars_touching", "bars_touching_node /"):
        assert forbidden not in source
