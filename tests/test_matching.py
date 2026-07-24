from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from hvn.matching import (
    MatchEvent,
    primary_cross_session_match,
    secondary_same_session_match,
)

NY = ZoneInfo("America/New_York")


def event(
    event_id: str,
    day: int,
    minute: int,
    *,
    atr: str = "10",
    displacement: str = "0.2",
    low: int = 400,
    high: int = 404,
    profile: str = "P",
) -> MatchEvent:
    session = date(2025, 1, day)
    touch = datetime(2025, 1, day, 9, 30, tzinfo=NY) + timedelta(minutes=minute)
    return MatchEvent(
        event_id,
        profile,
        event_id,
        session,
        "R02",
        "uniform_bar_volume",
        Decimal("0.10"),
        Decimal("2.0"),
        2025,
        "APPROACH_FROM_BELOW",
        4,
        minute,
        touch,
        Decimal(atr),
        Decimal(displacement),
        Decimal("0.5"),
        Decimal("1.0"),
        Decimal("2.0"),
        low,
        high,
    )


def test_primary_requires_different_sessions_and_needs_no_overlap_filter():
    treated = event("T", 6, 30)
    same = event("SAME", 6, 30, low=410, high=414)
    other = event("OTHER", 7, 30, low=410, high=414)
    pairs, _ = primary_cross_session_match([treated], [same, other], control_family="C01")
    assert len(pairs) == 1
    assert pairs[0].control_event_id == "OTHER"
    assert pairs[0].treated_session_date != pairs[0].control_session_date
    assert not pairs[0].overlap_120


def test_primary_uses_interaction_clock_and_60_minute_caliper():
    treated = event("T", 6, 10)
    eligible = event("E", 7, 70, low=410, high=414)
    outside = event("O", 8, 71, low=410, high=414)
    pairs, _ = primary_cross_session_match([treated], [outside, eligible], control_family="C01")
    assert pairs[0].control_event_id == "E"
    assert pairs[0].time_difference_minutes == 60


def test_primary_atr_proportional_caliper():
    treated = event("T", 6, 10, atr="10")
    edge = event("E", 7, 10, atr="12", low=410, high=414)
    outside = event("O", 8, 10, atr="12.01", low=410, high=414)
    pairs, _ = primary_cross_session_match([treated], [outside, edge], control_family="C01")
    assert pairs[0].control_event_id == "E"


def test_primary_is_deterministic_and_prevents_reuse():
    treated = [event("T2", 7, 10), event("T1", 6, 10)]
    controls = [event("C2", 9, 10, low=410, high=414), event("C1", 8, 10, low=410, high=414)]
    first, _ = primary_cross_session_match(treated, controls, control_family="C01")
    second, _ = primary_cross_session_match(reversed(treated), reversed(controls), control_family="C01")
    assert first == second
    assert len({pair.control_event_id for pair in first}) == len(first)


def test_primary_distance_has_no_forward_outcomes():
    assert "inside_close_share" not in MatchEvent.__dataclass_fields__
    assert "path_efficiency" not in MatchEvent.__dataclass_fields__


def test_secondary_is_same_session_separate_and_records_overlap():
    treated = event("T", 6, 10, low=400, high=404)
    control = event("C", 6, 40, low=410, high=414)
    pairs, _ = secondary_same_session_match([treated], [control], control_family="C01")
    assert pairs[0].match_design == "SECONDARY_SAME_SESSION"
    assert pairs[0].overlap_60
    assert pairs[0].overlap_120
    primary, _ = primary_cross_session_match([treated], [control], control_family="C01")
    assert primary == ()


def test_secondary_rejects_touching_zones_and_same_episode():
    treated = event("T", 6, 10, low=400, high=404)
    touching = event("C", 6, 20, low=404, high=408)
    pairs, _ = secondary_same_session_match([treated], [touching], control_family="C01")
    assert pairs == ()

