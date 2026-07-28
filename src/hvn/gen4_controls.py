"""Generation 4 control zones.

Implements `STAGE_02_GENERATION_4_CONTROL_SPEC.md`. Controls are drawn from the
same frozen tick profile as the treated zone and to the **same width**, so that
a wider interval cannot manufacture an apparent effect: a wide zone catches more
closes simply by being wide.

```text
C01_NEUTRAL           an ordinary profile region of the same width
C02_ACTIVITY_MATCHED  the same, and carrying comparable composite activity, so
                      the contrast isolates peak geometry rather than the raw
                      amount of volume and time-at-price
```

Controls are selected from frozen structural information only. No post-touch
quantity enters selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .zones_v4 import ProfileActivity, TickProfile, geometric_mean

C01_NEUTRAL = "C01_NEUTRAL"
C02_ACTIVITY_MATCHED = "C02_ACTIVITY_MATCHED"

# Amendment 02 / control spec: C02 must sit in a bounded activity band around
# its treated counterpart.
C02_ACTIVITY_RATIO_LOW = Decimal("0.80")
C02_ACTIVITY_RATIO_HIGH = Decimal("1.25")


@dataclass(frozen=True, slots=True)
class ControlZone:
    control_id: str
    profile_id: str
    control_family: str
    matched_zone_id: str
    low_index: int
    high_index: int
    width_ticks: int
    control_low: Decimal
    control_high: Decimal
    zone_volume_density: Decimal
    zone_tpo_density: Decimal
    zone_activity_density: Decimal
    atr_value: Decimal

    @property
    def width_points(self) -> Decimal:
        return self.control_high - self.control_low

    # The same interval interface the outcome engine uses for treated zones.
    def contains(self, price: Decimal) -> bool:
        return self.control_low <= price < self.control_high

    def touched_by(self, low: Decimal, high: Decimal) -> bool:
        return not (high < self.control_low or low >= self.control_high)


def _window_densities(
    profile: TickProfile, activity: ProfileActivity, low: int, high: int
) -> tuple[Decimal, Decimal, Decimal]:
    volume = sum(
        (profile.volume.get(i, Decimal(0)) for i in range(low, high + 1)), Decimal(0)
    )
    tpo = sum(profile.tpo.get(i, 0) for i in range(low, high + 1))
    width_share = Decimal(high - low + 1) / Decimal(len(activity.active))
    v = (volume / activity.v_total) / width_share
    t = (Decimal(tpo) / Decimal(activity.t_total)) / width_share
    return v, t, geometric_mean(v, t)


def select_controls(
    profile: TickProfile,
    activity: ProfileActivity,
    accepted_zones,
    treated,
    *,
    taken: set[int],
) -> list[ControlZone]:
    """One C01 and one C02 control for `treated`, or fewer if none is eligible.

    A control window must lie inside the profile's active range, must not
    overlap the volume POC, any accepted zone, any broad distribution already
    recorded, or a window already taken by another control in this lane.

    Selection is deterministic: eligible windows are scanned from the lowest
    tick index, and the one whose centre is nearest the treated zone's centre
    wins, with the lower index breaking an exact tie. Nearness is a structural
    criterion known at freeze time and keeps the control in comparable price
    territory without ever consulting a forward outcome.
    """
    width = treated.high_index - treated.low_index + 1
    blocked: set[int] = set(taken)
    blocked.add(profile.poc_index)
    for zone in accepted_zones:
        blocked.update(range(zone.low_index, zone.high_index + 1))

    active = set(activity.active)
    treated_centre = Decimal(treated.low_index + treated.high_index)

    candidates: list[tuple[Decimal, int, int, tuple[Decimal, Decimal, Decimal]]] = []
    for low in range(profile.low_index, profile.high_index - width + 2):
        high = low + width - 1
        window = range(low, high + 1)
        if any(i in blocked for i in window):
            continue
        if not all(i in active for i in window):
            continue
        densities = _window_densities(profile, activity, low, high)
        distance = abs(Decimal(low + high) - treated_centre)
        candidates.append((distance, low, high, densities))

    if not candidates:
        return []
    candidates.sort(key=lambda c: (c[0], c[1]))

    out: list[ControlZone] = []
    used: set[int] = set()

    def build(family: str, low: int, high: int, densities) -> ControlZone:
        v, t, a = densities
        return ControlZone(
            control_id=f"{treated.zone_id}-{family}",
            profile_id=profile.profile_id,
            control_family=family,
            matched_zone_id=treated.zone_id,
            low_index=low,
            high_index=high,
            width_ticks=high - low + 1,
            control_low=profile.tick_low(low),
            control_high=profile.tick_high(high),
            zone_volume_density=v,
            zone_tpo_density=t,
            zone_activity_density=a,
            atr_value=profile.atr_value,
        )

    # C01: the nearest eligible window of the same width, no activity condition.
    for distance, low, high, densities in candidates:
        out.append(build(C01_NEUTRAL, low, high, densities))
        used.update(range(low, high + 1))
        break

    # C02: the nearest eligible window whose composite activity sits inside the
    # frozen band around the treated zone's own activity.
    treated_activity = treated.zone_activity_density
    if treated_activity > 0:
        low_bound = C02_ACTIVITY_RATIO_LOW * treated_activity
        high_bound = C02_ACTIVITY_RATIO_HIGH * treated_activity
        for distance, low, high, densities in candidates:
            if any(i in used for i in range(low, high + 1)):
                continue
            if not (low_bound <= densities[2] <= high_bound):
                continue
            out.append(build(C02_ACTIVITY_MATCHED, low, high, densities))
            used.update(range(low, high + 1))
            break

    return out
