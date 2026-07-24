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


def _components(
    treated: MatchEvent, control: MatchEvent, *, include_atr: bool
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
    atr = abs(treated.atr_at_touch - control.atr_at_touch) / treated.atr_at_touch
    distance = (
        Decimal(time_difference) / Decimal(60)
        + displacement
        + path
        + Decimal("0.5") * open_distance
        + Decimal("0.5") * poc
        + (atr if include_atr else Decimal(0))
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
        eligible = []
        lane_count = 0
        for control in control_events:
            if control.event_id in used or not _same_lane(treated, control):
                continue
            lane_count += 1
            if control.session_date == treated.session_date:
                continue
            components = _components(treated, control, include_atr=True)
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
            unmatched[treated.event_id] = (
                "NO_LANE_CONTROLS" if lane_count == 0 else "PRIMARY_CALIPER_OR_SESSION"
            )
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
        for control in control_events:
            if control.event_id in used or not _same_lane(treated, control):
                continue
            if (
                control.session_date != treated.session_date
                or control.profile_id != treated.profile_id
            ):
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
