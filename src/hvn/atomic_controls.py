"""Generation 3 ordinary-bin control selection.

C01 neutral: an ordinary non-peak window whose weight lies in the profile's
25th-75th percentile band. C02 mass-matched: the ordinary non-peak window whose
weight is closest to the atomic peak without qualifying as a prominent local
peak. Both exclude anything that is, or touches, a qualifying peak, anything
containing the POC, and anything extending beyond the frozen grid.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .atomic import AtomicHvn, neutral_weight_window, ordinary_bin_controls
from .models import FrozenProfile

C01_NEUTRAL = "C01_NEUTRAL_NON_HVN"
C02_MASS_MATCHED = "C02_PROFILE_MASS_MATCHED_NON_HVN"


@dataclass(frozen=True, slots=True)
class ControlZone:
    control_id: str
    profile_id: str
    control_family: str
    start_bin_index: int
    end_bin_index: int
    width_bins: int
    control_low: Decimal
    control_high: Decimal
    control_center: Decimal
    window_weight: Decimal
    matched_atomic_id: str

    @property
    def width_points(self) -> Decimal:
        return self.control_high - self.control_low

    def contains(self, price: Decimal) -> bool:
        return self.control_low <= price < self.control_high

    def touched_by(self, low: Decimal, high: Decimal) -> bool:
        return not (high < self.control_low or low >= self.control_high)

    def distance_atr(self, price: Decimal, atr: Decimal) -> Decimal:
        if self.contains(price):
            return Decimal(0)
        gap = (
            self.control_low - price
            if price < self.control_low
            else price - self.control_high
        )
        return gap / atr

    def peak_distance_atr(self, price: Decimal, atr: Decimal) -> Decimal:
        return abs(price - self.control_center) / atr

    def band(self, expansion_atr: Decimal, atr: Decimal) -> tuple[Decimal, Decimal]:
        pad = expansion_atr * atr
        return self.control_low - pad, self.control_high + pad

    @property
    def peak_price(self) -> Decimal:
        """Centre of the control window, the analogue of the peak price."""
        return self.control_center

    @property
    def atomic_low(self) -> Decimal:
        return self.control_low

    @property
    def atomic_high(self) -> Decimal:
        return self.control_high


def _window_weight(profile: FrozenProfile, start: int, end: int) -> Decimal:
    return sum(
        (b.profile_weight for b in profile.bins if start <= b.bin_index <= end),
        Decimal(0),
    )


def select_controls(
    profile: FrozenProfile,
    atomic: AtomicHvn,
    atomic_hvns: tuple[AtomicHvn, ...],
) -> tuple[ControlZone, ...]:
    """One C01 and one C02 control for `atomic`, when eligible windows exist.

    Selection is deterministic and uses no forward information: candidates are
    ranked by weight distance and then by bin index.
    """
    windows = ordinary_bin_controls(
        profile, atomic_hvns, width_bins=atomic.width_bins
    )
    if not windows:
        return ()
    bins_by_index = {b.bin_index: b for b in profile.bins}
    low_quartile, high_quartile = neutral_weight_window(profile)

    scored = []
    for start, end in windows:
        weight = _window_weight(profile, start, end)
        scored.append((start, end, weight))

    out: list[ControlZone] = []

    neutral = [
        item for item in scored if low_quartile <= item[2] <= high_quartile
    ]
    if neutral:
        # Closest to the middle of the neutral band, then lowest bin index.
        midpoint = (low_quartile + high_quartile) / 2
        start, end, weight = min(
            neutral, key=lambda item: (abs(item[2] - midpoint), item[0])
        )
        out.append(
            _build(profile, bins_by_index, atomic, start, end, weight, C01_NEUTRAL)
        )

    start, end, weight = min(
        scored, key=lambda item: (abs(item[2] - atomic.peak_weight), item[0])
    )
    out.append(
        _build(profile, bins_by_index, atomic, start, end, weight, C02_MASS_MATCHED)
    )
    return tuple(out)


def _build(
    profile: FrozenProfile,
    bins_by_index: dict,
    atomic: AtomicHvn,
    start: int,
    end: int,
    weight: Decimal,
    family: str,
) -> ControlZone:
    low = bins_by_index[start].bin_low
    high = bins_by_index[end].bin_high
    return ControlZone(
        control_id=f"{profile.profile_id}-C{start:04d}-{family[:3]}",
        profile_id=profile.profile_id,
        control_family=family,
        start_bin_index=start,
        end_bin_index=end,
        width_bins=end - start + 1,
        control_low=low,
        control_high=high,
        control_center=(low + high) / 2,
        window_weight=weight,
        matched_atomic_id=atomic.atomic_id,
    )
