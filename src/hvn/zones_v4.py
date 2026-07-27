"""Generation 4 smoothed multi-tick HVN zones.

Implements `research/hvn/STAGE_02_GENERATION_4_ZONE_SPEC.md`. Every threshold
here is frozen by that specification and may never be revised after a
Generation 4 forward outcome is opened.

Stage 1 profile construction is not altered. Generation 4 builds its own
tick-grid volume and TPO profiles from the same locked source-profile windows,
the same completed one-minute bars and the same causal ATR reference, because
the specification requires all zone calculations on the 0.25-point NQ tick grid
rather than on the Stage 1 ATR-ratio bins.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction

from .atr import atr_before
from .engine import (
    ALLOCATION_QUANTUM,
    GRID_ORIGIN,
    TICK_SIZE,
    intersected_bin_indices,
    select_poc,
)
from .models import AtrPoint, Bar, ProfileWindow

# ---------------------------------------------------------------------------
# Frozen Generation 4 constants. Supplied by authorization; never searched.

SMOOTHING_SPAN_ATR = Decimal("0.05")          # half-width, in ATR
MIN_SMOOTHING_HALF_WIDTH_TICKS = 2

MIN_PEAK_ACTIVITY_PERCENTILE = Decimal("95.0")
MIN_PEAK_ACTIVITY_DENSITY = Decimal("1.50")

BASIN_FLOOR_ACTIVITY = Decimal("1.00")
BASIN_MAX_DISTANCE_ATR = Decimal("1.00")

CORE_EXPANSION_FRACTION = Decimal("0.70")

MIN_ZONE_WIDTH_ATR = Decimal("0.10")
MIN_ZONE_WIDTH_TICKS_FLOOR = 4
MAX_ZONE_WIDTH_ATR = Decimal("0.75")
MAX_POC_ZONE_WIDTH_ATR = Decimal("1.00")

MIN_ZONE_VOLUME_DENSITY = Decimal("1.25")
MIN_ZONE_TPO_DENSITY = Decimal("1.00")
MIN_ZONE_ACTIVITY_DENSITY = Decimal("1.35")
MIN_PEAK_TO_VALLEY_RATIO = Decimal("1.10")

MERGE_VALLEY_FRACTION = Decimal("0.85")
MERGE_SEPARATION_TICKS = 2

# Zone classes.
POC_HVN_ZONE = "POC_HVN_ZONE"
POC_BROAD_DISTRIBUTION = "POC_BROAD_DISTRIBUTION"
NONPOC_HVN_ZONE = "NONPOC_HVN_ZONE"
BROAD_ACTIVITY_DISTRIBUTION = "BROAD_ACTIVITY_DISTRIBUTION"

# Rejection reasons, in frozen first-failure order.
INVALID_PROFILE_TOTAL = "INVALID_PROFILE_TOTAL"
INVALID_TPO_TOTAL = "INVALID_TPO_TOTAL"
INVALID_ACTIVE_TICK_COUNT = "INVALID_ACTIVE_TICK_COUNT"
PEAK_PERCENTILE_TOO_LOW = "PEAK_PERCENTILE_TOO_LOW"
PEAK_ACTIVITY_TOO_LOW = "PEAK_ACTIVITY_TOO_LOW"
OVERLAPS_VOLUME_POC = "OVERLAPS_VOLUME_POC"
BASIN_TOO_NARROW = "BASIN_TOO_NARROW"
NO_VALID_BASIN_SEPARATION = "NO_VALID_BASIN_SEPARATION"
PEAK_TO_VALLEY_TOO_LOW = "PEAK_TO_VALLEY_TOO_LOW"
ZONE_VOLUME_DENSITY_TOO_LOW = "ZONE_VOLUME_DENSITY_TOO_LOW"
ZONE_TPO_DENSITY_TOO_LOW = "ZONE_TPO_DENSITY_TOO_LOW"
ZONE_ACTIVITY_DENSITY_TOO_LOW = "ZONE_ACTIVITY_DENSITY_TOO_LOW"
WIDTH_EXCEEDS_MAXIMUM = "WIDTH_EXCEEDS_MAXIMUM"
OVERLAPS_ACCEPTED_ZONE = "OVERLAPS_ACCEPTED_ZONE"

REJECTION_ORDER = (
    INVALID_PROFILE_TOTAL,
    INVALID_TPO_TOTAL,
    INVALID_ACTIVE_TICK_COUNT,
    PEAK_PERCENTILE_TOO_LOW,
    PEAK_ACTIVITY_TOO_LOW,
    OVERLAPS_VOLUME_POC,
    BASIN_TOO_NARROW,
    NO_VALID_BASIN_SEPARATION,
    PEAK_TO_VALLEY_TOO_LOW,
    ZONE_VOLUME_DENSITY_TOO_LOW,
    ZONE_TPO_DENSITY_TOO_LOW,
    ZONE_ACTIVITY_DENSITY_TOO_LOW,
    WIDTH_EXCEEDS_MAXIMUM,
    OVERLAPS_ACCEPTED_ZONE,
)


def geometric_mean(a: Decimal, b: Decimal) -> Decimal:
    """sqrt(a*b), deterministic and zero-preserving.

    Zero when either input is non-positive, so neither proxy compensates for
    the other's absence.
    """
    if a <= 0 or b <= 0:
        return Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 40
        return (a * b).sqrt()


# ---------------------------------------------------------------------------
# Tick-grid profile


@dataclass(frozen=True, slots=True)
class TickProfile:
    """Volume and TPO on the 0.25-point tick grid, frozen at `freeze_time`."""

    profile_id: str
    window: ProfileWindow
    atr_reference_time: object
    atr_value: Decimal
    low_index: int
    high_index: int
    volume: dict[int, Decimal]
    tpo: dict[int, int]
    poc_index: int
    source_row_ids: tuple[str, ...]
    source_total_volume: Decimal
    profile_range_low: Decimal
    profile_range_high: Decimal
    code_sha: str
    data_partition: str

    @property
    def indices(self) -> range:
        return range(self.low_index, self.high_index + 1)

    def tick_low(self, index: int) -> Decimal:
        return GRID_ORIGIN + Decimal(index) * TICK_SIZE

    def tick_high(self, index: int) -> Decimal:
        return self.tick_low(index) + TICK_SIZE

    def tick_center(self, index: int) -> Decimal:
        return self.tick_low(index) + TICK_SIZE / 2

    @property
    def active_indices(self) -> tuple[int, ...]:
        return tuple(
            i
            for i in self.indices
            if self.volume.get(i, Decimal(0)) > 0 or self.tpo.get(i, 0) > 0
        )


def _tick_profile_id(window: ProfileWindow) -> str:
    key = "|".join(
        [
            "GEN4_TICK",
            window.family.value,
            window.source_session_date,
            window.source_start.isoformat(),
            window.source_end.isoformat(),
            str(TICK_SIZE),
        ]
    )
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def construct_tick_profile(
    bars: list[Bar] | tuple[Bar, ...],
    atr_points: tuple[AtrPoint, ...],
    window: ProfileWindow,
    *,
    code_sha: str = "UNCOMMITTED",
    data_partition: str = "development",
) -> TickProfile:
    """Both proxies on the tick grid, from bars completed by the freeze time.

    Volume is allocated uniformly across every tick a bar occupies, with the
    exact residual carried onto the highest tick so allocation conserves source
    volume exactly. TPO adds one occupancy per occupied tick.
    """
    atr = atr_before(atr_points, window.source_start)
    if atr.available_time > window.source_start:
        raise AssertionError("causal ATR violation")
    source = sorted(
        (
            b
            for b in bars
            if window.source_start <= b.start_time < window.source_end
            and b.close_time <= window.freeze_time
        ),
        key=lambda b: (b.close_time, b.source_row_id),
    )
    if not source:
        raise ValueError("no source bars in profile window")
    row_ids = tuple(b.source_row_id for b in source)
    if len(set(row_ids)) != len(row_ids):
        raise ValueError("duplicate source_row_id in source window")
    if len({b.symbol for b in source}) != 1:
        raise ValueError("profile construction requires exactly one contract symbol")

    volume: dict[int, Decimal] = {}
    tpo: dict[int, int] = {}
    with localcontext() as ctx:
        ctx.prec = 80
        for bar in source:
            indices = intersected_bin_indices(bar.low, bar.high, TICK_SIZE)
            share = (bar.volume / Decimal(len(indices))).quantize(ALLOCATION_QUANTUM)
            contributions = [share] * (len(indices) - 1)
            contributions.append(bar.volume - share * Decimal(len(indices) - 1))
            for index, contribution in zip(indices, contributions):
                volume[index] = volume.get(index, Decimal(0)) + contribution
                tpo[index] = tpo.get(index, 0) + 1
        low_index, high_index = min(volume), max(volume)
        for index in range(low_index, high_index + 1):
            volume.setdefault(index, Decimal(0))
            tpo.setdefault(index, 0)
        source_total_volume = sum((b.volume for b in source), Decimal(0))
        exact_allocated = sum((Fraction(v) for v in volume.values()), Fraction(0))
        residual = Fraction(source_total_volume) - exact_allocated
        volume[high_index] += Decimal(residual.numerator) / Decimal(
            residual.denominator
        )
        if sum((Fraction(v) for v in volume.values()), Fraction(0)) != Fraction(
            source_total_volume
        ):
            raise AssertionError("uniform allocation failed exact volume conservation")

    range_low = min(b.low for b in source)
    range_high = max(b.high for b in source)
    centers = {i: GRID_ORIGIN + (Decimal(i) + Decimal("0.5")) * TICK_SIZE for i in volume}
    total = sum(volume.values(), Decimal(0))
    weighted_mean = sum(
        (centers[i] * w for i, w in volume.items()), Decimal(0)
    ) / total
    poc = select_poc(volume, centers, weighted_mean, (range_low + range_high) / 2)

    return TickProfile(
        profile_id=_tick_profile_id(window),
        window=window,
        atr_reference_time=atr.available_time,
        atr_value=atr.value,
        low_index=low_index,
        high_index=high_index,
        volume=volume,
        tpo=tpo,
        poc_index=poc,
        source_row_ids=row_ids,
        source_total_volume=source_total_volume,
        profile_range_low=range_low,
        profile_range_high=range_high,
        code_sha=code_sha,
        data_partition=data_partition,
    )


# ---------------------------------------------------------------------------
# Densities and smoothing


@dataclass(frozen=True, slots=True)
class ProfileActivity:
    valid: bool
    invalid_reason: str
    active: tuple[int, ...]
    volume_density: dict[int, Decimal]
    tpo_density: dict[int, Decimal]
    raw_activity: dict[int, Decimal]
    smoothed_activity: dict[int, Decimal]
    percentile: dict[int, Decimal]
    half_width_ticks: int
    v_total: Decimal
    t_total: int


def smoothing_half_width_ticks(atr: Decimal) -> int:
    """max(2 ticks, round_half_up(0.05 * ATR / 0.25))."""
    ticks = (SMOOTHING_SPAN_ATR * atr / TICK_SIZE).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return max(MIN_SMOOTHING_HALF_WIDTH_TICKS, int(ticks))


def triangular_weights(half_width: int) -> tuple[int, ...]:
    """Unnormalized integer weights: centre h+1, falling to 1 at the edges."""
    return tuple(
        half_width + 1 - abs(offset) for offset in range(-half_width, half_width + 1)
    )


def smooth(values: dict[int, Decimal], half_width: int, indices: range) -> dict[int, Decimal]:
    """Triangular smoothing, renormalized on the available window at edges."""
    weights = triangular_weights(half_width)
    out: dict[int, Decimal] = {}
    for index in indices:
        numerator = Decimal(0)
        denominator = 0
        for offset in range(-half_width, half_width + 1):
            neighbour = index + offset
            if neighbour not in values:
                continue
            weight = weights[offset + half_width]
            numerator += Decimal(weight) * values[neighbour]
            denominator += weight
        out[index] = numerator / Decimal(denominator) if denominator else Decimal(0)
    return out


def activity_percentile_100(values: dict[int, Decimal]) -> dict[int, Decimal]:
    """percentile = 100 * |{active ticks strictly below x}| / |{active ticks}|.

    Ties share the lowest percentile of their group. Exact Decimal arithmetic
    over integer counts, so the result is platform-independent.
    """
    active = sorted(v for v in values.values() if v > 0)
    if not active:
        return {}
    total = Decimal(len(active))
    ranks: dict[Decimal, Decimal] = {}
    for position, value in enumerate(active):
        if value not in ranks:
            ranks[value] = Decimal(100) * Decimal(position) / total
    return {k: ranks[v] for k, v in values.items() if v > 0}


def profile_activity(profile: TickProfile) -> ProfileActivity:
    """Volume, TPO, composite and smoothed composite densities per tick."""
    indices = profile.indices
    active = profile.active_indices
    v_total = sum(profile.volume.values(), Decimal(0))
    t_total = sum(profile.tpo.values())
    empty: dict[int, Decimal] = {}
    if not active:
        return ProfileActivity(
            False, INVALID_ACTIVE_TICK_COUNT, (), empty, empty, empty, empty, empty,
            smoothing_half_width_ticks(profile.atr_value), v_total, t_total,
        )
    if v_total <= 0:
        return ProfileActivity(
            False, INVALID_PROFILE_TOTAL, active, empty, empty, empty, empty, empty,
            smoothing_half_width_ticks(profile.atr_value), v_total, t_total,
        )
    if t_total <= 0:
        return ProfileActivity(
            False, INVALID_TPO_TOTAL, active, empty, empty, empty, empty, empty,
            smoothing_half_width_ticks(profile.atr_value), v_total, t_total,
        )

    positive_volume = [i for i in indices if profile.volume.get(i, Decimal(0)) > 0]
    positive_tpo = [i for i in indices if profile.tpo.get(i, 0) > 0]
    mean_volume = v_total / Decimal(len(positive_volume))
    mean_tpo = Decimal(t_total) / Decimal(len(positive_tpo))

    volume_density = {i: profile.volume.get(i, Decimal(0)) / mean_volume for i in indices}
    tpo_density = {i: Decimal(profile.tpo.get(i, 0)) / mean_tpo for i in indices}
    raw = {i: geometric_mean(volume_density[i], tpo_density[i]) for i in indices}
    half_width = smoothing_half_width_ticks(profile.atr_value)
    smoothed = smooth(raw, half_width, indices)
    return ProfileActivity(
        True, "", active, volume_density, tpo_density, raw, smoothed,
        activity_percentile_100(smoothed), half_width, v_total, t_total,
    )


# ---------------------------------------------------------------------------
# Zone geometry


def minimum_zone_width_ticks(atr: Decimal) -> int:
    """max(4 ticks, ceil(0.10 * ATR / 0.25)). No zone may be one tick wide."""
    ticks = (MIN_ZONE_WIDTH_ATR * atr / TICK_SIZE).to_integral_value(
        rounding=ROUND_CEILING
    )
    return max(MIN_ZONE_WIDTH_TICKS_FLOOR, int(ticks))


def maximum_zone_width_ticks(atr: Decimal) -> int:
    """floor(0.75 * ATR / 0.25), never smaller than the minimum."""
    ticks = int(
        (MAX_ZONE_WIDTH_ATR * atr / TICK_SIZE).to_integral_value(rounding=ROUND_FLOOR)
    )
    return max(minimum_zone_width_ticks(atr), ticks)


def maximum_poc_zone_width_ticks(atr: Decimal) -> int:
    """floor(1.00 * ATR / 0.25).

    Unlike the non-POC maximum this is **not** raised to the minimum width. The
    POC classification rule is stated literally as
    `minimum width <= POC zone width <= 1.00 ATR`, so when the four-tick
    absolute floor already exceeds 1.00 ATR the rule is unsatisfiable and the
    POC is a `POC_BROAD_DISTRIBUTION`. Clamping here would admit POC zones wider
    than 1.00 ATR and break G4-S05.
    """
    return int(
        (MAX_POC_ZONE_WIDTH_ATR * atr / TICK_SIZE).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )


def _plateaus(smoothed: dict[int, Decimal], indices: range) -> list[list[int]]:
    """Maximal contiguous runs of equal smoothed activity."""
    runs: list[list[int]] = []
    current: list[int] = []
    for index in indices:
        if current and smoothed[index] == smoothed[current[-1]]:
            current.append(index)
        else:
            if current:
                runs.append(current)
            current = [index]
    if current:
        runs.append(current)
    return runs


def peak_plateaus(activity: ProfileActivity, indices: range) -> list[list[int]]:
    """Local maxima and deterministic flat-top maxima of smoothed activity."""
    smoothed = activity.smoothed_activity
    runs = _plateaus(smoothed, indices)
    out = []
    for position, run in enumerate(runs):
        left = smoothed[runs[position - 1][-1]] if position else None
        right = (
            smoothed[runs[position + 1][0]] if position + 1 < len(runs) else None
        )
        value = smoothed[run[0]]
        if value <= 0:
            continue
        if (left is None or value > left) and (right is None or value > right):
            out.append(run)
    return out


@dataclass(frozen=True, slots=True)
class Basin:
    low_index: int
    high_index: int
    left_valley_index: int | None
    right_valley_index: int | None
    left_valley_activity: Decimal | None
    right_valley_activity: Decimal | None

    @property
    def width_ticks(self) -> int:
        return self.high_index - self.low_index + 1


def local_basin(activity: ProfileActivity, profile: TickProfile, plateau: list[int]) -> Basin:
    """Walk out from the plateau to the first valley, floor, edge or 1.00 ATR."""
    smoothed = activity.smoothed_activity
    limit_ticks = int(
        (BASIN_MAX_DISTANCE_ATR * profile.atr_value / TICK_SIZE).to_integral_value(
            rounding=ROUND_FLOOR
        )
    )
    low_edge, high_edge = profile.low_index, profile.high_index

    def walk(start: int, step: int) -> tuple[int, int | None]:
        index = start
        while True:
            nxt = index + step
            if nxt < low_edge or nxt > high_edge:
                return index, None
            if abs(nxt - start) > limit_ticks:
                return index, None
            if smoothed[nxt] <= BASIN_FLOOR_ACTIVITY:
                return nxt, nxt
            after = nxt + step
            is_min = (
                after < low_edge
                or after > high_edge
                or smoothed[after] >= smoothed[nxt]
            ) and smoothed[nxt] < smoothed[index]
            if is_min:
                return nxt, nxt
            index = nxt

    low, left_valley = walk(plateau[0], -1)
    high, right_valley = walk(plateau[-1], 1)
    return Basin(
        low_index=low,
        high_index=high,
        left_valley_index=left_valley,
        right_valley_index=right_valley,
        left_valley_activity=smoothed[left_valley] if left_valley is not None else None,
        right_valley_activity=smoothed[right_valley] if right_valley is not None else None,
    )


def expand_core(
    activity: ProfileActivity,
    plateau: list[int],
    basin: Basin,
    minimum_ticks: int,
) -> tuple[int, int]:
    """70%-of-peak contiguous core, then widened to the minimum inside the basin.

    The stronger side is added first; an exact tie adds the lower price.
    """
    smoothed = activity.smoothed_activity
    peak = smoothed[plateau[0]]
    threshold = max(BASIN_FLOOR_ACTIVITY, CORE_EXPANSION_FRACTION * peak)
    low, high = plateau[0], plateau[-1]

    def candidate(side_low: int, side_high: int) -> tuple[Decimal | None, Decimal | None]:
        below = smoothed[side_low - 1] if side_low - 1 >= basin.low_index else None
        above = smoothed[side_high + 1] if side_high + 1 <= basin.high_index else None
        return below, above

    while True:
        below, above = candidate(low, high)
        below_ok = below is not None and below >= threshold
        above_ok = above is not None and above >= threshold
        if not below_ok and not above_ok:
            break
        if above_ok and (not below_ok or above > below):
            high += 1
        else:
            low -= 1

    while high - low + 1 < minimum_ticks:
        below, above = candidate(low, high)
        if below is None and above is None:
            break
        if above is not None and (below is None or above > below):
            high += 1
        else:
            low -= 1
    return low, high


@dataclass(frozen=True, slots=True)
class HvnZone:
    zone_id: str
    profile_id: str
    physical_zone_id: str
    zone_class: str
    low_index: int
    high_index: int
    width_ticks: int
    zone_low: Decimal
    zone_high: Decimal
    peak_index: int
    peak_price: Decimal
    peak_smoothed_activity: Decimal
    peak_activity_percentile: Decimal
    zone_volume: Decimal
    zone_tpo: int
    zone_volume_density: Decimal
    zone_tpo_density: Decimal
    zone_activity_density: Decimal
    basin_low_index: int
    basin_high_index: int
    left_valley_activity: Decimal | None
    right_valley_activity: Decimal | None
    reference_valley_activity: Decimal | None
    peak_to_valley_ratio: Decimal | None
    minimum_width_ticks: int
    maximum_width_ticks: int
    smoothing_half_width_ticks: int
    atr_value: Decimal
    accepted: bool
    rejection_reason: str

    @property
    def width_points(self) -> Decimal:
        return self.zone_high - self.zone_low

    @property
    def width_atr(self) -> Decimal:
        return self.width_points / self.atr_value

    @property
    def midpoint(self) -> Decimal:
        return (self.zone_low + self.zone_high) / 2

    # Zone interface consumed by the outcome engine.
    @property
    def atomic_id(self) -> str:
        return self.zone_id

    @property
    def atomic_low(self) -> Decimal:
        return self.zone_low

    @property
    def atomic_high(self) -> Decimal:
        return self.zone_high

    def contains(self, price: Decimal) -> bool:
        return self.zone_low <= price < self.zone_high

    def touched_by(self, low: Decimal, high: Decimal) -> bool:
        return not (high < self.zone_low or low >= self.zone_high)

    def distance_atr(self, price: Decimal, atr: Decimal) -> Decimal:
        if self.contains(price):
            return Decimal(0)
        gap = self.zone_low - price if price < self.zone_low else price - self.zone_high
        return gap / atr

    def peak_distance_atr(self, price: Decimal, atr: Decimal) -> Decimal:
        return abs(price - self.peak_price) / atr

    def band(self, expansion_atr: Decimal, atr: Decimal) -> tuple[Decimal, Decimal]:
        pad = expansion_atr * atr
        return self.zone_low - pad, self.zone_high + pad

    def in_band(self, price: Decimal, expansion_atr: Decimal, atr: Decimal) -> bool:
        low, high = self.band(expansion_atr, atr)
        return low <= price < high


def physical_zone_id(
    profile: TickProfile, low_index: int, high_index: int, zone_class: str
) -> str:
    """Identity of the physical zone, independent of the consuming relationship."""
    symbol = profile.source_row_ids[0].split("|")[0] if profile.source_row_ids else ""
    key = "|".join(
        [
            symbol,
            profile.window.freeze_time.isoformat(),
            profile.window.family.value,
            str(low_index),
            str(high_index),
            zone_class,
        ]
    )
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def _zone_densities(
    profile: TickProfile, activity: ProfileActivity, low: int, high: int
) -> tuple[Decimal, int, Decimal, Decimal, Decimal]:
    zone_volume = sum(
        (profile.volume.get(i, Decimal(0)) for i in range(low, high + 1)), Decimal(0)
    )
    zone_tpo = sum(profile.tpo.get(i, 0) for i in range(low, high + 1))
    width_share = Decimal(high - low + 1) / Decimal(len(activity.active))
    volume_density = (zone_volume / activity.v_total) / width_share
    tpo_density = (Decimal(zone_tpo) / Decimal(activity.t_total)) / width_share
    return (
        zone_volume,
        zone_tpo,
        volume_density,
        tpo_density,
        geometric_mean(volume_density, tpo_density),
    )


def _build(
    profile: TickProfile,
    activity: ProfileActivity,
    plateau: list[int],
    *,
    is_poc: bool,
    poc_span: range | None,
) -> HvnZone:
    """One candidate evaluated in the frozen first-failure order."""
    atr = profile.atr_value
    minimum = minimum_zone_width_ticks(atr)
    maximum = maximum_poc_zone_width_ticks(atr) if is_poc else maximum_zone_width_ticks(atr)
    smoothed = activity.smoothed_activity
    peak_index = plateau[len(plateau) // 2]
    peak_value = smoothed[plateau[0]]
    percentile = activity.percentile.get(peak_index, Decimal(0))

    basin = local_basin(activity, profile, plateau)
    low, high = expand_core(activity, plateau, basin, minimum)
    valleys = [
        v
        for v in (basin.left_valley_activity, basin.right_valley_activity)
        if v is not None
    ]
    reference_valley = max(valleys) if valleys else None
    ratio = (
        peak_value / reference_valley
        if reference_valley is not None and reference_valley > 0
        else None
    )
    zone_volume, zone_tpo, v_density, t_density, a_density = _zone_densities(
        profile, activity, low, high
    )
    width = high - low + 1

    reason = ""
    if not is_poc:
        if percentile < MIN_PEAK_ACTIVITY_PERCENTILE:
            reason = PEAK_PERCENTILE_TOO_LOW
        elif peak_value < MIN_PEAK_ACTIVITY_DENSITY:
            reason = PEAK_ACTIVITY_TOO_LOW
        elif poc_span is not None and any(i in poc_span for i in range(low, high + 1)):
            reason = OVERLAPS_VOLUME_POC
    if not reason and basin.width_ticks < minimum:
        reason = BASIN_TOO_NARROW
    if not reason and not is_poc:
        if ratio is None:
            reason = NO_VALID_BASIN_SEPARATION
        elif ratio < MIN_PEAK_TO_VALLEY_RATIO:
            reason = PEAK_TO_VALLEY_TOO_LOW
        elif v_density < MIN_ZONE_VOLUME_DENSITY:
            reason = ZONE_VOLUME_DENSITY_TOO_LOW
        elif t_density < MIN_ZONE_TPO_DENSITY:
            reason = ZONE_TPO_DENSITY_TOO_LOW
        elif a_density < MIN_ZONE_ACTIVITY_DENSITY:
            reason = ZONE_ACTIVITY_DENSITY_TOO_LOW
    if not reason and width > maximum:
        reason = WIDTH_EXCEEDS_MAXIMUM

    if is_poc:
        zone_class = POC_BROAD_DISTRIBUTION if reason == WIDTH_EXCEEDS_MAXIMUM else POC_HVN_ZONE
    else:
        zone_class = (
            BROAD_ACTIVITY_DISTRIBUTION
            if reason == WIDTH_EXCEEDS_MAXIMUM
            else NONPOC_HVN_ZONE
        )

    return HvnZone(
        zone_id=f"{profile.profile_id}-Z{low:07d}",
        profile_id=profile.profile_id,
        physical_zone_id=physical_zone_id(profile, low, high, zone_class),
        zone_class=zone_class,
        low_index=low,
        high_index=high,
        width_ticks=width,
        zone_low=profile.tick_low(low),
        zone_high=profile.tick_high(high),
        peak_index=peak_index,
        peak_price=profile.tick_center(peak_index),
        peak_smoothed_activity=peak_value,
        peak_activity_percentile=percentile,
        zone_volume=zone_volume,
        zone_tpo=zone_tpo,
        zone_volume_density=v_density,
        zone_tpo_density=t_density,
        zone_activity_density=a_density,
        basin_low_index=basin.low_index,
        basin_high_index=basin.high_index,
        left_valley_activity=basin.left_valley_activity,
        right_valley_activity=basin.right_valley_activity,
        reference_valley_activity=reference_valley,
        peak_to_valley_ratio=ratio,
        minimum_width_ticks=minimum,
        maximum_width_ticks=maximum,
        smoothing_half_width_ticks=activity.half_width_ticks,
        atr_value=atr,
        accepted=reason == "",
        rejection_reason=reason,
    )


def _merged_pairs(
    activity: ProfileActivity, zones: list[HvnZone]
) -> set[str]:
    """Candidate pairs whose cores are near and whose valley is shallow.

    Two cores separated by fewer than two ticks whose intervening valley is at
    least 0.85 of the lower peak's activity are one broad activity distribution,
    not two HVN zones.
    """
    smoothed = activity.smoothed_activity
    ordered = sorted(zones, key=lambda z: z.low_index)
    merged: set[str] = set()
    for left, right in zip(ordered, ordered[1:]):
        gap = right.low_index - left.high_index - 1
        if gap >= MERGE_SEPARATION_TICKS:
            continue
        between = [
            smoothed[i] for i in range(left.high_index + 1, right.low_index)
        ]
        lower_peak = min(left.peak_smoothed_activity, right.peak_smoothed_activity)
        valley = min(between) if between else lower_peak
        if valley >= MERGE_VALLEY_FRACTION * lower_peak:
            merged.add(left.zone_id)
            merged.add(right.zone_id)
    return merged


def classify_zones(profile: TickProfile) -> tuple[tuple[HvnZone, ...], ProfileActivity]:
    """Every candidate for one frozen tick profile, accepted and rejected alike.

    Returned in ascending price order. Accepted zones never overlap: candidates
    are resolved strongest peak first, and a weaker candidate overlapping an
    accepted zone is rejected as `OVERLAPS_ACCEPTED_ZONE`.
    """
    activity = profile_activity(profile)
    if not activity.valid:
        return (), activity

    poc_plateau_run = [
        i
        for i in _plateaus(activity.smoothed_activity, profile.indices)
        if profile.poc_index in i
    ]
    poc_run = poc_plateau_run[0] if poc_plateau_run else [profile.poc_index]
    poc_zone = _build(profile, activity, poc_run, is_poc=True, poc_span=None)
    poc_span = range(poc_zone.low_index, poc_zone.high_index + 1)

    candidates = [
        _build(profile, activity, run, is_poc=False, poc_span=poc_span)
        for run in peak_plateaus(activity, profile.indices)
        if profile.poc_index not in run
    ]

    merged = _merged_pairs(
        activity, [z for z in candidates if z.accepted]
    )
    resolved: list[HvnZone] = []
    for zone in candidates:
        if zone.zone_id in merged and zone.accepted:
            resolved.append(
                _replace_rejection(
                    zone, NO_VALID_BASIN_SEPARATION, BROAD_ACTIVITY_DISTRIBUTION
                )
            )
        else:
            resolved.append(zone)

    accepted_spans: list[range] = [poc_span]
    final: list[HvnZone] = []
    for zone in sorted(
        resolved,
        key=lambda z: (-z.peak_smoothed_activity, z.low_index),
    ):
        if zone.accepted and any(
            zone.low_index <= span.stop - 1 and span.start <= zone.high_index
            for span in accepted_spans
        ):
            final.append(
                _replace_rejection(zone, OVERLAPS_ACCEPTED_ZONE, zone.zone_class)
            )
            continue
        if zone.accepted:
            accepted_spans.append(range(zone.low_index, zone.high_index + 1))
        final.append(zone)

    final.append(poc_zone)
    final.sort(key=lambda z: (z.low_index, z.zone_id))
    return tuple(final), activity


def _replace_rejection(zone: HvnZone, reason: str, zone_class: str) -> HvnZone:
    """Re-decide a candidate after cross-candidate resolution.

    The physical identity carries the zone class, so it is recomputed whenever
    the class changes.
    """
    return replace(zone, accepted=False, rejection_reason=reason, zone_class=zone_class)
