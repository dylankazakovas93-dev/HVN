"""Rolling multi-session volume profile, re-anchored on a fixed schedule.

Everything tested so far used single-session anchors: roughly 400 bars, a fresh
node set every day. This builds a profile from the trailing N completed sessions
and re-anchors it at each scheduled close, so nodes are built from ~8,000 bars
and persist across days.

Causality is the whole point of the re-anchor schedule. A profile stamped at an
hourly close contains only bars that closed at or before that moment, and it is
eligible to be interacted with only strictly after it. No bar contributes to a
profile that is then used to classify that same bar.

Both high and low nodes are detected. A low node is a thin shelf in the
smoothed activity profile — the opposite object from an HVN, and one this
project has never tested.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from zoneinfo import ZoneInfo

from .engine import TICK_SIZE, intersected_bin_indices
from .models import Bar
from .zones_v4 import (
    ProfileActivity,
    activity_percentile_100,
    geometric_mean,
    smooth,
    smoothing_half_width_ticks,
)

NY = ZoneInfo("America/New_York")

# Frozen rolling-profile parameters.
ROLLING_SESSIONS = 20
REANCHOR_MINUTES = 60

HIGH_NODE = "HIGH_VOLUME_NODE"
LOW_NODE = "LOW_VOLUME_NODE"

# A high node sits in the top decile of smoothed activity; a low node in the
# bottom decile. Symmetric by construction so neither is privileged.
HIGH_NODE_PERCENTILE = Decimal("90.0")
LOW_NODE_PERCENTILE = Decimal("10.0")
HIGH_NODE_MIN_ACTIVITY = Decimal("1.30")
LOW_NODE_MAX_ACTIVITY = Decimal("0.70")


@dataclass(frozen=True, slots=True)
class RollingProfile:
    """Tick-grid volume and TPO over the trailing sessions, frozen at a moment."""

    anchor_time: datetime
    sessions: tuple[str, ...]
    low_index: int
    high_index: int
    volume: dict[int, Decimal]
    tpo: dict[int, int]
    bars_used: int
    atr_value: Decimal

    @property
    def indices(self) -> range:
        return range(self.low_index, self.high_index + 1)

    def tick_low(self, index: int) -> Decimal:
        return Decimal(index) * TICK_SIZE

    def tick_high(self, index: int) -> Decimal:
        return self.tick_low(index) + TICK_SIZE


def session_date(moment: datetime) -> str:
    """The CME session a bar belongs to: 18:00 starts the next session's date."""
    local = moment.astimezone(NY)
    if local.hour >= 18:
        local = local + timedelta(days=1)
    return local.date().isoformat()


def reanchor_times(bars: list[Bar] | tuple[Bar, ...], *, minutes: int = REANCHOR_MINUTES):
    """Every scheduled close in the data, in order, deduplicated."""
    seen = []
    previous = None
    for bar in sorted(bars, key=lambda b: b.close_time):
        local = bar.close_time.astimezone(NY)
        if local.minute % minutes:
            continue
        if previous is not None and bar.close_time == previous:
            continue
        seen.append(bar.close_time)
        previous = bar.close_time
    return tuple(seen)


def build_rolling_profile(
    bars: list[Bar] | tuple[Bar, ...],
    anchor: datetime,
    *,
    atr: Decimal,
    sessions: int = ROLLING_SESSIONS,
) -> RollingProfile | None:
    """Profile the trailing `sessions` completed sessions as of `anchor`.

    Only bars whose close time is at or before the anchor contribute, so the
    profile is knowable at the anchor and nothing later leaks in. The current,
    incomplete session is included up to the anchor: that is information a chart
    genuinely shows at that moment.
    """
    eligible = [b for b in bars if b.close_time <= anchor]
    if not eligible:
        return None
    dates = sorted({session_date(b.close_time) for b in eligible})
    keep = set(dates[-sessions:])
    window = [b for b in eligible if session_date(b.close_time) in keep]
    if len(window) < 2:
        return None

    volume: dict[int, Decimal] = {}
    tpo: dict[int, int] = {}
    for bar in window:
        indices = intersected_bin_indices(bar.low, bar.high, TICK_SIZE)
        share = bar.volume / Decimal(len(indices))
        for index in indices:
            volume[index] = volume.get(index, Decimal(0)) + share
            tpo[index] = tpo.get(index, 0) + 1
    low_index, high_index = min(volume), max(volume)
    for index in range(low_index, high_index + 1):
        volume.setdefault(index, Decimal(0))
        tpo.setdefault(index, 0)

    return RollingProfile(
        anchor_time=anchor,
        sessions=tuple(sorted(keep)),
        low_index=low_index,
        high_index=high_index,
        volume=volume,
        tpo=tpo,
        bars_used=len(window),
        atr_value=atr,
    )


