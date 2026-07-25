"""Generation 3 atomic HVN extraction.

An atomic HVN is one locally prominent peak bin, or one contiguous plateau of
exactly equal-weight adjacent peak bins. It is the `PeakCandidate` produced by
the locked Stage 1 rules, taken *before* `extract_hvns()` expands through bins
at 50% of peak weight and merges touching zones. No locked peak rule changes
here; this module only refuses the expansion and the merge.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .hvn import peak_candidates
from .models import FrozenProfile, PeakCandidate

TICK_SIZE = Decimal("0.25")


@dataclass(frozen=True, slots=True)
class AtomicHvn:
    atomic_id: str
    profile_id: str
    candidate_id: str
    start_bin_index: int
    end_bin_index: int
    width_bins: int
    atomic_low: Decimal
    atomic_high: Decimal
    peak_price: Decimal
    peak_weight: Decimal
    local_baseline: Decimal | None
    prominence_ratio: Decimal | None
    prominence_threshold: Decimal
    contains_poc: bool
    is_plateau: bool
    peak_weight_share: Decimal

    @property
    def width_points(self) -> Decimal:
        return self.atomic_high - self.atomic_low

    def contains(self, price: Decimal) -> bool:
        """Half-open containment: [atomic_low, atomic_high)."""
        return self.atomic_low <= price < self.atomic_high

    def touched_by(self, low: Decimal, high: Decimal) -> bool:
        """True when any valid tick in the inclusive bar range lies inside.

        The bar range is inclusive of its high, but the zone is half-open, so a
        bar whose high exactly equals atomic_high does not touch unless some
        lower tick reaches atomic_low.
        """
        if high < self.atomic_low or low >= self.atomic_high:
            return False
        return True

    def distance_atr(self, price: Decimal, atr: Decimal) -> Decimal:
        """Zero inside the zone, else the gap to the nearest boundary over ATR."""
        if self.contains(price):
            return Decimal(0)
        gap = (
            self.atomic_low - price
            if price < self.atomic_low
            else price - self.atomic_high
        )
        return gap / atr

    def peak_distance_atr(self, price: Decimal, atr: Decimal) -> Decimal:
        return abs(price - self.peak_price) / atr

    def band(self, expansion_atr: Decimal, atr: Decimal) -> tuple[Decimal, Decimal]:
        """The atomic zone expanded by `expansion_atr` ATR on each side."""
        pad = expansion_atr * atr
        return self.atomic_low - pad, self.atomic_high + pad

    def in_band(
        self, price: Decimal, expansion_atr: Decimal, atr: Decimal
    ) -> bool:
        low, high = self.band(expansion_atr, atr)
        return low <= price < high


def extract_atomic_hvns(
    profile: FrozenProfile, prominence_threshold: Decimal
) -> tuple[AtomicHvn, ...]:
    """Every qualifying local peak, preserved as a separate atomic feature.

    Peaks are neither expanded nor merged, so two adjacent qualifying peaks
    remain two atomic HVNs.
    """
    bins_by_index = {bin_.bin_index: bin_ for bin_ in profile.bins}
    poc_index = profile.poc_bin_index
    out: list[AtomicHvn] = []
    for candidate in peak_candidates(profile, prominence_threshold):
        if not candidate.qualifies:
            continue
        start, end = candidate.start_bin_index, candidate.end_bin_index
        span = [bins_by_index[i] for i in range(start, end + 1)]
        out.append(
            AtomicHvn(
                atomic_id=f"{candidate.candidate_id}-A{prominence_threshold}",
                profile_id=profile.profile_id,
                candidate_id=candidate.candidate_id,
                start_bin_index=start,
                end_bin_index=end,
                width_bins=end - start + 1,
                atomic_low=span[0].bin_low,
                atomic_high=span[-1].bin_high,
                peak_price=candidate.peak_price,
                peak_weight=candidate.peak_weight,
                local_baseline=candidate.local_baseline,
                prominence_ratio=candidate.prominence_ratio,
                prominence_threshold=prominence_threshold,
                contains_poc=start <= poc_index <= end,
                is_plateau=end > start,
                peak_weight_share=sum(
                    (bin_.weight_share for bin_ in span), Decimal(0)
                ),
            )
        )
    return tuple(out)


def ordinary_bin_controls(
    profile: FrozenProfile,
    atomic_hvns: tuple[AtomicHvn, ...],
    *,
    width_bins: int,
) -> tuple[tuple[int, int], ...]:
    """Contiguous ordinary-bin windows of `width_bins`, eligible as controls.

    A window is excluded when it is part of, or touches, any qualifying atomic
    peak or plateau, when it contains the profile POC, or when it extends
    beyond the frozen grid.
    """
    indices = [bin_.bin_index for bin_ in profile.bins]
    if not indices or width_bins <= 0:
        return ()
    lowest, highest = min(indices), max(indices)
    # Every index inside a peak, plus one bin of separation on each side.
    blocked: set[int] = set()
    for atomic in atomic_hvns:
        for index in range(atomic.start_bin_index - 1, atomic.end_bin_index + 2):
            blocked.add(index)
    blocked.add(profile.poc_bin_index)
    windows = []
    for start in range(lowest, highest - width_bins + 2):
        end = start + width_bins - 1
        if end > highest:
            break
        if any(index in blocked for index in range(start, end + 1)):
            continue
        windows.append((start, end))
    return tuple(windows)


def neutral_weight_window(profile: FrozenProfile) -> tuple[Decimal, Decimal]:
    """The 25th and 75th percentile of the profile-bin weight distribution.

    Uses the same exact type-7 interpolation as the rest of the project.
    """
    weights = sorted(bin_.profile_weight for bin_ in profile.bins)
    if not weights:
        return Decimal(0), Decimal(0)

    def quantile(fraction: Decimal) -> Decimal:
        position = (Decimal(len(weights)) - 1) * fraction
        lower = int(position)
        upper = min(lower + 1, len(weights) - 1)
        remainder = position - Decimal(lower)
        return weights[lower] + (weights[upper] - weights[lower]) * remainder

    return quantile(Decimal("0.25")), quantile(Decimal("0.75"))
