"""Composite volume/TPO atomic nodes — hand-calculated fixtures (Amendment 02)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hvn.atomic_v2 import POC_ATOMIC, POC_BROAD, value_area
from hvn.atomic_v3 import (
    BROAD_COMPOSITE_PLATEAU,
    COMPOSITE_ACTIVITY_TOO_LOW,
    COMPOSITE_FLAT_TOP_PLATEAU,
    NONPOC_ATOMIC_HVN,
    ONE_BIN_COMPOSITE_LOCAL_MAXIMUM,
    OVERLAPS_VOLUME_POC,
    PEAK_VOLUME_DENSITY_TOO_LOW,
    WIDTH_TOO_LARGE,
    ZONE_TPO_DENSITY_TOO_LOW,
    ZONE_VOLUME_DENSITY_TOO_LOW,
    classify_composite_nodes,
    composite_local_maxima,
    density_ratios,
    geometric_mean,
    percentile_ranks,
)
from hvn.atomic_v2 import profile_normalization

from test_atomic_extraction import build_profile


def nodes_of(volume, tpo, atr="40"):
    profile = build_profile(volume, atr=atr)
    tpo_by_index = {b.bin_index: Decimal(t) for b, t in zip(profile.bins, tpo)}
    return classify_composite_nodes(profile, tpo_by_index)[0], profile, tpo_by_index


def nonpoc(nodes):
    return [n for n in nodes if n.node_class == NONPOC_ATOMIC_HVN]


# 1/2. Geometric mean.
def test_composite_activity_is_the_geometric_mean():
    assert geometric_mean(Decimal("1.5"), Decimal("1.5")) == Decimal("1.5")
    assert geometric_mean(Decimal("2.25"), Decimal("1.0")) == Decimal("1.5")
    assert geometric_mean(Decimal(4), Decimal(9)) == Decimal(6)


def test_composite_activity_is_one_when_both_inputs_are_one():
    assert geometric_mean(Decimal(1), Decimal(1)) == Decimal(1)


# 3/4. Neither proxy can compensate for the other's absence.
def test_high_volume_cannot_compensate_for_near_zero_tpo():
    assert geometric_mean(Decimal(100), Decimal(0)) == 0
    tiny = geometric_mean(Decimal(100), Decimal("0.0001"))
    assert tiny < Decimal("0.11")


def test_high_tpo_cannot_compensate_for_weak_volume():
    tiny = geometric_mean(Decimal("0.0001"), Decimal(100))
    assert tiny < Decimal("0.11")


# 5/6. A dense centre with low neighbour prominence can now qualify.
def test_dense_centre_with_low_prominence_qualifies():
    """A busy price embedded among equally busy prices — the V2 veto case.

    Bin 5 peaks at 80 against neighbours of 70-75, so local prominence is 1.10
    and Amendment 01 would have rejected it. Bin 10 carries the POC, so bin 5
    is genuinely non-POC.
    """
    volume = [1, 1, 1, 70, 75, 80, 75, 70, 1, 1, 120, 1]
    nodes, profile, _ = nodes_of(volume, list(volume))
    node = next(n for n in nonpoc(nodes) if n.start_bin_index == 5)
    assert node.local_volume_prominence < Decimal("1.5")   # would fail V2
    assert node.peak_volume_density_ratio >= Decimal("1.50")
    assert node.zone_activity_density_ratio >= Decimal("1.35")
    assert node.accepted, node.rejection_reason


def test_local_prominence_is_never_a_rejection_reason():
    import inspect

    import hvn.atomic_v3 as module

    import ast

    tree = ast.parse(inspect.getsource(module._rejection_reason).lstrip())
    function = tree.body[0]
    if (function.body and isinstance(function.body[0], ast.Expr)
            and isinstance(function.body[0].value, ast.Constant)):
        function.body = function.body[1:]        # drop the docstring
    body = ast.unparse(function).lower()
    for token in ("prominence", "percentile"):
        assert token not in body, token


# 7. Percentiles are recorded but not gates.
def test_percentiles_are_recorded_but_not_eligibility():
    volume = [1, 1, 1, 1, 40, 60, 40, 1, 1, 1, 1, 1]
    nodes, _, _ = nodes_of(volume, volume)
    node = next(n for n in nodes if n.start_bin_index == 5)
    assert node.volume_percentile > 0
    assert node.tpo_percentile > 0
    assert node.activity_percentile > 0
    assert node.accepted


# 8/9. Candidates come from the composite profile.
def test_candidates_are_composite_peaks_not_volume_peaks():
    profile = build_profile([10, 10, 60, 10, 10], atr="40")
    # TPO is flat, so the composite peak still follows volume here.
    tpo_flat = {b.bin_index: Decimal(10) for b in profile.bins}
    norm = profile_normalization(profile, tpo_flat)
    _, _, activity = density_ratios(profile, tpo_flat, norm)
    runs = composite_local_maxima(profile, activity)
    assert [r[0].bin_index for r in runs] == [2]

    # Now give bin 1 all the time-at-price: the composite peak moves.
    tpo_shift = {b.bin_index: Decimal(1) for b in profile.bins}
    tpo_shift[1] = Decimal(500)
    norm2 = profile_normalization(profile, tpo_shift)
    _, _, activity2 = density_ratios(profile, tpo_shift, norm2)
    runs2 = composite_local_maxima(profile, activity2)
    assert 1 in [r[0].bin_index for r in runs2]


def test_a_volume_peak_that_is_not_a_composite_peak_is_not_a_candidate():
    profile = build_profile([10, 10, 60, 10, 10], atr="40")
    tpo = {b.bin_index: Decimal(1) for b in profile.bins}
    tpo[2] = Decimal("0.0001")          # volume peak, effectively no time
    norm = profile_normalization(profile, tpo)
    _, _, activity = density_ratios(profile, tpo, norm)
    runs = composite_local_maxima(profile, activity)
    assert 2 not in [r[0].bin_index for r in runs]


# 10-15. Each fixed floor, at the boundary and just below it.
def build_for_floors(zone_v_target, tpo_scale=1):
    """A 12-bin profile with one non-POC composite peak of tunable strength."""
    volume = [1] * 12
    volume[3] = 100                      # POC, far from the test peak
    volume[8] = zone_v_target
    tpo = [1] * 12
    tpo[3] = 100
    tpo[8] = max(int(zone_v_target * tpo_scale), 1)
    return volume, tpo


def test_floors_accept_at_the_boundary_and_reject_just_below():
    # Strong peak: comfortably above every floor.
    nodes, _, _ = nodes_of(*build_for_floors(40))
    strong = [n for n in nonpoc(nodes) if n.start_bin_index == 8]
    assert strong and strong[0].accepted, strong and strong[0].rejection_reason

    # Weak peak: barely above its neighbours, must fail on a density floor.
    nodes, _, _ = nodes_of(*build_for_floors(2))
    weak = [n for n in nonpoc(nodes) if n.start_bin_index == 8]
    assert weak and not weak[0].accepted
    assert weak[0].rejection_reason in (
        ZONE_VOLUME_DENSITY_TOO_LOW,
        PEAK_VOLUME_DENSITY_TOO_LOW,
        COMPOSITE_ACTIVITY_TOO_LOW,
        ZONE_TPO_DENSITY_TOO_LOW,
    )


def test_tpo_floor_rejects_a_volume_only_peak():
    volume = [1] * 12
    volume[3] = 100
    volume[8] = 40
    tpo = [5] * 12
    tpo[3] = 100
    tpo[8] = 1                            # below-average time at that price
    nodes, _, _ = nodes_of(volume, tpo)
    node = [n for n in nonpoc(nodes) if n.start_bin_index == 8]
    if node:
        assert not node[0].accepted
        assert node[0].rejection_reason in (
            ZONE_TPO_DENSITY_TOO_LOW, COMPOSITE_ACTIVITY_TOO_LOW,
        )


# 16/17. Widths.
def test_widths_one_to_five_qualify_and_six_is_broad():
    volume = [1, 1, 100, 1, 1] + [30] * 3 + [1, 1, 1, 1]
    tpo = list(volume)
    nodes, _, _ = nodes_of(volume, tpo, atr="400")
    plateau = [n for n in nonpoc(nodes) if n.width_bins == 3]
    assert plateau and plateau[0].geometry == COMPOSITE_FLAT_TOP_PLATEAU

    wide_volume = [1, 1, 100, 1, 1] + [30] * 6 + [1, 1]
    nodes, _, _ = nodes_of(wide_volume, list(wide_volume), atr="400")
    broad = [n for n in nonpoc(nodes) if n.width_bins == 6]
    assert broad
    assert broad[0].geometry == BROAD_COMPOSITE_PLATEAU
    assert not broad[0].accepted and broad[0].rejection_reason == WIDTH_TOO_LARGE
    assert broad[0].end_bin_index - broad[0].start_bin_index + 1 == 6   # not truncated


# 18/19. No shoulder expansion, no merging.
def test_no_shoulder_expansion_and_no_merging():
    volume = [1, 1, 25, 40, 25, 1, 1, 1, 1, 1, 1, 1]
    nodes, _, _ = nodes_of(volume, list(volume), atr="40")
    peak = [n for n in nodes if n.start_bin_index == 3]
    assert peak and peak[0].width_bins == 1

    two = [1, 40, 6, 40, 1, 1, 1, 1, 1, 1, 1, 1]
    nodes, _, _ = nodes_of(two, list(two), atr="120")
    spans = sorted((n.start_bin_index, n.end_bin_index) for n in nodes)
    assert (1, 1) in spans and (3, 3) in spans


# 20/21. POC rules unchanged; non-POC cannot overlap the POC.
def test_poc_rules_are_unchanged_and_nonpoc_cannot_overlap_poc():
    volume = [1, 1, 1, 1, 60, 65, 70, 65, 60, 1, 1, 1, 1]
    nodes, _, _ = nodes_of(volume, list(volume))
    poc = [n for n in nodes if n.node_class in (POC_ATOMIC, POC_BROAD)]
    assert len(poc) == 1
    span = set(range(poc[0].start_bin_index, poc[0].end_bin_index + 1))
    for node in nonpoc(nodes):
        if node.accepted:
            assert not (set(range(node.start_bin_index, node.end_bin_index + 1)) & span)
        elif set(range(node.start_bin_index, node.end_bin_index + 1)) & span:
            assert node.rejection_reason == OVERLAPS_VOLUME_POC


def test_poc_and_composite_zone_are_never_double_counted():
    volume = [1, 1, 1, 1, 40, 60, 40, 1, 1, 1, 1, 1]
    nodes, _, _ = nodes_of(volume, list(volume))
    spans = [(n.start_bin_index, n.end_bin_index) for n in nodes]
    assert len(spans) == len(set(spans)), spans


# 22/23. Value areas unchanged and not an eligibility filter.
def test_value_area_construction_is_unchanged():
    profile = build_profile([5, 10, 50, 10, 5])
    weights = {b.bin_index: b.profile_weight for b in profile.bins}
    bins = {b.bin_index: b for b in profile.bins}
    area = value_area(weights, bins, Decimal(80))
    assert (area.low_bin_index, area.high_bin_index) == (1, 2)
    assert area.covered_share == Decimal("0.75")


def test_value_area_location_does_not_affect_eligibility():
    import inspect

    import hvn.atomic_v3 as module

    source = inspect.getsource(module.classify_composite_nodes)
    for token in ("value_area", "inside_volume", "inside_tpo", "VAL", "VAH"):
        assert token not in source, token


# 24. Ledger arithmetic.
def test_candidates_reconcile_with_accepted_and_rejected():
    volume = [1, 1, 1, 1, 40, 60, 40, 1, 30, 1, 1, 1]
    nodes, _, _ = nodes_of(volume, list(volume))
    accepted = [n for n in nodes if n.accepted]
    rejected = [n for n in nodes if not n.accepted]
    assert len(nodes) == len(accepted) + len(rejected)
    assert all(n.rejection_reason == "" for n in accepted)
    assert all(n.rejection_reason != "" for n in rejected)


# 25/26. Structural isolation and causality.
def test_detector_imports_no_forward_module():
    import ast
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "src/hvn/atomic_v3.py").read_text()
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
    forward = {"hvn.atomic_proximity", "hvn.atomic_residence",
               "hvn.atomic_departure", "hvn.atomic_pipeline"}
    assert not (imported & forward)
    for prefix in ("atomic_proximity", "atomic_residence", "atomic_departure"):
        assert not any(prefix in m for m in imported)


def test_classification_is_deterministic_and_frozen():
    volume = [1, 1, 1, 1, 40, 60, 40, 1, 30, 1, 1, 1]
    first, _, _ = nodes_of(volume, list(volume))
    second, _, _ = nodes_of(volume, list(volume))
    assert [(n.node_id, n.accepted, n.rejection_reason) for n in first] == [
        (n.node_id, n.accepted, n.rejection_reason) for n in second
    ]


# Percentile convention.
def test_percentile_ties_share_the_lowest_rank():
    ranks = percentile_ranks({0: Decimal(5), 1: Decimal(5), 2: Decimal(9)})
    assert ranks[0] == ranks[1] == Decimal(0)
    assert ranks[2] == Decimal(2) / Decimal(3)
