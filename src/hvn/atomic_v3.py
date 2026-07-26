"""Composite volume/TPO atomic nodes — Generation 3 Amendment 02.

Non-POC candidates are detected from a composite activity profile, the
geometric mean of the volume and TPO density ratios, and qualified on fixed
density floors. Local prominence and percentiles are recorded as annotations
and may never decide eligibility. POC rules carry over unchanged from
Amendment 01.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .atomic_v2 import (
    INVALID_ACTIVE_BIN_COUNT,
    INVALID_PROFILE_TOTAL,
    INVALID_TPO_TOTAL,
    MAX_ATOMIC_WIDTH_BINS,
    POC_ATOMIC,
    POC_BROAD,
    ProfileNorm,
    local_prominence,
    poc_plateau,
    profile_normalization,
    value_area,
)
from .models import FrozenProfile, ProfileBin

# Fixed Amendment 02 floors. Never tuned after a pilot or an outcome.
MIN_ZONE_VOLUME_DENSITY = Decimal("1.25")
MIN_PEAK_VOLUME_DENSITY = Decimal("1.50")
MIN_ZONE_TPO_DENSITY = Decimal("1.00")
MIN_ZONE_ACTIVITY_DENSITY = Decimal("1.35")
MIN_POC_VOLUME_DENSITY = Decimal("1.50")

NONPOC_ATOMIC_HVN = "NONPOC_ATOMIC_HVN"
ONE_BIN_COMPOSITE_LOCAL_MAXIMUM = "ONE_BIN_COMPOSITE_LOCAL_MAXIMUM"
COMPOSITE_FLAT_TOP_PLATEAU = "COMPOSITE_FLAT_TOP_PLATEAU"
BROAD_COMPOSITE_PLATEAU = "BROAD_COMPOSITE_PLATEAU"

WIDTH_TOO_LARGE = "WIDTH_TOO_LARGE"
OVERLAPS_VOLUME_POC = "OVERLAPS_VOLUME_POC"
ZONE_VOLUME_DENSITY_TOO_LOW = "ZONE_VOLUME_DENSITY_TOO_LOW"
PEAK_VOLUME_DENSITY_TOO_LOW = "PEAK_VOLUME_DENSITY_TOO_LOW"
ZONE_TPO_DENSITY_TOO_LOW = "ZONE_TPO_DENSITY_TOO_LOW"
COMPOSITE_ACTIVITY_TOO_LOW = "COMPOSITE_ACTIVITY_TOO_LOW"


def geometric_mean(a: Decimal, b: Decimal) -> Decimal:
    """sqrt(a*b), deterministic and zero-preserving.

    Returns zero when either input is zero or negative, so neither proxy can
    compensate for the other's absence.
    """
    if a <= 0 or b <= 0:
        return Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 40
        return (a * b).sqrt()


@dataclass(frozen=True, slots=True)
class CompositeNode:
    node_id: str
    profile_id: str
    node_class: str
    geometry: str
    start_bin_index: int
    end_bin_index: int
    width_bins: int
    zone_low: Decimal
    zone_high: Decimal
    peak_price: Decimal
    peak_bin_index: int
    peak_volume: Decimal
    zone_volume_density_ratio: Decimal
    zone_tpo_density_ratio: Decimal
    zone_activity_density_ratio: Decimal
    peak_volume_density_ratio: Decimal
    peak_tpo_density_ratio: Decimal
    peak_activity_density_ratio: Decimal
    volume_percentile: Decimal
    tpo_percentile: Decimal
    activity_percentile: Decimal
    local_volume_prominence: Decimal | None
    local_tpo_prominence: Decimal | None
    local_activity_prominence: Decimal | None
    accepted: bool
    rejection_reason: str

    @property
    def width_points(self) -> Decimal:
        return self.zone_high - self.zone_low

    # Zone interface consumed by the locked Generation 3 outcome engines.
    @property
    def atomic_id(self) -> str:
        return self.node_id

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


def density_ratios(
    profile: FrozenProfile, tpo_by_index: dict, norm: ProfileNorm
) -> tuple[dict, dict, dict]:
    """Per-bin volume, TPO and composite activity density ratios."""
    if not norm.valid:
        return {}, {}, {}
    mean_v = norm.mean_active_volume
    mean_t = norm.mean_active_tpo
    volume, tpo, activity = {}, {}, {}
    for b in profile.bins:
        v = b.profile_weight / mean_v if mean_v > 0 else Decimal(0)
        t = tpo_by_index.get(b.bin_index, Decimal(0)) / mean_t if mean_t > 0 else Decimal(0)
        volume[b.bin_index] = v
        tpo[b.bin_index] = t
        activity[b.bin_index] = geometric_mean(v, t)
    return volume, tpo, activity


def percentile_ranks(values: dict) -> dict:
    """Ties share the lowest percentile of their group, over positive values."""
    positive = sorted(v for v in values.values() if v > 0)
    if not positive:
        return {}
    total = Decimal(len(positive))
    ranks: dict[Decimal, Decimal] = {}
    for index, value in enumerate(positive):
        if value not in ranks:
            ranks[value] = Decimal(index) / total
    return {k: ranks[v] for k, v in values.items() if v > 0}


def composite_local_maxima(
    profile: FrozenProfile, activity: dict
) -> list[list[ProfileBin]]:
    """Maximal equal-activity runs strictly above both neighbours.

    No shoulder expansion, no merging, no truncation.
    """
    bins = [b for b in profile.bins]
    if not bins:
        return []
    runs: list[list[ProfileBin]] = []
    current = [bins[0]]
    for b in bins[1:]:
        if activity.get(b.bin_index, Decimal(0)) == activity.get(
            current[-1].bin_index, Decimal(0)
        ):
            current.append(b)
        else:
            runs.append(current)
            current = [b]
    runs.append(current)

    out = []
    for position, run in enumerate(runs):
        value = activity.get(run[0].bin_index, Decimal(0))
        if value <= 0:
            continue
        left = (
            activity.get(runs[position - 1][-1].bin_index, Decimal(0))
            if position
            else None
        )
        right = (
            activity.get(runs[position + 1][0].bin_index, Decimal(0))
            if position + 1 < len(runs)
            else None
        )
        if (left is None or value > left) and (right is None or value > right):
            out.append(run)
    return out


def classify_composite_nodes(
    profile: FrozenProfile, tpo_by_index: dict
) -> tuple[tuple[CompositeNode, ...], ProfileNorm]:
    """Every composite candidate plus the volume POC, accepted or rejected.

    A physical zone recognised as both the POC and a composite candidate is
    emitted once, as the POC.
    """
    norm = profile_normalization(profile, tpo_by_index)
    bins_by_index = {b.bin_index: b for b in profile.bins}
    volume_d, tpo_d, activity_d = density_ratios(profile, tpo_by_index, norm)
    v_rank = percentile_ranks({b.bin_index: b.profile_weight for b in profile.bins})
    t_rank = percentile_ranks(tpo_by_index)
    a_rank = percentile_ranks(activity_d) if activity_d else {}

    poc_run = poc_plateau(profile)
    poc_span = (
        set(range(poc_run[0].bin_index, poc_run[-1].bin_index + 1)) if poc_run else set()
    )

    candidates: list[tuple[list[ProfileBin], bool]] = []
    if poc_run:
        candidates.append((poc_run, True))
    for run in composite_local_maxima(profile, activity_d):
        span = set(range(run[0].bin_index, run[-1].bin_index + 1))
        if span == poc_span:
            continue          # same physical zone as the POC; never duplicated
        candidates.append((run, False))

    nodes = []
    for run, is_poc in candidates:
        start, end = run[0].bin_index, run[-1].bin_index
        width = end - start + 1
        peak_bin = max(run, key=lambda b: (b.profile_weight, -b.bin_index))
        zone_volume = sum((b.profile_weight for b in run), Decimal(0))
        zone_tpo = sum(
            (tpo_by_index.get(b.bin_index, Decimal(0)) for b in run), Decimal(0)
        )
        if norm.valid:
            width_fraction = Decimal(width) / Decimal(norm.n_active)
            zone_v = (zone_volume / norm.v_total) / width_fraction
            zone_t = (zone_tpo / norm.t_total) / width_fraction
        else:
            zone_v = zone_t = Decimal(0)
        zone_a = geometric_mean(zone_v, zone_t)

        if is_poc:
            geometry = (
                COMPOSITE_FLAT_TOP_PLATEAU if width > 1 else ONE_BIN_COMPOSITE_LOCAL_MAXIMUM
            )
            node_class = POC_ATOMIC if width <= MAX_ATOMIC_WIDTH_BINS else POC_BROAD
        else:
            geometry = (
                ONE_BIN_COMPOSITE_LOCAL_MAXIMUM
                if width == 1
                else (
                    COMPOSITE_FLAT_TOP_PLATEAU
                    if width <= MAX_ATOMIC_WIDTH_BINS
                    else BROAD_COMPOSITE_PLATEAU
                )
            )
            node_class = NONPOC_ATOMIC_HVN

        reason = _rejection_reason(
            norm=norm,
            width=width,
            is_poc=is_poc,
            overlaps_poc=(not is_poc) and bool(poc_span & set(range(start, end + 1))),
            zone_v=zone_v,
            zone_t=zone_t,
            zone_a=zone_a,
            peak_v=volume_d.get(peak_bin.bin_index, Decimal(0)),
        )
        nodes.append(
            CompositeNode(
                node_id=f"{profile.profile_id}-N{start:06d}",
                profile_id=profile.profile_id,
                node_class=node_class,
                geometry=geometry,
                start_bin_index=start,
                end_bin_index=end,
                width_bins=width,
                zone_low=bins_by_index[start].bin_low,
                zone_high=bins_by_index[end].bin_high,
                peak_price=peak_bin.bin_center,
                peak_bin_index=peak_bin.bin_index,
                peak_volume=peak_bin.profile_weight,
                zone_volume_density_ratio=zone_v,
                zone_tpo_density_ratio=zone_t,
                zone_activity_density_ratio=zone_a,
                peak_volume_density_ratio=volume_d.get(peak_bin.bin_index, Decimal(0)),
                peak_tpo_density_ratio=tpo_d.get(peak_bin.bin_index, Decimal(0)),
                peak_activity_density_ratio=activity_d.get(
                    peak_bin.bin_index, Decimal(0)
                ),
                volume_percentile=v_rank.get(peak_bin.bin_index, Decimal(0)),
                tpo_percentile=t_rank.get(peak_bin.bin_index, Decimal(0)),
                activity_percentile=a_rank.get(peak_bin.bin_index, Decimal(0)),
                local_volume_prominence=local_prominence(profile, run),
                local_tpo_prominence=_prominence_from(
                    profile, run, tpo_by_index
                ),
                local_activity_prominence=_prominence_from(
                    profile, run, activity_d
                ),
                accepted=reason == "",
                rejection_reason=reason,
            )
        )
    nodes.sort(key=lambda n: n.start_bin_index)
    return tuple(nodes), norm


def _prominence_from(
    profile: FrozenProfile, run: list[ProfileBin], weights: dict
) -> Decimal | None:
    """Descriptive prominence against the +/- 0.50 ATR neighbourhood median."""
    radius = profile.atr_value * Decimal("0.50")
    centre = run[len(run) // 2].bin_center
    plateau = {b.bin_index for b in run}
    neighbourhood = sorted(
        weights.get(b.bin_index, Decimal(0))
        for b in profile.bins
        if b.bin_index not in plateau and abs(b.bin_center - centre) <= radius
    )
    if len(neighbourhood) < 2:
        return None
    middle = len(neighbourhood) // 2
    median = (
        neighbourhood[middle]
        if len(neighbourhood) % 2
        else (neighbourhood[middle - 1] + neighbourhood[middle]) / 2
    )
    if median <= 0:
        return None
    return weights.get(run[0].bin_index, Decimal(0)) / median


def _rejection_reason(
    *,
    norm: ProfileNorm,
    width: int,
    is_poc: bool,
    overlaps_poc: bool,
    zone_v: Decimal,
    zone_t: Decimal,
    zone_a: Decimal,
    peak_v: Decimal,
) -> str:
    """First failed condition. Prominence and percentile never appear here."""
    if not norm.valid:
        return norm.invalid_reason
    if width > MAX_ATOMIC_WIDTH_BINS:
        return WIDTH_TOO_LARGE
    if is_poc:
        # Amendment 01 POC rules, carried over unchanged.
        if zone_v < MIN_POC_VOLUME_DENSITY:
            return ZONE_VOLUME_DENSITY_TOO_LOW
        return ""
    if overlaps_poc:
        return OVERLAPS_VOLUME_POC
    if zone_v < MIN_ZONE_VOLUME_DENSITY:
        return ZONE_VOLUME_DENSITY_TOO_LOW
    if peak_v < MIN_PEAK_VOLUME_DENSITY:
        return PEAK_VOLUME_DENSITY_TOO_LOW
    if zone_t < MIN_ZONE_TPO_DENSITY:
        return ZONE_TPO_DENSITY_TOO_LOW
    if zone_a < MIN_ZONE_ACTIVITY_DENSITY:
        return COMPOSITE_ACTIVITY_TOO_LOW
    return ""
