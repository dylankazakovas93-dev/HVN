from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from hvn.control_zones import mass_matched_controls, neutral_controls, percentile_type7
from hvn.models import (
    AllocationMethod,
    FrozenProfile,
    HvnNode,
    PeakCandidate,
    ProfileBin,
    ProfileFamily,
    ProfileWindow,
)

NY = ZoneInfo("America/New_York")


def profile(weights: list[int], poc: int) -> FrozenProfile:
    total = Decimal(sum(weights))
    cumulative = Decimal(0)
    bins = []
    for index, weight in enumerate(weights):
        share = Decimal(weight) / total
        cumulative += share
        bins.append(
            ProfileBin(
                index,
                Decimal(index),
                Decimal(index + 1),
                Decimal(index) + Decimal("0.5"),
                Decimal(weight),
                share,
                cumulative,
                index == poc,
            )
        )
    start = datetime(2025, 1, 6, 9, 30, tzinfo=NY)
    end = start + timedelta(hours=1)
    return FrozenProfile(
        "P",
        ProfileWindow(ProfileFamily.OPENING_HOUR, "2025-01-06", start, end, end),
        AllocationMethod.UNIFORM_VOLUME,
        start,
        Decimal(10),
        Decimal("0.10"),
        Decimal(1),
        Decimal(1),
        Decimal(0),
        Decimal(len(weights)),
        tuple(bins),
        poc,
        ("x",),
        total,
        total,
        "SHA",
        "development",
    )


def node(low: int, high: int, weight: int, share: Decimal) -> HvnNode:
    return HvnNode(
        "H",
        Decimal(low),
        Decimal(high),
        (Decimal(low) + Decimal(high)) / 2,
        Decimal(high - low),
        Decimal(low) + Decimal("0.5"),
        Decimal(weight),
        Decimal(1),
        Decimal(2),
        Decimal(weight),
        share,
        high - low,
        ("C",),
        "C",
    )


def test_type7_percentile_is_hand_calculated():
    values = [Decimal(v) for v in [0, 2, 4, 6, 8]]
    assert percentile_type7(values, Decimal("0.25")) == 2
    assert percentile_type7(values, Decimal("0.75")) == 6


def test_neutral_controls_preserve_width_and_exclude_poc_hvn_touch():
    subject = profile([2, 2, 2, 10, 10, 2, 2, 2, 2, 2], poc=8)
    hvn = node(3, 5, 20, Decimal(20) / Decimal(36))
    controls = neutral_controls(subject, (hvn,), width_bins=2)
    assert controls
    assert all(control.width_bins == 2 for control in controls)
    assert all(not (control.start_bin_index <= 8 <= control.end_bin_index) for control in controls)
    assert all(control.end_bin_index < 2 or control.start_bin_index > 5 for control in controls)


def test_zero_weight_bins_are_preserved_in_neutral_distribution():
    subject = profile([0, 0, 10, 10, 0, 0, 1, 1], poc=2)
    hvn = node(2, 4, 20, Decimal(20) / Decimal(22))
    controls = neutral_controls(subject, (hvn,), width_bins=1)
    assert any(control.zone_weight == 0 for control in controls)


def test_mass_matched_controls_are_calipered_and_deterministic():
    subject = profile([3, 3, 3, 8, 8, 3, 3, 3, 3, 3], poc=9)
    treated = node(3, 5, 16, Decimal(16) / Decimal(40))
    candidate = PeakCandidate(
        "C",
        3,
        4,
        3,
        Decimal("3.5"),
        Decimal(8),
        Decimal(3),
        Decimal(2),
        (1, 2, 5, 6),
        True,
        "",
    )
    controls = mass_matched_controls(
        subject, (treated,), (candidate,), treated=treated, width_bins=2
    )
    assert controls == tuple(sorted(controls, key=lambda control: control.start_bin_index))
    assert all(control.mass_proportional_difference <= Decimal("0.20") for control in controls)
    assert all(control.width_bins == 2 for control in controls)


def test_mass_match_rejects_outside_caliper():
    subject = profile([1, 1, 1, 20, 20, 1, 1, 1], poc=0)
    treated = node(3, 5, 40, Decimal(40) / Decimal(46))
    assert mass_matched_controls(
        subject, (treated,), (), treated=treated, width_bins=2
    ) == ()
