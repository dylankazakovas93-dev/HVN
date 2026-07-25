"""Amendment 02 primary matching: width caliper, distance term, strata."""

from __future__ import annotations

import csv
import gzip
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from hvn.matching import (
    WIDTH_RATIO_MAXIMUM,
    WIDTH_RATIO_MINIMUM,
    MatchEvent,
    primary_cross_session_match,
    zone_width_atr,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = datetime(2021, 3, 1, 10, 0, tzinfo=timezone.utc)


def event(
    event_id: str,
    *,
    session_day: int,
    width_ticks: int,
    year: int = 2021,
    atr: str = "10",
    minute: int = 30,
    displacement: str = "0.10",
    path: str = "0.50",
    open_distance: str = "0.10",
    poc: str = "0.10",
    approach_side: str = "FROM_ABOVE",
    zone_low_ticks: int = 1000,
    width_bins: int = 3,
) -> MatchEvent:
    return MatchEvent(
        event_id,
        f"P-{event_id}",
        f"N-{event_id}",
        date(year, 3, session_day),
        "R03",
        "uniform_bar_volume",
        Decimal("0.10"),
        Decimal("2.0"),
        year,
        approach_side,
        width_bins,
        minute,
        BASE + timedelta(days=session_day, minutes=minute),
        Decimal(atr),
        Decimal(displacement),
        Decimal(path),
        Decimal(open_distance),
        Decimal(poc),
        zone_low_ticks,
        zone_low_ticks + width_ticks,
    )


def match(treated, controls):
    return primary_cross_session_match(treated, controls, control_family="C01")


# 1. Exact zone_width_bins equality is no longer required.
def test_differing_zone_width_bins_can_match():
    treated = event("T1", session_day=1, width_ticks=40, width_bins=3)
    control = event("C1", session_day=2, width_ticks=40, width_bins=9)
    pairs, unmatched = match([treated], [control])
    assert [p.control_event_id for p in pairs] == ["C1"]
    assert unmatched == {}


# 2 & 3. Same-year matching required; different-year controls rejected.
def test_same_year_required_and_other_years_rejected():
    treated = event("T1", session_day=1, width_ticks=40)
    same_year = event("C_SAME", session_day=2, width_ticks=40)
    other_year = event("C_OTHER", session_day=2, width_ticks=40, year=2023)
    pairs, _ = match([treated], [other_year])
    assert pairs == ()
    pairs, _ = match([treated], [other_year, same_year])
    assert [p.control_event_id for p in pairs] == ["C_SAME"]


# 4. Ratios of exactly 0.67 and 1.50 are handled deterministically.
@pytest.mark.parametrize("ratio", [WIDTH_RATIO_MINIMUM, WIDTH_RATIO_MAXIMUM])
def test_caliper_boundaries_are_inclusive(ratio):
    treated = event("T1", session_day=1, width_ticks=400)
    control_ticks = int(Decimal(400) * ratio)
    control = event("C1", session_day=2, width_ticks=control_ticks)
    treated_w = zone_width_atr(treated)
    control_w = zone_width_atr(control)
    assert control_w / treated_w == ratio
    pairs, _ = match([treated], [control])
    assert [p.control_event_id for p in pairs] == ["C1"]


# 5. Ratios outside the caliper are rejected.
@pytest.mark.parametrize("control_ticks", [264, 604])  # 0.66 and 1.51 of 400
def test_widths_outside_the_caliper_are_rejected(control_ticks):
    treated = event("T1", session_day=1, width_ticks=400)
    control = event("C1", session_day=2, width_ticks=control_ticks)
    ratio = zone_width_atr(control) / zone_width_atr(treated)
    assert not WIDTH_RATIO_MINIMUM <= ratio <= WIDTH_RATIO_MAXIMUM
    pairs, unmatched = match([treated], [control])
    assert pairs == ()
    assert unmatched["T1"] == "PRIMARY_CALIPER_OR_SESSION"


# 6. Invalid or zero width is rejected.
def test_zero_and_nonpositive_width_and_atr_are_rejected():
    assert zone_width_atr(event("Z", session_day=1, width_ticks=0)) is None
    assert zone_width_atr(event("N", session_day=1, width_ticks=-4)) is None
    assert zone_width_atr(event("A", session_day=1, width_ticks=40, atr="0")) is None
    treated = event("T1", session_day=1, width_ticks=0)
    control = event("C1", session_day=2, width_ticks=40)
    pairs, unmatched = match([treated], [control])
    assert pairs == ()
    assert unmatched["T1"] == "INVALID_TREATED_WIDTH"
    # A zero-width control is dropped before it can be considered.
    treated = event("T2", session_day=1, width_ticks=40)
    pairs, unmatched = match([treated], [event("C0", session_day=2, width_ticks=0)])
    assert pairs == ()
    assert unmatched["T2"] == "NO_LANE_CONTROLS"


# 7. The log-width distance term is calculated correctly.
def test_log_width_distance_term_is_correct():
    treated = event("T1", session_day=1, width_ticks=400)
    control = event("C1", session_day=2, width_ticks=500)
    pairs, _ = match([treated], [control])
    treated_w, control_w = zone_width_atr(treated), zone_width_atr(control)
    expected_width_term = abs((treated_w / control_w).ln())
    # Every other component is identical between the two events, so the whole
    # distance is exactly the width term.
    assert pairs[0].distance == expected_width_term
    assert expected_width_term > 0


# 8. A closer-width control wins when all other distances are equal.
def test_closest_width_control_is_preferred():
    treated = event("T1", session_day=1, width_ticks=400)
    far = event("C_FAR", session_day=2, width_ticks=560)
    near = event("C_NEAR", session_day=3, width_ticks=410)
    pairs, _ = match([treated], [far, near])
    assert [p.control_event_id for p in pairs] == ["C_NEAR"]
    # ... and the reversed candidate order gives the same answer.
    pairs, _ = match([treated], [near, far])
    assert [p.control_event_id for p in pairs] == ["C_NEAR"]


# 9. Control reuse remains impossible.
def test_controls_are_never_reused():
    treated = [
        event("T1", session_day=1, width_ticks=400),
        event("T2", session_day=2, width_ticks=400),
    ]
    pairs, unmatched = match(treated, [event("C1", session_day=5, width_ticks=400)])
    assert len(pairs) == 1
    assert len({p.control_event_id for p in pairs}) == 1
    assert unmatched["T2"] == "LANE_CONTROLS_EXHAUSTED"


# 10. Primary pairs remain cross-session.
def test_primary_pairs_are_cross_session():
    treated = event("T1", session_day=4, width_ticks=400)
    same = event("C_SAME", session_day=4, width_ticks=400)
    other = event("C_OTHER", session_day=6, width_ticks=400)
    pairs, _ = match([treated], [same, other])
    assert [p.control_event_id for p in pairs] == ["C_OTHER"]
    for pair in pairs:
        assert pair.treated_session_date != pair.control_session_date
        assert not (pair.overlap_15 or pair.overlap_30 or pair.overlap_60 or pair.overlap_120)


# 11. Matching is deterministic.
def test_matching_is_deterministic_under_input_permutation():
    treated = [event(f"T{i}", session_day=i, width_ticks=400 + i) for i in range(1, 6)]
    controls = [event(f"C{i}", session_day=10 + i, width_ticks=400 + 2 * i) for i in range(1, 6)]
    first, first_unmatched = match(treated, controls)
    second, second_unmatched = match(list(reversed(treated)), list(reversed(controls)))
    assert [(p.treated_event_id, p.control_event_id) for p in first] == [
        (p.treated_event_id, p.control_event_id) for p in second
    ]
    assert [p.pair_id for p in first] == [p.pair_id for p in second]
    assert first_unmatched == second_unmatched


# 12. No forward outcome enters eligibility or distance.
def test_no_forward_outcome_fields_are_referenced_in_matching():
    import ast

    source = (ROOT / "src/hvn/matching.py").read_text()
    names = {
        node.id if isinstance(node, ast.Name) else node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Name, ast.Attribute))
    }
    forbidden = ("forward", "horizon", "mae", "mfe", "outcome", "acceptance",
                 "pnl", "departure", "accepted", "reject_price")
    offending = {
        name for name in names
        if any(token in name.lower() for token in forbidden)
    }
    assert offending == set(), offending
    # The matching input type carries no outcome field at all.
    assert not any(
        any(token in field.lower() for token in forbidden)
        for field in MatchEvent.__dataclass_fields__
    )


