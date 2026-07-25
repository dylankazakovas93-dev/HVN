from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class MatchEvent:
    event_id: str
    profile_id: str
    node_id: str
    session_date: date
    relationship_id: str
    allocation_method: str
    bin_ratio: Decimal
    prominence_threshold: Decimal
    year: int
    approach_side: str
    zone_width_bins: int
    minute_from_interaction_start: int
    touch_time: datetime
    atr_at_touch: Decimal
    pre_touch_displacement_atr: Decimal
    pre_touch_path_efficiency: Decimal
    interaction_open_distance_atr: Decimal
    poc_distance_atr: Decimal
    zone_low_ticks: int
    zone_high_ticks: int
    economic_episode_id: str = ""


@dataclass(frozen=True, slots=True)
class MatchedPair:
    pair_id: str
    match_design: str
    control_family: str
    treated_event_id: str
    control_event_id: str
    treated_session_date: date
    control_session_date: date
    distance: Decimal
    time_difference_minutes: int
    atr_proportional_difference: Decimal
    displacement_difference: Decimal
    path_efficiency_difference: Decimal
    interaction_open_distance_difference: Decimal
    poc_distance_difference: Decimal
    overlap_15: bool
    overlap_30: bool
    overlap_60: bool
    overlap_120: bool


def _same_lane(treated: MatchEvent, control: MatchEvent) -> bool:
    return (
        treated.relationship_id == control.relationship_id
        and treated.allocation_method == control.allocation_method
        and treated.bin_ratio == control.bin_ratio
        and treated.prominence_threshold == control.prominence_threshold
        and treated.year == control.year
        and treated.approach_side == control.approach_side
        and treated.zone_width_bins == control.zone_width_bins
    )


def _lane_key(event: MatchEvent):
    return (
        event.relationship_id,
        event.allocation_method,
        event.bin_ratio,
        event.prominence_threshold,
        event.year,
        event.approach_side,
        event.zone_width_bins,
    )


def _primary_lane_key(event: MatchEvent):
    """Amendment 02 primary stratum: the Amendment 01 lane without zone width.

    Year stays an exact stratum, so controls from another year can never enter
    a treated event's candidate set. Width is controlled by caliper, distance
    term and post-match balance instead of by exact equality.
    """
    return (
        event.relationship_id,
        event.allocation_method,
        event.bin_ratio,
        event.prominence_threshold,
        event.year,
        event.approach_side,
    )


TICK_SIZE = Decimal("0.25")
WIDTH_RATIO_MINIMUM = Decimal("0.67")
WIDTH_RATIO_MAXIMUM = Decimal("1.50")


def zone_width_atr(event: MatchEvent) -> Decimal | None:
    """ATR-normalized zone width, or None when it is not usable for matching.

    Amendment 02 rejects invalid, missing, zero or nonpositive width and any
    nonpositive ATR, before the caliper is evaluated.
    """
    if event.atr_at_touch is None or event.atr_at_touch <= 0:
        return None
    width_points = (event.zone_high_ticks - event.zone_low_ticks) * TICK_SIZE
    if width_points <= 0:
        return None
    return width_points / event.atr_at_touch


def _width_terms(
    treated_width: Decimal, control_width: Decimal
) -> tuple[bool, Decimal]:
    """Return whether the pair passes the width caliper, and its log distance.

    The caliper is the literal ratio bound `0.67 <= W_C/W_T <= 1.50`, which is
    stricter than the log form at the lower end; see STAGE_02_AMENDMENT_02.md.
    Both stated boundary values are inclusive.
    """
    ratio = control_width / treated_width
    admissible = WIDTH_RATIO_MINIMUM <= ratio <= WIDTH_RATIO_MAXIMUM
    return admissible, abs((treated_width / control_width).ln())


def _components(
    treated: MatchEvent,
    control: MatchEvent,
    *,
    include_atr: bool,
    width_distance: Decimal = Decimal(0),
) -> tuple[Decimal, int, Decimal, Decimal, Decimal, Decimal, Decimal]:
    time_difference = abs(
        treated.minute_from_interaction_start - control.minute_from_interaction_start
    )
    displacement = abs(
        treated.pre_touch_displacement_atr - control.pre_touch_displacement_atr
    )
    path = abs(
        treated.pre_touch_path_efficiency - control.pre_touch_path_efficiency
    )
    open_distance = abs(
        treated.interaction_open_distance_atr - control.interaction_open_distance_atr
    )
    poc = abs(treated.poc_distance_atr - control.poc_distance_atr)
    if treated.atr_at_touch <= 0:
        raise ValueError(f"nonpositive ATR at touch for {treated.event_id}")
    atr = abs(treated.atr_at_touch - control.atr_at_touch) / treated.atr_at_touch
    distance = (
        Decimal(time_difference) / Decimal(60)
        + displacement
        + path
        + Decimal("0.5") * open_distance
        + Decimal("0.5") * poc
        + (atr if include_atr else Decimal(0))
        + width_distance
    )
    return distance, time_difference, atr, displacement, path, open_distance, poc


