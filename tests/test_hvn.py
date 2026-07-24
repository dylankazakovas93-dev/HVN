from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from hvn.hvn import extract_hvns, peak_candidates
from hvn.models import (
    AllocationMethod,
    FrozenProfile,
    ProfileBin,
    ProfileFamily,
    ProfileWindow,
)

NY = ZoneInfo("America/New_York")


def manual_profile(weights, *, atr="8", size="1", poc=None):
    start = datetime(2025, 1, 1, 9, 30, tzinfo=NY)
    end = datetime(2025, 1, 1, 10, 30, tzinfo=NY)
    total = sum((Decimal(str(w)) for w in weights), Decimal(0))
    cumulative = Decimal(0)
    maximum = max(Decimal(str(w)) for w in weights)
    poc_index = (
        poc
        if poc is not None
        else next(i for i, w in enumerate(weights) if Decimal(str(w)) == maximum)
    )
    bins = []
    for i, w in enumerate(weights):
        weight = Decimal(str(w))
        share = weight / total
        cumulative += share
        bins.append(
            ProfileBin(
                i,
                Decimal(i) * Decimal(size),
                Decimal(i + 1) * Decimal(size),
                (Decimal(i) + Decimal("0.5")) * Decimal(size),
                weight,
                share,
                cumulative,
                i == poc_index,
            )
        )
    return FrozenProfile(
        "manual",
        ProfileWindow(ProfileFamily.OPENING_HOUR, "2025-01-01", start, end, end),
        AllocationMethod.UNIFORM_VOLUME,
        start,
        Decimal(atr),
        Decimal("0.10"),
        Decimal(size),
        Decimal(size),
        tuple(bins),
        poc_index,
        ("manual-row",),
        total,
        total,
        "sha",
        "synthetic",
    )


def test_isolated_peak_and_threshold_equality():
    candidates = peak_candidates(manual_profile([2, 2, 4, 2, 2]), Decimal(2))
    peak = next(c for c in candidates if c.representative_bin_index == 2)
    assert peak.local_baseline == 2
    assert peak.prominence_ratio == 2
    assert peak.qualifies


def test_flat_plateau_is_single_candidate_and_preserves_range():
    candidates = peak_candidates(manual_profile([1, 5, 5, 1]), Decimal("1.5"))
    assert len(candidates) == 1
    assert (candidates[0].start_bin_index, candidates[0].end_bin_index) == (1, 2)
    assert candidates[0].representative_bin_index == 1


def test_node_boundary_expansion_stops_below_half_peak():
    _, nodes = extract_hvns(manual_profile([1, 5, 10, 5, 4]), Decimal("1.5"))
    node = nodes[0]
    assert (node.hvn_low, node.hvn_high, node.node_bin_count) == (
        Decimal(1),
        Decimal(4),
        3,
    )


def test_overlapping_peak_nodes_merge_without_double_count():
    profile = manual_profile([1, 8, 5, 8, 1])
    _, nodes = extract_hvns(profile, Decimal("1.2"))
    assert len(nodes) == 1
    assert len(nodes[0].constituent_candidate_ids) == 2
    assert nodes[0].node_total_weight == Decimal(21)


def test_touching_peak_nodes_merge():
    profile = manual_profile([1, 8, 4, 8, 1])
    _, nodes = extract_hvns(profile, Decimal("1.2"))
    assert len(nodes) == 1


def test_zero_local_baseline_special_rule():
    candidates = peak_candidates(manual_profile([0, 0, 5, 0, 0]), Decimal("2"))
    peak = next(c for c in candidates if c.representative_bin_index == 2)
    assert peak.local_baseline == 0
    assert peak.prominence_ratio == Decimal("Infinity")
    assert peak.qualifies
    assert peak.rejection_reason == "zero_baseline_positive_peak"


def test_insufficient_baseline_is_recorded_not_silently_divided():
    candidates = peak_candidates(
        manual_profile([1, 5, 1], atr="1"),
        Decimal("1.5"),
        minimum_baseline_bins=2,
    )
    peak = next(c for c in candidates if c.representative_bin_index == 1)
    assert not peak.qualifies
    assert peak.rejection_reason == "insufficient_local_baseline_bins"


def test_below_threshold_rejected():
    candidates = peak_candidates(manual_profile([4, 5, 4]), Decimal("2"))
    peak = next(c for c in candidates if c.representative_bin_index == 1)
    assert not peak.qualifies
    assert peak.rejection_reason == "below_prominence_threshold"