# 13 & 14. Generation 1 artifacts unchanged; Generation 2 writes elsewhere.
def test_generation_1_artifacts_are_preserved_and_separate():
    generation_1 = ROOT / "outputs/stage_02"
    assert (generation_1 / "gate_results.csv").exists()
    rows = list(csv.DictReader((generation_1 / "gate_results.csv").open()))
    assert len(rows) == 40
    assert {row["status"] for row in rows} == {"UNDERPOWERED"}
    quality = list(csv.DictReader((generation_1 / "match_quality.csv").open()))
    assert sum(int(row["matched_pairs"]) for row in quality) == 42
    generation_2 = ROOT / "outputs/stage_02_generation_2"
    assert generation_2.resolve() != generation_1.resolve()
    assert generation_2 not in generation_1.parents


def test_aggregator_never_writes_into_the_input_directory():
    """A generation must not write artifacts into the shared ledger directory.

    Generation 2 originally emitted its match and episode ledgers into
    outputs/stage_02/detailed, silently modifying preserved Generation 1
    artifacts. Every DETAIL path must now be read-only input.
    """
    import ast

    source = (ROOT / "scripts/aggregate_stage_02.py").read_text()
    detail_targets = set()
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Div)
            and isinstance(node.left, ast.Name)
            and node.left.id == "DETAIL"
        ):
            if isinstance(node.right, ast.Constant):
                detail_targets.add(node.right.value)
            elif isinstance(node.right, ast.JoinedStr):
                detail_targets.add(
                    "".join(
                        part.value if isinstance(part, ast.Constant) else "{}"
                        for part in node.right.values
                    )
                )
    # Only per-year input ledgers and checkpoints may be addressed under DETAIL.
    assert detail_targets <= {"{}_{}.csv.gz", "checkpoint_{}.json"}, detail_targets
    for forbidden in ("match_ledger", "economic_episode_ledger"):
        assert f'DETAIL / "{forbidden}' not in source, forbidden


# 15. No forbidden partition is reachable from the Generation 2 inputs.
def test_generation_2_inputs_exclude_forbidden_years():
    detail = ROOT / "outputs/stage_02/detailed"
    years = {int(p.stem.split("_")[-1]) for p in detail.glob("checkpoint_*.json")}
    assert years == {2019, 2021, 2023, 2025, 2026}
    assert not years & {2020, 2022, 2024}
    for checkpoint in detail.glob("checkpoint_*.json"):
        summary = json.loads(checkpoint.read_text())
        assert "nq2020" not in summary["archive"]
    for ledger in detail.glob("events_*.csv.gz"):
        with gzip.open(ledger, "rt", newline="") as stream:
            for row in csv.DictReader(stream):
                assert int(row["year"]) not in {2020, 2022, 2024}
                break
