"""Confluence: what counts as one vote, what tolerance changes, and causality."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hvn.confluence import (
    ABOVE,
    BELOW,
    Level,
    LevelSet,
    cluster_levels,
    nearest_barriers,
)

ANCHOR = datetime(2019, 3, 4, 15, 0, tzinfo=UTC)


def level(source, low, high, kind="LOW_NODE"):
    return Level(source=source, kind=kind, low=Decimal(low), high=Decimal(high))


# ---------------------------------------------------------------------------
# Degree counts sources, not levels


def test_two_levels_from_the_same_source_are_one_vote():
    levels = [level("P1", "100", "101"), level("P1", "100.25", "101.25")]
    clusters = cluster_levels(levels, tolerance=Decimal("0.5"))
    assert len(clusters) == 1
    assert clusters[0].degree == 1, "one source cannot confluence with itself"


def test_three_distinct_sources_at_the_same_price_are_degree_three():
    levels = [
        level("P1", "100", "101"),
        level("P3", "100.5", "101.5"),
        level("P7", "100.25", "100.75"),
    ]
    clusters = cluster_levels(levels, tolerance=Decimal("0.25"))
    assert len(clusters) == 1
    assert clusters[0].degree == 3
    assert clusters[0].sources == ("P1", "P3", "P7")


def test_a_source_emitting_many_levels_cannot_manufacture_degree():
    levels = [level("P2", str(100 + i / 4), str(100.25 + i / 4)) for i in range(8)]
    clusters = cluster_levels(levels, tolerance=Decimal("1"))
    assert max(c.degree for c in clusters) == 1


# ---------------------------------------------------------------------------
# Tolerance


def test_a_tighter_tolerance_separates_what_a_looser_one_merges():
    # The gap between them is 2.75, so only a tolerance above that merges them.
    levels = [level("P1", "100", "100.25"), level("P5", "103", "103.25")]
    tight = cluster_levels(levels, tolerance=Decimal("0.25"))
    loose = cluster_levels(levels, tolerance=Decimal("3"))
    assert len(tight) == 2 and max(c.degree for c in tight) == 1
    assert len(loose) == 1 and loose[0].degree == 2


def test_degree_never_falls_as_tolerance_rises():
    levels = [
        level("P1", "100", "100.25"),
        level("P3", "101", "101.25"),
        level("P5", "104", "104.25"),
        level("P7", "108", "108.25"),
    ]
    best = [
        max(c.degree for c in cluster_levels(levels, tolerance=Decimal(t)))
        for t in ("0.25", "1", "4")
    ]
    assert best == sorted(best), "a wider tolerance cannot reduce agreement"


def test_the_reported_interval_is_not_inflated_by_the_tolerance():
    levels = [level("P1", "100", "100.25"), level("P3", "100.5", "100.75")]
    cluster = cluster_levels(levels, tolerance=Decimal("1"))[0]
    # Members span 100.00 to 100.75; the tolerance groups them but must not
    # widen the barrier itself.
    assert cluster.low == Decimal("100") and cluster.high == Decimal("100.75")


# ---------------------------------------------------------------------------
# Nearest barrier


def test_the_nearest_barrier_above_and_below_are_the_closest_on_each_side():
    clusters = cluster_levels(
        [
            level("P1", "90", "90.25"),
            level("P3", "95", "95.25"),
            level("P5", "105", "105.25"),
            level("P7", "110", "110.25"),
        ],
        tolerance=Decimal("0.25"),
    )
    found = nearest_barriers(clusters, Decimal("100"))
    assert found[ABOVE].low == Decimal("105")
    assert found[BELOW].high == Decimal("95.25")


def test_a_cluster_containing_the_price_is_a_barrier_on_neither_side():
    clusters = cluster_levels(
        [level("P1", "99", "101"), level("P3", "105", "105.25")],
        tolerance=Decimal("0.25"),
    )
    found = nearest_barriers(clusters, Decimal("100"))
    assert found[BELOW] is None, "price is inside it, so there is nothing to travel to"
    assert found[ABOVE].low == Decimal("105")


def test_a_side_with_no_cluster_yields_no_barrier():
    clusters = cluster_levels([level("P1", "90", "90.25")], tolerance=Decimal("0.25"))
    found = nearest_barriers(clusters, Decimal("100"))
    assert found[ABOVE] is None
    assert found[BELOW] is not None


def test_no_levels_at_all_is_not_an_error():
    assert cluster_levels([], tolerance=Decimal("1")) == []
    assert nearest_barriers([], Decimal("100")) == {ABOVE: None, BELOW: None}


# ---------------------------------------------------------------------------
# Causality is asserted, not assumed


def test_a_level_set_built_from_a_later_bar_is_rejected():
    late = LevelSet(
        anchor_time=ANCHOR,
        levels=(level("P1", "100", "101"),),
        latest_bar_close=ANCHOR + timedelta(minutes=1),
    )
    with pytest.raises(ValueError, match="lookahead"):
        late.assert_causal()


def test_a_level_set_built_up_to_the_anchor_passes():
    ontime = LevelSet(
        anchor_time=ANCHOR,
        levels=(level("P1", "100", "101"),),
        latest_bar_close=ANCHOR,
    )
    ontime.assert_causal()


def test_a_level_set_with_no_bars_is_not_a_causality_failure():
    LevelSet(anchor_time=ANCHOR, levels=(), latest_bar_close=None).assert_causal()


# ---------------------------------------------------------------------------
# Chaining is the defect that invalidated the first scan


def test_a_ladder_of_levels_does_not_chain_into_one_giant_cluster():
    # Nine sources one ATR apart. Under single linkage each reaches its
    # neighbour and all nine merge; under complete linkage they cannot.
    levels = [
        Level(f"P{i}", "NODE", Decimal(100 + i), Decimal(100 + i) + Decimal("0.25"))
        for i in range(9)
    ]
    clusters = cluster_levels(levels, tolerance=Decimal("1"))
    assert max(c.degree for c in clusters) < 9, "single linkage would merge all nine"
    for cluster in clusters:
        assert cluster.high - cluster.low <= Decimal("3")


def test_two_far_apart_levels_never_join_through_a_middle_one():
    levels = [
        Level("P1", "NODE", Decimal("100"), Decimal("100.25")),
        Level("P3", "NODE", Decimal("101"), Decimal("101.25")),
        Level("P5", "NODE", Decimal("102"), Decimal("102.25")),
    ]
    clusters = cluster_levels(levels, tolerance=Decimal("0.9"))
    for cluster in clusters:
        sources = set(cluster.sources)
        assert not {"P1", "P5"} <= sources, "the ends must not meet through P3"


def test_a_cluster_wider_than_the_cap_is_dropped():
    levels = [
        Level("P1", "NODE", Decimal("100"), Decimal("110")),
        Level("P3", "NODE", Decimal("100"), Decimal("110")),
    ]
    assert cluster_levels(levels, tolerance=Decimal("1")) != []
    assert cluster_levels(levels, tolerance=Decimal("1"), max_width=Decimal("3")) == []


def test_the_width_cap_does_not_drop_an_ordinary_barrier():
    levels = [
        Level("P1", "NODE", Decimal("100"), Decimal("100.75")),
        Level("P3", "NODE", Decimal("100.25"), Decimal("101")),
    ]
    kept = cluster_levels(levels, tolerance=Decimal("0.5"), max_width=Decimal("3"))
    assert len(kept) == 1 and kept[0].degree == 2


def test_tolerance_is_the_gap_between_levels_not_a_margin_on_each():
    # Exactly 1.00 apart, edge to edge.
    levels = [
        Level("P1", "NODE", Decimal("100"), Decimal("100.25")),
        Level("P3", "NODE", Decimal("101.25"), Decimal("101.50")),
    ]
    assert max(c.degree for c in cluster_levels(levels, tolerance=Decimal("0.9"))) == 1
    assert max(c.degree for c in cluster_levels(levels, tolerance=Decimal("1.1"))) == 2
