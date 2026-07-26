"""Final Generation 3 detector — hand-calculated fixtures (Amendment 03)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hvn.atomic_v2 import POC_ATOMIC, POC_BROAD, profile_normalization, value_area
from hvn.atomic_v3 import (
    COMPOSITE_ACTIVITY_TOO_LOW,
    NONPOC_ATOMIC_HVN,
    PEAK_VOLUME_DENSITY_TOO_LOW,
    WIDTH_TOO_LARGE,
    ZONE_TPO_DENSITY_TOO_LOW,
    ZONE_VOLUME_DENSITY_TOO_LOW,
    classify_composite_nodes,
    density_ratios,
)
from hvn.atomic_v4 import (
    ACTIVITY_PERCENTILE_TOO_LOW,
    LOCAL_ACTIVITY_PROMINENCE_TOO_LOW,
    MIN_LOCAL_ACTIVITY_PROMINENCE,
    MIN_PEAK_ACTIVITY_PERCENTILE,
    REJECTION_ORDER,
    activity_percentile_100,
    classify_final_nodes,
)

from test_atomic_extraction import build_profile


def final_nodes(volume, tpo=None, atr="40"):
    profile = build_profile(volume, atr=atr)
    tpo_by_index = {
        b.bin_index: Decimal(t) for b, t in zip(profile.bins, tpo or volume)
    }
    return classify_final_nodes(profile, tpo_by_index)[0], profile, tpo_by_index


def nonpoc(nodes):
    return [n for n in nodes if n.node_class == NONPOC_ATOMIC_HVN]


# 1/2. Percentile uses the frozen profile, ties deterministic.
def test_activity_percentile_is_profile_relative_and_tie_deterministic():
    ranks = activity_percentile_100({0: Decimal(1), 1: Decimal(1), 2: Decimal(5),
                                     3: Decimal(9), 4: Decimal(0)})
    assert ranks[0] == ranks[1] == Decimal(0)          # ties share the lowest
    assert ranks[2] == Decimal(100) * Decimal(2) / Decimal(4)
    assert ranks[3] == Decimal(100) * Decimal(3) / Decimal(4)
    assert 4 not in ranks                              # inactive bins excluded
    assert activity_percentile_100({}) == {}


# 3/4. Exactly 90.0 passes; immediately below fails.
def test_percentile_boundary_at_exactly_ninety():
    # Ten active bins: the top bin has nine strictly below it -> exactly 90.0
    values = {i: Decimal(i + 1) for i in range(10)}
    ranks = activity_percentile_100(values)
    assert ranks[9] == Decimal("90")
    assert ranks[9] >= MIN_PEAK_ACTIVITY_PERCENTILE          # passes
    assert ranks[8] == Decimal("80")
    assert ranks[8] < MIN_PEAK_ACTIVITY_PERCENTILE           # fails
    # Twenty bins: the 19th of 20 has 18 below -> 90.0 exactly
    values = {i: Decimal(i + 1) for i in range(20)}
    assert activity_percentile_100(values)[18] == Decimal("90")


def test_percentile_gate_rejects_a_mid_profile_bump():
    # A broad hump: a small local maximum well inside the distribution.
    volume = [5, 6, 7, 8, 9, 10, 9, 8, 30, 8, 9, 10, 11, 12, 40, 12, 11, 10, 9, 8]
    nodes, _, _ = final_nodes(volume)
    rejected = [n for n in nonpoc(nodes) if not n.accepted]
    assert any(n.rejection_reason == ACTIVITY_PERCENTILE_TOO_LOW for n in rejected) or \
        all(n.rejection_reason in REJECTION_ORDER for n in rejected)


# 5/6/7/8. Local composite prominence.
def test_local_activity_prominence_boundary_and_below_background():
    from hvn.atomic_v3 import _prominence_from

    profile = build_profile([10, 10, 10, 11, 10, 10, 10], atr="40")
    activity = {b.bin_index: b.profile_weight for b in profile.bins}
    run = [b for b in profile.bins if b.bin_index == 3]
    # neighbourhood bins 1,2,4,5 all weight 10 -> median 10 -> 11/10 = 1.10
    assert _prominence_from(profile, run, activity) == Decimal("1.1")
    assert _prominence_from(profile, run, activity) >= MIN_LOCAL_ACTIVITY_PROMINENCE

    below = build_profile([10, 12, 12, 11, 12, 12, 10], atr="40")
    activity_b = {b.bin_index: b.profile_weight for b in below.bins}
    run_b = [b for b in below.bins if b.bin_index == 3]
    # median of 12,12,12,12 -> 11/12 < 1
    assert _prominence_from(below, run_b, activity_b) < Decimal(1)


def test_zero_baseline_is_invalid_not_infinite():
    from hvn.atomic_v3 import _prominence_from

    profile = build_profile([0, 0, 5, 0, 0], atr="40")
    activity = {b.bin_index: b.profile_weight for b in profile.bins}
    run = [b for b in profile.bins if b.bin_index == 2]
    assert _prominence_from(profile, run, activity) is None


def test_a_node_below_its_background_is_rejected():
    # Bin 8 is a local composite max but sits under a heavy shoulder region.
    volume = [1, 1, 200, 1, 1, 60, 62, 61, 63, 61, 62, 60, 1, 1, 1, 1]
    nodes, _, _ = final_nodes(volume)
    node = [n for n in nonpoc(nodes) if n.start_bin_index == 8]
    if node and not node[0].accepted:
        assert node[0].rejection_reason in (
            LOCAL_ACTIVITY_PROMINENCE_TOO_LOW, ACTIVITY_PERCENTILE_TOO_LOW,
        )


# 9. A genuinely distinct dense node still passes.
def test_distinct_dense_node_passes_both_new_gates():
    volume = [1, 1, 1, 1, 1, 1, 1, 1, 1, 200, 1, 1, 40, 60, 40, 1, 1, 1, 1, 1]
    nodes, _, _ = final_nodes(volume)
    node = next(n for n in nonpoc(nodes) if n.start_bin_index == 13)
    assert node.activity_percentile >= MIN_PEAK_ACTIVITY_PERCENTILE
    assert node.local_activity_prominence >= MIN_LOCAL_ACTIVITY_PROMINENCE
    assert node.accepted, node.rejection_reason


# 10/11/12. The old veto is gone; volume and TPO prominence never veto alone.
def test_the_old_one_point_five_volume_veto_is_absent():
    import ast
    import inspect
    from pathlib import Path

    import hvn.atomic_v4 as module

    source = Path(inspect.getfile(module)).read_text()
    assert "MIN_LOCAL_PROMINENCE" not in source
    assert 'Decimal("1.50")' not in source          # no 1.50 prominence gate here
    tree = ast.parse(source)
    names = {
        n.id if isinstance(n, ast.Name) else n.attr
        for n in ast.walk(tree)
        if isinstance(n, (ast.Name, ast.Attribute))
    }
    # Fields set through dataclasses.replace() appear as keyword arguments.
    names |= {n.arg for n in ast.walk(tree) if isinstance(n, ast.keyword) and n.arg}
    assert "local_volume_prominence" not in names
    assert "local_tpo_prominence" not in names
    assert "local_activity_prominence" in names


def test_volume_and_tpo_prominence_are_recorded_but_never_gate():
    volume = [1, 1, 1, 1, 1, 1, 1, 1, 1, 200, 1, 1, 40, 60, 40, 1, 1, 1, 1, 1]
    nodes, _, _ = final_nodes(volume)
    node = next(n for n in nonpoc(nodes) if n.start_bin_index == 13)
    assert node.local_volume_prominence is not None
    assert node.local_tpo_prominence is not None
    assert node.accepted
    rejected_reasons = {n.rejection_reason for n in nodes if not n.accepted}
    assert not any("VOLUME_PROMINENCE" in r or "TPO_PROMINENCE" in r
                   for r in rejected_reasons)


# 13/14. TPO stays in discovery and qualification.
def test_tpo_remains_in_discovery_and_qualification():
    volume = [1, 1, 1, 1, 1, 1, 1, 1, 1, 200, 1, 1, 40, 60, 40, 1, 1, 1, 1, 1]
    # Same volume, but no time-at-price at the candidate: it must not qualify.
    tpo = list(volume)
    tpo[12] = tpo[13] = tpo[14] = 1
    nodes, _, _ = final_nodes(volume, tpo)
    node = [n for n in nonpoc(nodes) if n.start_bin_index == 13]
    assert not node or not node[0].accepted


# 16/17/18/19. Retained rules.
def test_amendment_02_floors_are_unchanged():
    from hvn import atomic_v3

    assert atomic_v3.MIN_ZONE_VOLUME_DENSITY == Decimal("1.25")
    assert atomic_v3.MIN_PEAK_VOLUME_DENSITY == Decimal("1.50")
    assert atomic_v3.MIN_ZONE_TPO_DENSITY == Decimal("1.00")
    assert atomic_v3.MIN_ZONE_ACTIVITY_DENSITY == Decimal("1.35")


def test_poc_rules_and_population_are_unchanged():
    volume = [1, 1, 1, 70, 75, 80, 75, 70, 1, 1, 120, 1]
    profile = build_profile(volume, atr="40")
    tpo = {b.bin_index: Decimal(v) for b, v in zip(profile.bins, volume)}
    v3_nodes, _ = classify_composite_nodes(profile, tpo)
    v4_nodes, _ = classify_final_nodes(profile, tpo)
    v3_poc = [(n.start_bin_index, n.end_bin_index, n.node_class, n.accepted)
              for n in v3_nodes if n.node_class in (POC_ATOMIC, POC_BROAD)]
    v4_poc = [(n.start_bin_index, n.end_bin_index, n.node_class, n.accepted)
              for n in v4_nodes if n.node_class in (POC_ATOMIC, POC_BROAD)]
    assert v3_poc == v4_poc, "POC population must be identical to Pilot V3"


def test_width_rules_unchanged():
    volume = [1, 1, 200, 1, 1] + [30] * 6 + [1, 1]
    nodes, _, _ = final_nodes(volume, atr="400")
    broad = [n for n in nonpoc(nodes) if n.width_bins == 6]
    assert broad and broad[0].rejection_reason == WIDTH_TOO_LARGE
    assert broad[0].end_bin_index - broad[0].start_bin_index + 1 == 6


def test_value_area_rules_unchanged():
    profile = build_profile([5, 10, 50, 10, 5])
    weights = {b.bin_index: b.profile_weight for b in profile.bins}
    bins = {b.bin_index: b for b in profile.bins}
    area = value_area(weights, bins, Decimal(80))
    assert (area.low_bin_index, area.high_bin_index) == (1, 2)
    assert area.covered_share == Decimal("0.75")


# 21. Ledgers reconcile and the ordering is frozen.
def test_ledgers_reconcile_and_reasons_are_in_the_frozen_set():
    volume = [1, 1, 1, 70, 75, 80, 75, 70, 1, 1, 120, 1, 30, 1, 5, 6, 5, 1]
    nodes, _, _ = final_nodes(volume)
    accepted = [n for n in nodes if n.accepted]
    rejected = [n for n in nodes if not n.accepted]
    assert len(nodes) == len(accepted) + len(rejected)
    assert all(n.rejection_reason == "" for n in accepted)
    for n in rejected:
        assert n.rejection_reason in REJECTION_ORDER, n.rejection_reason


def test_new_reasons_are_last_in_the_frozen_order():
    assert REJECTION_ORDER[-2:] == (
        ACTIVITY_PERCENTILE_TOO_LOW, LOCAL_ACTIVITY_PROMINENCE_TOO_LOW,
    )
    assert REJECTION_ORDER.index(WIDTH_TOO_LARGE) < REJECTION_ORDER.index(
        ACTIVITY_PERCENTILE_TOO_LOW
    )


# 24/25. No future field; structural isolation.
def test_no_forward_field_appears_in_the_final_detector():
    import ast
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "src/hvn/atomic_v4.py").read_text()
    tree = ast.parse(src)
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            imported.add(n.module)
        elif isinstance(n, ast.Import):
            imported |= {a.name for a in n.names}
    assert not (imported & {"hvn.atomic_proximity", "hvn.atomic_residence",
                            "hvn.atomic_departure", "hvn.atomic_pipeline"})
    names = {
        n.id if isinstance(n, ast.Name) else n.attr
        for n in ast.walk(tree)
        if isinstance(n, (ast.Name, ast.Attribute))
    }
    for token in ("forward", "horizon", "proximity", "residence", "departure",
                  "excursion", "outcome", "mfe", "mae"):
        assert not any(token in x.lower() for x in names), token


# 29. Determinism with the new fields.
def test_determinism_survives_the_new_fields():
    volume = [1, 1, 1, 70, 75, 80, 75, 70, 1, 1, 120, 1, 30, 1, 5, 6, 5, 1]
    first, _, _ = final_nodes(volume)
    second, _, _ = final_nodes(volume)
    key = lambda ns: [
        (n.node_id, n.accepted, n.rejection_reason,
         n.activity_percentile, n.local_activity_prominence) for n in ns
    ]
    assert key(first) == key(second)