def _pair(
    treated: MatchEvent,
    control: MatchEvent,
    *,
    design: str,
    family: str,
    components,
) -> MatchedPair:
    distance, time_difference, atr, displacement, path, open_distance, poc = components
    digest = hashlib.sha256(
        f"{design}|{family}|{treated.event_id}|{control.event_id}".encode()
    ).hexdigest()[:20]
    elapsed = abs(
        int((treated.touch_time - control.touch_time).total_seconds() // 60)
    )
    # Different dates are always nonoverlapping. Same-session overlaps are
    # recorded, not filtered.
    same_session = treated.session_date == control.session_date
    return MatchedPair(
        f"PAIR-{digest}",
        design,
        family,
        treated.event_id,
        control.event_id,
        treated.session_date,
        control.session_date,
        distance,
        time_difference,
        atr,
        displacement,
        path,
        open_distance,
        poc,
        same_session and elapsed < 15,
        same_session and elapsed < 30,
        same_session and elapsed < 60,
        same_session and elapsed < 120,
    )


def primary_cross_session_match(
    treated_events: list[MatchEvent] | tuple[MatchEvent, ...],
    control_events: list[MatchEvent] | tuple[MatchEvent, ...],
    *,
    control_family: str,
) -> tuple[tuple[MatchedPair, ...], dict[str, str]]:
    control_events = tuple(control_events)
    controls_by_lane: dict[tuple, list[MatchEvent]] = {}
    control_width: dict[str, Decimal] = {}
    for control in control_events:
        width = zone_width_atr(control)
        if width is None:
            continue
        control_width[control.event_id] = width
        controls_by_lane.setdefault(_primary_lane_key(control), []).append(control)
    used: set[str] = set()
    pairs: list[MatchedPair] = []
    unmatched: dict[str, str] = {}
    ordered = sorted(
        treated_events,
        key=lambda event: (
            event.year,
            event.session_date,
            event.touch_time,
            event.profile_id,
            event.node_id,
            event.event_id,
        ),
    )
    for treated in ordered:
        treated_width = zone_width_atr(treated)
        if treated_width is None:
            unmatched[treated.event_id] = "INVALID_TREATED_WIDTH"
            continue
        eligible = []
        lane_controls = controls_by_lane.get(_primary_lane_key(treated), ())
        available = 0
        for control in lane_controls:
            if control.event_id in used:
                continue
            available += 1
            if control.session_date == treated.session_date:
                continue
            admissible, width_distance = _width_terms(
                treated_width, control_width[control.event_id]
            )
            if not admissible:
                continue
            components = _components(
                treated, control, include_atr=True, width_distance=width_distance
            )
            _, time_difference, atr, displacement, _, open_distance, _ = components
            if (
                time_difference > 60
                or displacement > Decimal("0.75")
                or open_distance > Decimal("1.00")
                or atr > Decimal("0.20")
            ):
                continue
            eligible.append((components[0], control.event_id, control, components))
        if not eligible:
            if not lane_controls:
                unmatched[treated.event_id] = "NO_LANE_CONTROLS"
            elif available == 0:
                unmatched[treated.event_id] = "LANE_CONTROLS_EXHAUSTED"
            else:
                unmatched[treated.event_id] = "PRIMARY_CALIPER_OR_SESSION"
            continue
        _, _, control, components = min(eligible)
        used.add(control.event_id)
        pairs.append(
            _pair(
                treated,
                control,
                design="PRIMARY_CROSS_SESSION",
                family=control_family,
                components=components,
            )
        )
    return tuple(pairs), unmatched


def secondary_same_session_match(
    treated_events: list[MatchEvent] | tuple[MatchEvent, ...],
    control_events: list[MatchEvent] | tuple[MatchEvent, ...],
    *,
    control_family: str,
) -> tuple[tuple[MatchedPair, ...], dict[str, str]]:
    control_events = tuple(control_events)
    controls_by_lane: dict[tuple, list[MatchEvent]] = {}
    for control in control_events:
        key = (_lane_key(control), control.profile_id, control.session_date)
        controls_by_lane.setdefault(key, []).append(control)
    used: set[str] = set()
    pairs = []
    unmatched = {}
    for treated in sorted(
        treated_events,
        key=lambda event: (
            event.year,
            event.session_date,
            event.touch_time,
            event.profile_id,
            event.node_id,
            event.event_id,
        ),
    ):
        eligible = []
        lane_controls = controls_by_lane.get(
            (_lane_key(treated), treated.profile_id, treated.session_date), ()
        )
        for control in lane_controls:
            if control.event_id in used:
                continue
            if (
                treated.economic_episode_id
                and treated.economic_episode_id == control.economic_episode_id
            ):
                continue
            # Zones may neither overlap nor touch.
            if not (
                treated.zone_high_ticks < control.zone_low_ticks
                or control.zone_high_ticks < treated.zone_low_ticks
            ):
                continue
            components = _components(treated, control, include_atr=False)
            if components[1] > 60:
                continue
            eligible.append((components[0], control.event_id, control, components))
        if not eligible:
            unmatched[treated.event_id] = "NO_SECONDARY_CONTROL"
            continue
        _, _, control, components = min(eligible)
        used.add(control.event_id)
        pairs.append(
            _pair(
                treated,
                control,
                design="SECONDARY_SAME_SESSION",
                family=control_family,
                components=components,
            )
        )
    return tuple(pairs), unmatched