def rolling_activity(profile: RollingProfile) -> ProfileActivity:
    """Volume, TPO, composite and smoothed composite densities per tick."""
    indices = profile.indices
    active = tuple(
        i
        for i in indices
        if profile.volume.get(i, Decimal(0)) > 0 or profile.tpo.get(i, 0) > 0
    )
    v_total = sum(profile.volume.values(), Decimal(0))
    t_total = sum(profile.tpo.values())
    empty: dict[int, Decimal] = {}
    half_width = smoothing_half_width_ticks(profile.atr_value)
    if not active or v_total <= 0 or t_total <= 0:
        return ProfileActivity(
            False, "INVALID_ROLLING_PROFILE", active, empty, empty, empty, empty,
            empty, half_width, v_total, t_total,
        )

    positive_volume = [i for i in indices if profile.volume.get(i, Decimal(0)) > 0]
    positive_tpo = [i for i in indices if profile.tpo.get(i, 0) > 0]
    mean_volume = v_total / Decimal(len(positive_volume))
    mean_tpo = Decimal(t_total) / Decimal(len(positive_tpo))

    volume_density = {i: profile.volume.get(i, Decimal(0)) / mean_volume for i in indices}
    tpo_density = {i: Decimal(profile.tpo.get(i, 0)) / mean_tpo for i in indices}
    raw = {i: geometric_mean(volume_density[i], tpo_density[i]) for i in indices}
    smoothed = smooth(raw, half_width, indices)
    # Rank only over ticks that actually traded. Smoothing gives an untraded gap
    # a small positive value, and if those ticks entered the ranking they would
    # occupy the bottom decile and crowd out the thin *traded* shelves that a low
    # node is supposed to find.
    traded = {i: smoothed[i] for i in active if smoothed.get(i, Decimal(0)) > 0}
    return ProfileActivity(
        True, "", active, volume_density, tpo_density, raw, smoothed,
        activity_percentile_100(traded), half_width, v_total, t_total,
    )


@dataclass(frozen=True, slots=True)
class Node:
    """A high or low node in the rolling profile, with its price interval."""

    node_class: str
    low_index: int
    high_index: int
    node_low: Decimal
    node_high: Decimal
    peak_index: int
    peak_price: Decimal
    smoothed_activity: Decimal
    activity_percentile: Decimal
    anchor_time: datetime

    @property
    def width_ticks(self) -> int:
        return self.high_index - self.low_index + 1

    @property
    def width_points(self) -> Decimal:
        return self.node_high - self.node_low

    def contains(self, price: Decimal) -> bool:
        return self.node_low <= price < self.node_high

    def touched_by(self, low: Decimal, high: Decimal) -> bool:
        return not (high < self.node_low or low >= self.node_high)

    def distance_atr(self, price: Decimal, atr: Decimal) -> Decimal:
        if self.contains(price):
            return Decimal(0)
        gap = self.node_low - price if price < self.node_low else price - self.node_high
        return gap / atr


def _runs(indices: list[int]) -> list[list[int]]:
    """Split sorted indices into maximal contiguous runs."""
    out: list[list[int]] = []
    for index in indices:
        if out and index == out[-1][-1] + 1:
            out[-1].append(index)
        else:
            out.append([index])
    return out


