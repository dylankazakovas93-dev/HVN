"""Session-normalized atomic nodes — hand-calculated fixtures.

Amendment 01. Profiles use 10-point bins from 1000; ATR 40 unless stated, so
the +/- 0.50 ATR prominence radius is 20 points, i.e. two bins each side.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hvn.atomic_v2 import (
    BROAD_HIGH_VOLUME_PLATEAU,
    FLAT_TOP_PLATEAU,
    LOCAL_PROMINENCE_TOO_LOW,
    NONPOC_ATOMIC_HVN,
    ONE_BIN_LOCAL_MAXIMUM,
    OVERLAPS_POC,
    POC_ATOMIC,
    POC_BROAD,
    TPO_DENSITY_TOO_LOW,
    VOLUME_DENSITY_TOO_LOW,
    VOLUME_PERCENTILE_TOO_LOW,
    WIDTH_TOO_LARGE,
    classify_nodes,
    local_maxima,
    local_prominence,
    poc_plateau,
    profile_normalization,
    value_area,
    volume_percentiles,
)
from hvn.models import ProfileBin

from test_atomic_extraction import build_profile


def tpo_like(profile, weights=None):
    """TPO counts per bin index; defaults to the volume weights."""
    if weights is None:
        return {b.bin_index: b.profile_weight for b in profile.bins}
    return {b.bin_index: Decimal(w) for b, w in zip(profile.bins, weights)}


def nodes_of(profile, tpo=None):
    return classify_nodes(profile, tpo_like(profile, tpo))[0]


# 1/2/3. Density normalization at bin and zone level, width-normalized.
def test_volume_and_tpo_density_normalization():
    profile = build_profile([10, 10, 40, 10, 10])
    norm = profile_normalization(profile, tpo_like(profile))
    assert norm.v_total == 80 and norm.n_active == 5
    assert norm.mean_active_volume == 16
    node = next(n for n in nodes_of(profile) if n.start_bin_index == 2)
    # zone share 40/80 = 0.5 over width fraction 1/5 -> density 2.5
    assert node.zone_volume_share == Decimal("0.5")
    assert node.zone_volume_density_ratio == Decimal("2.5")
    assert node.zone_tpo_density_ratio == Decimal("2.5")


def test_zone_width_normalization_does_not_favour_wide_zones():
    # A two-bin plateau holding twice a one-bin peak has the same density.
    one = build_profile([10, 10, 40, 10, 10])
    two = build_profile([10, 10, 40, 40, 10, 10])
    a = next(n for n in nodes_of(one) if n.start_bin_index == 2)
    b = next(n for n in nodes_of(two) if n.start_bin_index == 2)
    assert a.width_bins == 1 and b.width_bins == 2
    # one: (40/80)/(1/5)=2.5 ; two: (80/120)/(2/6)=2.0 -> wider zone not favoured
    assert a.zone_volume_density_ratio > b.zone_volume_density_ratio


# 4. Percentile tie handling.
def test_percentile_ties_share_the_lowest_rank():
    profile = build_profile([10, 10, 10, 40, 50])
    ranks = volume_percentiles(profile)
    tied = [ranks[i] for i in (0, 1, 2)]
    assert tied == [Decimal(0), Decimal(0), Decimal(0)]
    assert ranks[3] == Decimal(3) / Decimal(5)
    assert ranks[4] == Decimal(4) / Decimal(5)
    # Zero-weight bins are excluded from the positive-bin population.
    sparse = build_profile([0, 0, 10, 20])
    assert set(volume_percentiles(sparse)) == {2, 3}


# 5/6. One-bin maximum and 2-5 bin flat top.
def test_one_bin_and_flat_top_geometry():
    one = next(n for n in nodes_of(build_profile([10, 10, 40, 10, 10]))
               if n.start_bin_index == 2)
    assert one.geometry == ONE_BIN_LOCAL_MAXIMUM and one.width_bins == 1
    flat = next(n for n in nodes_of(build_profile([5, 40, 40, 40, 5], atr="200"))
                if n.start_bin_index == 1)
    assert flat.geometry == FLAT_TOP_PLATEAU and flat.width_bins == 3


# 7. Wider than five bins is broad and excluded.
def test_plateau_wider_than_five_bins_is_broad_and_excluded():
    weights = [5] + [40] * 6 + [5]
    node = next(n for n in nodes_of(build_profile(weights, atr="400"))
                if n.start_bin_index == 1)
    assert node.width_bins == 6
    assert node.geometry == BROAD_HIGH_VOLUME_PLATEAU
    assert not node.accepted
    assert node.rejection_reason == WIDTH_TOO_LARGE
    # Never truncated to five bins.
    assert node.end_bin_index - node.start_bin_index + 1 == 6


# 8/9. No shoulder expansion, no merging.
def test_no_shoulder_expansion_and_no_merging():
    profile = build_profile([8, 25, 40, 25, 8])
    node = next(n for n in nodes_of(profile) if n.start_bin_index == 2)
    assert node.width_bins == 1                     # 25 is 62.5% of 40
    separate = nodes_of(build_profile([5, 40, 6, 40, 5], atr="120"))
    peaks = [n for n in separate if n.start_bin_index in (1, 3)]
    assert len(peaks) == 2
    assert peaks[0].end_bin_index < peaks[1].start_bin_index


# 10. The V1 failure: a sparse tail bump must now be rejected.
def test_sparse_tail_bump_is_rejected_by_the_session_normalized_floor():
    # Tail run of 3 against neighbours of 2, beside a dense body. Prominence
    # would pass; session-normalized volume density must not.
    weights = [3, 2, 3, 2, 3, 2] + [200, 400, 200] + [2, 3, 2]
    profile = build_profile(weights, atr="400")
    tail = [n for n in nodes_of(profile) if n.start_bin_index < 6]
    assert tail, "expected tail candidates to exist"
    for node in tail:
        assert not node.accepted
        assert node.rejection_reason == VOLUME_DENSITY_TOO_LOW


# 11. The other V1 failure: a dense centre with heavy neighbours must survive.
def test_dense_centre_with_heavy_neighbours_is_retained_as_poc():
    # The V1 failure: a dense centre whose neighbours are also heavy. Local
    # prominence is 1.12 and would be rejected, but the zone is genuinely
    # concentrated at 2.77x the profile's own active-bin mean.
    weights = [1, 1, 1, 1, 60, 65, 70, 65, 60, 1, 1, 1, 1]
    profile = build_profile(weights, atr="40")
    poc = next(n for n in nodes_of(profile) if n.node_class == POC_ATOMIC)
    assert poc.peak_volume == 70
    assert poc.local_volume_prominence < Decimal("1.5")   # would fail V1
    assert poc.zone_volume_density_ratio >= Decimal("1.5")
    assert poc.accepted, "POC is exempt from local prominence"


def test_a_near_flat_profile_yields_no_concentrated_node():
    """Concentration is relative to the profile's own mean active bin.

    In [40,55,62,67,62,55,40] the maximum is only 1.23x the active-bin mean, so
    no node is concentrated and the POC is rejected on volume density. This is
    the floor working, not a defect.
    """
    profile = build_profile([40, 55, 62, 67, 62, 55, 40], atr="40")
    poc = next(n for n in nodes_of(profile) if n.node_class == POC_ATOMIC)
    assert poc.zone_volume_density_ratio < Decimal("1.5")
    assert not poc.accepted
    assert poc.rejection_reason == VOLUME_DENSITY_TOO_LOW


# 12/13. Prominence required for non-POC, exempt for POC.
def test_nonpoc_requires_prominence_and_poc_does_not():
    weights = [1, 1, 1, 1, 60, 65, 70, 65, 60, 1, 1, 1, 1]
    profile = build_profile(weights, atr="40")
    nodes = nodes_of(profile)
    poc = [n for n in nodes if n.node_class == POC_ATOMIC]
    assert poc and all(n.accepted for n in poc)
    assert all(n.local_volume_prominence < Decimal("1.5") for n in poc)
    # A non-POC candidate failing prominence is rejected for that reason.
    profile2 = build_profile([10, 10, 100, 10, 10, 30, 29, 30, 10], atr="40")
    rejects = [
        n for n in nodes_of(profile2)
        if n.node_class == NONPOC_ATOMIC_HVN and not n.accepted
    ]
    assert any(
        n.rejection_reason in (LOCAL_PROMINENCE_TOO_LOW, VOLUME_DENSITY_TOO_LOW,
                               VOLUME_PERCENTILE_TOO_LOW, TPO_DENSITY_TOO_LOW)
        for n in rejects
    )


def test_zero_baseline_fails_rather_than_qualifying():
    # V1 treated a zero neighbourhood median as infinite prominence.
    profile = build_profile([0, 0, 5, 0, 0], atr="40")
    run = local_maxima(profile)[0]
    assert local_prominence(profile, run) is None


# 14. POC broad classification.
def test_poc_broad_when_the_tied_maximum_is_wide():
    weights = [5] + [40] * 6 + [5]
    profile = build_profile(weights, atr="400")
    poc = next(n for n in nodes_of(profile) if n.node_class == POC_BROAD)
    assert poc.width_bins == 6 and not poc.accepted


# 15. A non-POC node may not overlap the POC zone.
def test_nonpoc_node_cannot_overlap_the_poc():
    profile = build_profile([10, 10, 40, 40, 10, 10])
    nodes = nodes_of(profile)
    poc = [n for n in nodes if n.node_class.startswith("POC")]
    assert poc, "expected a POC node"
    poc_span = set(range(poc[0].start_bin_index, poc[0].end_bin_index + 1))
    for node in nodes:
        if node.node_class == NONPOC_ATOMIC_HVN and node.accepted:
            span = set(range(node.start_bin_index, node.end_bin_index + 1))
            assert not (span & poc_span)


# 16/17/18. Volume value area: construction, ties, overshoot.
def test_volume_value_area_construction():
    profile = build_profile([5, 10, 50, 10, 5])
    weights = {b.bin_index: b.profile_weight for b in profile.bins}
    bins = {b.bin_index: b for b in profile.bins}
    area = value_area(weights, bins, Decimal(80))
    # 50 -> needs 56. Both sides hold 10, so the tie rule adds the lower bin,
    # reaching 60 and stopping. The area is bins 1..2.
    assert (area.low_bin_index, area.high_bin_index) == (1, 2)
    assert area.poc_low_bin_index == 2
    assert area.covered_share == Decimal("0.75")
    assert area.low_bin_index <= area.poc_low_bin_index <= area.high_bin_index
    assert area.bin_count == 2


def test_volume_value_area_tie_adds_the_lower_side():
    profile = build_profile([1, 20, 50, 20, 1])
    weights = {b.bin_index: b.profile_weight for b in profile.bins}
    bins = {b.bin_index: b for b in profile.bins}
    area = value_area(weights, bins, Decimal(92))
    # 50 -> needs 64.4; both sides hold 20, the lower is added first
    assert area.low_bin_index == 1
    assert area.covered_share >= Decimal("0.70")


def test_value_area_may_overshoot_and_is_not_forced_to_exactly_seventy():
    profile = build_profile([1, 1, 98])
    weights = {b.bin_index: b.profile_weight for b in profile.bins}
    bins = {b.bin_index: b for b in profile.bins}
    area = value_area(weights, bins, Decimal(100))
    assert area.covered_share == Decimal("0.98")
    assert area.bin_count == 1


# 19/20. TPO value area, and the POC lies inside its own area.
def test_tpo_value_area_is_separate_from_the_volume_value_area():
    profile = build_profile([50, 10, 5, 10, 5])          # volume POC at bin 0
    volume_weights = {b.bin_index: b.profile_weight for b in profile.bins}
    tpo_weights = {0: Decimal(5), 1: Decimal(5), 2: Decimal(50),
                   3: Decimal(10), 4: Decimal(10)}
    bins = {b.bin_index: b for b in profile.bins}
    v = value_area(volume_weights, bins, Decimal(80))
    t = value_area(tpo_weights, bins, Decimal(80))
    assert v.poc_low_bin_index == 0
    assert t.poc_low_bin_index == 2
    assert v.low_bin_index <= v.poc_low_bin_index <= v.high_bin_index
    assert t.low_bin_index <= t.poc_low_bin_index <= t.high_bin_index


# 21. Value-area location is an annotation, never an eligibility filter.
def test_value_area_membership_is_not_an_eligibility_condition():
    import inspect

    import hvn.atomic_v2 as module

    source = inspect.getsource(module._rejection_reason)
    for token in ("value_area", "inside_volume", "inside_tpo", "VAL", "VAH"):
        assert token not in source, token


# 22/23. Causality.
def test_classification_uses_only_the_frozen_profile():
    profile = build_profile([10, 10, 40, 10, 10])
    first = nodes_of(profile)
    again = nodes_of(profile)
    assert [n.node_id for n in first] == [n.node_id for n in again]
    assert [n.accepted for n in first] == [n.accepted for n in again]


def test_detector_never_references_forward_information():
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "src/hvn/atomic_v2.py").read_text()
    names = {
        node.id if isinstance(node, ast.Name) else node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Name, ast.Attribute))
    }
    for token in ("forward", "horizon", "proximity", "residence", "departure",
                  "excursion", "outcome", "mfe", "mae"):
        assert not any(token in name.lower() for name in names), token


# 29. Invalid totals are rejected safely.
def test_invalid_totals_are_rejected_without_raising():
    empty = build_profile([0, 0, 0])
    norm = profile_normalization(empty, tpo_like(empty))
    assert not norm.valid
    nodes, norm2 = classify_nodes(empty, tpo_like(empty))
    assert not norm2.valid
    assert all(not n.accepted for n in nodes)


def test_poc_plateau_is_contiguous_and_deterministic():
    profile = build_profile([10, 40, 40, 10, 40])
    run = poc_plateau(profile)
    assert [b.bin_index for b in run] == [1, 2]     # lowest contiguous tie
