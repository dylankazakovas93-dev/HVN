from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class EpisodeEvent:
    event_id: str
    contract: str
    relationship_id: str
    session_date: date
    touch_time: datetime
    zone_low_ticks: int
    zone_high_ticks: int
    approach_side: str


def _linked(left: EpisodeEvent, right: EpisodeEvent) -> bool:
    if (
        left.contract != right.contract
        or left.relationship_id != right.relationship_id
        or left.session_date != right.session_date
        or left.approach_side != right.approach_side
    ):
        return False
    if abs((left.touch_time - right.touch_time).total_seconds()) > 300:
        return False
    overlap = max(
        0,
        min(left.zone_high_ticks, right.zone_high_ticks)
        - max(left.zone_low_ticks, right.zone_low_ticks),
    )
    narrower = min(
        left.zone_high_ticks - left.zone_low_ticks,
        right.zone_high_ticks - right.zone_low_ticks,
    )
    return overlap * 2 >= narrower


def cluster_episodes(
    events: list[EpisodeEvent] | tuple[EpisodeEvent, ...],
) -> dict[str, str]:
    ordered = sorted(
        events,
        key=lambda event: (
            event.contract,
            event.relationship_id,
            event.session_date,
            event.touch_time,
            event.zone_low_ticks,
            event.zone_high_ticks,
            event.event_id,
        ),
    )
    parent = list(range(len(ordered)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for left in range(len(ordered)):
        for right in range(left + 1, len(ordered)):
            if _linked(ordered[left], ordered[right]):
                union(left, right)
    members: dict[int, list[str]] = {}
    for index, event in enumerate(ordered):
        members.setdefault(find(index), []).append(event.event_id)
    output = {}
    for event_ids in members.values():
        episode = "EP-" + hashlib.sha256("|".join(sorted(event_ids)).encode()).hexdigest()[:20]
        for event_id in event_ids:
            output[event_id] = episode
    return output

