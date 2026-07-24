from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import FrozenProfile, HvnNode, PeakCandidate


@dataclass(frozen=True, slots=True)
class ControlZone:
    control_zone_id: str
    control_family: str
    start_bin_index: int
    end_bin_index: int
    low: Decimal
    high: Decimal
    width_bins: int
    mean_bin_weight: Decimal
    zone_weight: Decimal
    zone_weight_share: Decimal
    mass_proportional_difference: Decimal | None


def percentile_type7(values: list[Decimal] | tuple[Decimal, ...], probability: Decimal) -> Decimal:
    if not values:
        raise ValueError("percentile requires values")
    if probability < 0 or probability > 1:
        raise ValueError("probability outside [0, 1]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * Decimal(len(ordered) - 1)
    lower = int(position)
    fraction = position - Decimal(lower)
    return ordered[lower] + fraction * (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower])


def _candidate_windows(
    profile: FrozenProfile,
    nodes: tuple[HvnNode, ...],
    width_bins: int,
) -> list[tuple[int, int, tuple]]:
    bins = profile.bins
    if width_bins < 1 or width_bins > len(bins):
        return []
    poc = profile.poc_bin_index
    excluded_ranges = [
        (
            next(bin_.bin_index for bin_ in bins if bin_.bin_low == node.hvn_low),
            next(bin_.bin_index for bin_ in bins if bin_.bin_high == node.hvn_high),
        )
        for node in nodes
    ]
    out = []
    for offset in range(len(bins) - width_bins + 1):
        window = bins[offset : offset + width_bins]
        indices = [bin_.bin_index for bin_ in window]
        if indices != list(range(indices[0], indices[0] + width_bins)):
            continue
        start, end = indices[0], indices[-1]
        if start <= poc <= end:
            continue
        if any(not (end < low - 1 or start > high + 1) for low, high in excluded_ranges):
            continue
        out.append((start, end, window))
    return out


def neutral_controls(
    profile: FrozenProfile,
    nodes: tuple[HvnNode, ...],
    *,
    width_bins: int,
) -> tuple[ControlZone, ...]:
    weights = [bin_.profile_weight for bin_ in profile.bins]
    q25 = percentile_type7(weights, Decimal("0.25"))
    q75 = percentile_type7(weights, Decimal("0.75"))
    total = sum(weights, Decimal(0))
    result = []
    for start, end, window in _candidate_windows(profile, nodes, width_bins):
        zone_weight = sum((bin_.profile_weight for bin_ in window), Decimal(0))
        mean = zone_weight / Decimal(width_bins)
        if q25 <= mean <= q75:
            result.append(
                ControlZone(
                    f"{profile.profile_id}-C01-{start}-{end}",
                    "C01",
                    start,
                    end,
                    window[0].bin_low,
                    window[-1].bin_high,
                    width_bins,
                    mean,
                    zone_weight,
                    zone_weight / total,
                    None,
                )
            )
    return tuple(result)


def mass_matched_controls(
    profile: FrozenProfile,
    nodes: tuple[HvnNode, ...],
    candidates: tuple[PeakCandidate, ...],
    *,
    treated: HvnNode,
    width_bins: int,
    caliper: Decimal = Decimal("0.20"),
) -> tuple[ControlZone, ...]:
    total = sum((bin_.profile_weight for bin_ in profile.bins), Decimal(0))
    prominent_bins = {
        candidate.representative_bin_index for candidate in candidates if candidate.qualifies
    }
    result = []
    for start, end, window in _candidate_windows(profile, nodes, width_bins):
        if any(start <= index <= end for index in prominent_bins):
            continue
        zone_weight = sum((bin_.profile_weight for bin_ in window), Decimal(0))
        share = zone_weight / total
        difference = abs(share - treated.node_weight_share) / treated.node_weight_share
        if difference <= caliper:
            result.append(
                ControlZone(
                    f"{profile.profile_id}-C02-{start}-{end}",
                    "C02",
                    start,
                    end,
                    window[0].bin_low,
                    window[-1].bin_high,
                    width_bins,
                    zone_weight / Decimal(width_bins),
                    zone_weight,
                    share,
                    difference,
                )
            )
    return tuple(
        sorted(
            result,
            key=lambda zone: (
                zone.mass_proportional_difference,
                abs(zone.zone_weight_share - treated.node_weight_share),
                zone.start_bin_index,
                zone.control_zone_id,
            ),
        )
    )