def detect_nodes(
    profile: RollingProfile,
    activity: ProfileActivity,
    *,
    min_width_ticks: int | None = None,
    max_width_ticks: int | None = None,
) -> list[Node]:
    """High and low nodes as contiguous runs in the top and bottom activity decile.

    High and low nodes are found by the same procedure with the comparison
    reversed, so neither class is favoured by the construction. Runs outside the
    width band are dropped rather than truncated.
    """
    if not activity.valid:
        return []
    atr = profile.atr_value
    if min_width_ticks is None:
        min_width_ticks = max(
            3, int((Decimal("0.40") * atr / TICK_SIZE).to_integral_value(rounding="ROUND_CEILING"))
        )
    if max_width_ticks is None:
        max_width_ticks = max(
            min_width_ticks,
            int((Decimal("1.50") * atr / TICK_SIZE).to_integral_value(rounding=ROUND_FLOOR)),
        )

    smoothed = activity.smoothed_activity
    percentile = activity.percentile
    active = set(activity.active)

    high_ticks = sorted(
        i
        for i in profile.indices
        if i in active
        and percentile.get(i, Decimal(0)) >= HIGH_NODE_PERCENTILE
        and smoothed.get(i, Decimal(0)) >= HIGH_NODE_MIN_ACTIVITY
    )
    low_ticks = sorted(
        i
        for i in profile.indices
        if i in active
        and percentile.get(i, Decimal(100)) <= LOW_NODE_PERCENTILE
        and 0 < smoothed.get(i, Decimal(0)) <= LOW_NODE_MAX_ACTIVITY
    )

    nodes: list[Node] = []
    for node_class, ticks, pick_extreme in (
        (HIGH_NODE, high_ticks, max),
        (LOW_NODE, low_ticks, min),
    ):
        for run in _runs(ticks):
            width = len(run)
            if width < min_width_ticks or width > max_width_ticks:
                continue
            extreme = pick_extreme(run, key=lambda i: (smoothed[i], -i))
            nodes.append(
                Node(
                    node_class=node_class,
                    low_index=run[0],
                    high_index=run[-1],
                    node_low=profile.tick_low(run[0]),
                    node_high=profile.tick_high(run[-1]),
                    peak_index=extreme,
                    peak_price=profile.tick_low(extreme) + TICK_SIZE / 2,
                    smoothed_activity=smoothed[extreme],
                    activity_percentile=percentile.get(extreme, Decimal(0)),
                    anchor_time=profile.anchor_time,
                )
            )
    nodes.sort(key=lambda n: (n.low_index, n.node_class))
    return nodes


# ---------------------------------------------------------------------------
# Tap validity


@dataclass(frozen=True, slots=True)
class Tap:
    """A qualifying interaction: close enough, for long enough."""

    valid: bool
    first_index: int | None
    bars_within: int
    closest_distance_atr: Decimal | None


def find_tap(
    forward: list[Bar] | tuple[Bar, ...],
    node: Node,
    *,
    atr: Decimal,
    max_distance_atr: Decimal,
    min_bars_within: int,
) -> Tap:
    """The first run of `min_bars_within` consecutive bars inside the band.

    A brush that leaves immediately is not a tap. Requiring consecutive bars
    inside `max_distance_atr` is what separates "price visited" from "price
    engaged", and it is the condition the earlier studies never imposed.
    """
    run = 0
    start: int | None = None
    closest: Decimal | None = None
    for index, bar in enumerate(forward):
        near_high = node.distance_atr(bar.high, atr)
        near_low = node.distance_atr(bar.low, atr)
        distance = min(near_high, near_low)
        if closest is None or distance < closest:
            closest = distance
        if distance <= max_distance_atr:
            run += 1
            if start is None:
                start = index
            if run >= min_bars_within:
                return Tap(True, start, run, closest)
        else:
            run = 0
            start = None
    return Tap(False, None, run, closest)
