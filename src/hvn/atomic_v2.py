"""Session-normalized atomic nodes — Generation 3 Amendment 01.

Every threshold is normalized inside the single completed frozen source profile
that produced the node, so a quiet overnight profile and a busy RTH profile are
never compared by raw volume. See STAGE_02_GENERATION_3_AMENDMENT_01.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import FrozenProfile, ProfileBin

# Frozen thresholds. Supplied by authorization; never searched.
MAX_ATOMIC_WIDTH_BINS = 5
MIN_ZONE_VOLUME_DENSITY = Decimal("1.50")
MIN_ZONE_TPO_DENSITY = Decimal("1.25")
MIN_PEAK_VOLUME_PERCENTILE = Decimal("0.75")
MIN_LOCAL_PROMINENCE = Decimal("1.50")
VALUE_AREA_TARGET = Decimal("0.70")
PROMINENCE_RADIUS_ATR = Decimal("0.50")

ONE_BIN_LOCAL_MAXIMUM = "ONE_BIN_LOCAL_MAXIMUM"
FLAT_TOP_PLATEAU = "FLAT_TOP_PLATEAU"
BROAD_HIGH_VOLUME_PLATEAU = "BROAD_HIGH_VOLUME_PLATEAU"

POC_ATOMIC = "POC_ATOMIC"
POC_BROAD = "POC_BROAD"
NONPOC_ATOMIC_HVN = "NONPOC_ATOMIC_HVN"

WIDTH_TOO_LARGE = "WIDTH_TOO_LARGE"
VOLUME_DENSITY_TOO_LOW = "VOLUME_DENSITY_TOO_LOW"
TPO_DENSITY_TOO_LOW = "TPO_DENSITY_TOO_LOW"
VOLUME_PERCENTILE_TOO_LOW = "VOLUME_PERCENTILE_TOO_LOW"
LOCAL_PROMINENCE_TOO_LOW = "LOCAL_PROMINENCE_TOO_LOW"
INVALID_PROFILE_TOTAL = "INVALID_PROFILE_TOTAL"
INVALID_TPO_TOTAL = "INVALID_TPO_TOTAL"
INVALID_ACTIVE_BIN_COUNT = "INVALID_ACTIVE_BIN_COUNT"
OVERLAPS_POC = "OVERLAPS_POC"


@dataclass(frozen=True, slots=True)
class ProfileNorm:
    """Profile-level quantities, frozen at the profile freeze time."""

    v_total: Decimal
    t_total: Decimal
    n_active: int
    valid: bool
    invalid_reason: str

    @property
    def mean_active_volume(self) -> Decimal:
        return self.v_total / Decimal(self.n_active)

    @property
    def mean_active_tpo(self) -> Decimal:
        return self.t_total / Decimal(self.n_active)


@dataclass(frozen=True, slots=True)
class ValueArea:
    low_bin_index: int
    high_bin_index: int
    poc_low_bin_index: int
    poc_high_bin_index: int
    low_price: Decimal
    high_price: Decimal
    poc_price: Decimal
    covered_share: Decimal
    bin_count: int


@dataclass(frozen=True, slots=True)
class AtomicNodeV2:
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
    zone_volume: Decimal
    zone_tpo: Decimal
    zone_volume_share: Decimal
    zone_tpo_share: Decimal
    zone_volume_density_ratio: Decimal
    zone_tpo_density_ratio: Decimal
    peak_volume_percentile: Decimal
    local_volume_prominence: Decimal | None
    accepted: bool
    rejection_reason: str

    @property
    def width_points(self) -> Decimal:
        return self.zone_high - self.zone_low

    # The zone interface used by the locked Generation 3 outcome engines.
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
        gap = (
            self.zone_low - price if price < self.zone_low else price - self.zone_high
        )
        return gap / atr

    def peak_distance_atr(self, price: Decimal, atr: Decimal) -> Decimal:
        return abs(price - self.peak_price) / atr

    def band(self, expansion_atr: Decimal, atr: Decimal) -> tuple[Decimal, Decimal]:
        pad = expansion_atr * atr
        return self.zone_low - pad, self.zone_high + pad

    def in_band(self, price: Decimal, expansion_atr: Decimal, atr: Decimal) -> bool:
        low, high = self.band(expansion_atr, atr)
        return low <= price < high


def _tpo_weights(profile: FrozenProfile, tpo_profile: FrozenProfile | None) -> dict:
    """TPO count per bin index, taken from the independent TPO profile.

    When no TPO profile is supplied the volume profile's own weights are used,
    which is only correct when that profile is itself the TPO construction.
    """
    source = tpo_profile if tpo_profile is not None else profile
    return {b.bin_index: b.profile_weight for b in source.bins}


def profile_normalization(
    profile: FrozenProfile, tpo_by_index: dict
) -> ProfileNorm:
    v_total = sum((b.profile_weight for b in profile.bins), Decimal(0))
    t_total = sum(tpo_by_index.values(), Decimal(0))
    n_active = sum(
        1
        for b in profile.bins
        if b.profile_weight > 0 or tpo_by_index.get(b.bin_index, Decimal(0)) > 0
    )
    if n_active <= 0:
        return ProfileNorm(v_total, t_total, 0, False, INVALID_ACTIVE_BIN_COUNT)
    if v_total <= 0:
        return ProfileNorm(v_total, t_total, n_active, False, INVALID_PROFILE_TOTAL)
    if t_total <= 0:
        return ProfileNorm(v_total, t_total, n_active, False, INVALID_TPO_TOTAL)
    return ProfileNorm(v_total, t_total, n_active, True, "")


def volume_percentiles(profile: FrozenProfile) -> dict[int, Decimal]:
    """Frozen convention: ties share the lowest percentile of their group.

    percentile_i = |{positive bins with weight strictly less than w_i}| /
                   |{positive bins}|
    """
    positive = [b.profile_weight for b in profile.bins if b.profile_weight > 0]
    if not positive:
        return {}
    ordered = sorted(positive)
    total = Decimal(len(ordered))
    ranks: dict[Decimal, Decimal] = {}
    for index, weight in enumerate(ordered):
        if weight not in ranks:
            ranks[weight] = Decimal(index) / total
    return {
        b.bin_index: ranks[b.profile_weight]
        for b in profile.bins
        if b.profile_weight > 0
    }


def _maximal_runs(bins: tuple[ProfileBin, ...]) -> list[list[ProfileBin]]:
    """Maximal contiguous runs of equal weight."""
    runs: list[list[ProfileBin]] = []
    current: list[ProfileBin] = []
    for bin_ in bins:
        if current and bin_.profile_weight == current[-1].profile_weight:
            current.append(bin_)
        else:
            if current:
                runs.append(current)
            current = [bin_]
    if current:
        runs.append(current)
    return runs


def local_maxima(profile: FrozenProfile) -> list[list[ProfileBin]]:
    """One-bin maxima and flat-top plateaus: runs strictly above both sides.

    No 50% shoulder expansion, no merging of separate peaks, no growth through
    lower-weight bins.
    """
    bins = profile.bins
    runs = _maximal_runs(bins)
    by_index = {b.bin_index: b for b in bins}
    out = []
    for position, run in enumerate(runs):
        left = runs[position - 1][-1].profile_weight if position else None
        right = (
            runs[position + 1][0].profile_weight
            if position + 1 < len(runs)
            else None
        )
        above_left = left is None or run[0].profile_weight > left
        above_right = right is None or run[-1].profile_weight > right
        if above_left and above_right and run[0].profile_weight > 0:
            out.append(run)
    return out


def poc_plateau(profile: FrozenProfile) -> list[ProfileBin]:
    """The contiguous tied maximum-volume plateau.

    A non-contiguous tie resolves to the run containing the lowest bin index.
    """
    peak = max(b.profile_weight for b in profile.bins)
    for run in _maximal_runs(profile.bins):
        if run[0].profile_weight == peak:
            return run
    return []


def local_prominence(
    profile: FrozenProfile, run: list[ProfileBin]
) -> Decimal | None:
    """Peak weight over the median of the +/- 0.50 ATR neighbourhood.

    Bins of the candidate plateau are excluded. A zero or absent baseline makes
    prominence undefined, which fails the condition rather than passing it.
    """
    radius = profile.atr_value * PROMINENCE_RADIUS_ATR
    centre = run[len(run) // 2].bin_center
    plateau = {b.bin_index for b in run}
    neighbourhood = [
        b.profile_weight
        for b in profile.bins
        if b.bin_index not in plateau and abs(b.bin_center - centre) <= radius
    ]
    if len(neighbourhood) < 2:
        return None
    ordered = sorted(neighbourhood)
    middle = len(ordered) // 2
    median = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2
    )
    if median <= 0:
        return None
    return run[0].profile_weight / median


def value_area(
    weights: dict[int, Decimal],
    bins_by_index: dict[int, ProfileBin],
    total: Decimal,
    *,
    target: Decimal = VALUE_AREA_TARGET,
) -> ValueArea | None:
    """Rough contiguous 70% value area, expanded one bin at a time.

    Starts from the complete tied maximum plateau, always adds the adjacent
    side holding more weight, and breaks an exact tie by adding the lower side.
    The final bin may overshoot the target; the result is never forced to 70%.
    """
    if not weights or total <= 0:
        return None
    ordered = sorted(weights)
    peak = max(weights.values())
    start = end = None
    for index in ordered:
        if weights[index] == peak:
            start = end = index
            while end + 1 in weights and weights[end + 1] == peak:
                end += 1
            break
    if start is None:
        return None
    covered = sum(
        (weights[i] for i in range(start, end + 1)), Decimal(0)
    )
    low, high = start, end
    while covered < target * total:
        below = weights.get(low - 1)
        above = weights.get(high + 1)
        if below is None and above is None:
            break
        if above is None or (below is not None and below >= above):
            # Exact tie adds the lower side.
            low -= 1
            covered += below
        else:
            high += 1
            covered += above
    return ValueArea(
        low_bin_index=low,
        high_bin_index=high,
        poc_low_bin_index=start,
        poc_high_bin_index=end,
        low_price=bins_by_index[low].bin_low,
        high_price=bins_by_index[high].bin_high,
        poc_price=bins_by_index[start].bin_center,
        covered_share=covered / total,
        bin_count=high - low + 1,
    )


def classify_nodes(
    profile: FrozenProfile,
    tpo_by_index: dict,
    *,
    prominence_threshold: Decimal = MIN_LOCAL_PROMINENCE,
) -> tuple[tuple[AtomicNodeV2, ...], ProfileNorm]:
    """All candidates for one frozen profile, accepted and rejected alike."""
    norm = profile_normalization(profile, tpo_by_index)
    bins_by_index = {b.bin_index: b for b in profile.bins}
    percentiles = volume_percentiles(profile)
    poc_run = poc_plateau(profile)
    poc_span = (
        range(poc_run[0].bin_index, poc_run[-1].bin_index + 1) if poc_run else range(0)
    )

    candidates = list(local_maxima(profile))
    # The POC plateau is always evaluated, even when it is not a local maximum.
    if poc_run and not any(
        run[0].bin_index == poc_run[0].bin_index for run in candidates
    ):
        candidates.append(poc_run)

    nodes = []
    for run in candidates:
        start, end = run[0].bin_index, run[-1].bin_index
        width = end - start + 1
        is_poc = bool(poc_run) and start == poc_run[0].bin_index
        zone_volume = sum((b.profile_weight for b in run), Decimal(0))
        zone_tpo = sum(
            (tpo_by_index.get(b.bin_index, Decimal(0)) for b in run), Decimal(0)
        )
        peak_bin = max(run, key=lambda b: (b.profile_weight, -b.bin_index))
        geometry = (
            ONE_BIN_LOCAL_MAXIMUM
            if width == 1
            else (
                FLAT_TOP_PLATEAU
                if width <= MAX_ATOMIC_WIDTH_BINS
                else BROAD_HIGH_VOLUME_PLATEAU
            )
        )
        if norm.valid:
            share_v = zone_volume / norm.v_total
            share_t = zone_tpo / norm.t_total
            width_fraction = Decimal(width) / Decimal(norm.n_active)
            density_v = share_v / width_fraction
            density_t = share_t / width_fraction
        else:
            share_v = share_t = density_v = density_t = Decimal(0)
        percentile = percentiles.get(peak_bin.bin_index, Decimal(0))
        prominence = local_prominence(profile, run)

        node_class = (
            (POC_ATOMIC if width <= MAX_ATOMIC_WIDTH_BINS else POC_BROAD)
            if is_poc
            else NONPOC_ATOMIC_HVN
        )
        reason = _rejection_reason(
            norm=norm,
            width=width,
            density_v=density_v,
            density_t=density_t,
            percentile=percentile,
            prominence=prominence,
            is_poc=is_poc,
            overlaps_poc=(not is_poc) and any(i in poc_span for i in range(start, end + 1)),
        )
        nodes.append(
            AtomicNodeV2(
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
                zone_volume=zone_volume,
                zone_tpo=zone_tpo,
                zone_volume_share=share_v,
                zone_tpo_share=share_t,
                zone_volume_density_ratio=density_v,
                zone_tpo_density_ratio=density_t,
                peak_volume_percentile=percentile,
                local_volume_prominence=prominence,
                accepted=reason == "",
                rejection_reason=reason,
            )
        )
    nodes.sort(key=lambda n: n.start_bin_index)
    return tuple(nodes), norm


def _rejection_reason(
    *,
    norm: ProfileNorm,
    width: int,
    density_v: Decimal,
    density_t: Decimal,
    percentile: Decimal,
    prominence: Decimal | None,
    is_poc: bool,
    overlaps_poc: bool,
) -> str:
    """First failed condition, in a fixed order."""
    if not norm.valid:
        return norm.invalid_reason
    if width > MAX_ATOMIC_WIDTH_BINS:
        return WIDTH_TOO_LARGE
    if density_v < MIN_ZONE_VOLUME_DENSITY:
        return VOLUME_DENSITY_TOO_LOW
    if is_poc:
        # Exempt from TPO density and local prominence, never from width or
        # volume concentration.
        return ""
    if overlaps_poc:
        return OVERLAPS_POC
    if density_t < MIN_ZONE_TPO_DENSITY:
        return TPO_DENSITY_TOO_LOW
    if percentile < MIN_PEAK_VOLUME_PERCENTILE:
        return VOLUME_PERCENTILE_TOO_LOW
    if prominence is None or prominence < MIN_LOCAL_PROMINENCE:
        return LOCAL_PROMINENCE_TOO_LOW
    return ""
