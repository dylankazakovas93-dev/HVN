from __future__ import annotations

from decimal import Decimal
from statistics import median

from .models import FrozenProfile, HvnNode, PeakCandidate


def _representative(profile: FrozenProfile, indices: list[int]) -> int:
    by_index = {b.bin_index: b for b in profile.bins}
    total = sum((b.profile_weight for b in profile.bins), Decimal(0))
    mean = sum(
        (b.bin_center * b.profile_weight for b in profile.bins), Decimal(0)
    ) / total
    range_mid = (profile.bins[0].bin_low + profile.bins[-1].bin_high) / Decimal(2)
    return min(
        indices,
        key=lambda i: (
            abs(by_index[i].bin_center - mean),
            abs(by_index[i].bin_center - range_mid),
            by_index[i].bin_center,
        ),
    )


def peak_candidates(
    profile: FrozenProfile,
    prominence_threshold: Decimal,
    *,
    minimum_baseline_bins: int = 2,
) -> tuple[PeakCandidate, ...]:
    bins = profile.bins
    out: list[PeakCandidate] = []
    i = 0
    while i < len(bins):
        j = i
        while j + 1 < len(bins) and bins[j + 1].profile_weight == bins[i].profile_weight:
            j += 1
        left = bins[i - 1].profile_weight if i else Decimal("-Infinity")
        right = bins[j + 1].profile_weight if j + 1 < len(bins) else Decimal("-Infinity")
        is_peak = bins[i].profile_weight > left and bins[j].profile_weight > right
        if is_peak:
            plateau_indices = [b.bin_index for b in bins[i : j + 1]]
            rep = _representative(profile, plateau_indices)
            rep_bin = next(b for b in bins if b.bin_index == rep)
            radius = profile.atr_value * Decimal("0.50")
            baseline_bins = [
                b
                for b in bins
                if b.bin_index not in plateau_indices
                and abs(b.bin_center - rep_bin.bin_center) <= radius
            ]
            baseline: Decimal | None = None
            prominence: Decimal | None = None
            qualifies = False
            reason = ""
            if len(baseline_bins) < minimum_baseline_bins:
                reason = "insufficient_local_baseline_bins"
            else:
                baseline = median([b.profile_weight for b in baseline_bins])
                if baseline == 0:
                    prominence = Decimal("Infinity") if rep_bin.profile_weight > 0 else None
                    qualifies = rep_bin.profile_weight > 0
                    reason = "zero_baseline_positive_peak" if qualifies else "zero_peak"
                else:
                    prominence = rep_bin.profile_weight / baseline
                    qualifies = prominence >= prominence_threshold
                    reason = "" if qualifies else "below_prominence_threshold"
            out.append(
                PeakCandidate(
                    f"{profile.profile_id}-P{len(out)+1:03d}",
                    bins[i].bin_index,
                    bins[j].bin_index,
                    rep,
                    rep_bin.bin_center,
                    rep_bin.profile_weight,
                    baseline,
                    prominence,
                    tuple(b.bin_index for b in baseline_bins),
                    qualifies,
                    reason,
                )
            )
        i = j + 1
    return tuple(out)


def extract_hvns(
    profile: FrozenProfile, prominence_threshold: Decimal
) -> tuple[tuple[PeakCandidate, ...], tuple[HvnNode, ...]]:
    candidates = peak_candidates(profile, prominence_threshold)
    by_index = {b.bin_index: b for b in profile.bins}
    qualifying = [c for c in candidates if c.qualifies]
    raw: list[dict] = []
    for candidate in qualifying:
        threshold = candidate.peak_weight * Decimal("0.50")
        left, right = candidate.start_bin_index, candidate.end_bin_index
        while left - 1 in by_index and by_index[left - 1].profile_weight >= threshold:
            left -= 1
        while right + 1 in by_index and by_index[right + 1].profile_weight >= threshold:
            right += 1
        raw.append({"left": left, "right": right, "candidates": [candidate]})
    raw.sort(key=lambda item: item["left"])
    merged: list[dict] = []
    for node in raw:
        if merged and by_index[node["left"]].bin_low <= by_index[merged[-1]["right"]].bin_high:
            merged[-1]["right"] = max(merged[-1]["right"], node["right"])
            merged[-1]["candidates"].extend(node["candidates"])
        else:
            merged.append(node)
    total_profile_weight = sum((b.profile_weight for b in profile.bins), Decimal(0))
    nodes: list[HvnNode] = []
    for ordinal, item in enumerate(merged, 1):
        node_bins = [by_index[i] for i in range(item["left"], item["right"] + 1)]
        node_weight = sum((b.profile_weight for b in node_bins), Decimal(0))
        candidates_here = item["candidates"]
        representative = min(
            candidates_here,
            key=lambda c: (
                -c.peak_weight,
                -(node_weight / total_profile_weight),
                -(c.prominence_ratio or Decimal("-Infinity")),
                abs(c.peak_price - by_index[profile.poc_bin_index].bin_center),
                c.peak_price,
            ),
        )
        low, high = node_bins[0].bin_low, node_bins[-1].bin_high
        nodes.append(
            HvnNode(
                f"{profile.profile_id}-H{ordinal:03d}",
                low,
                high,
                (low + high) / Decimal(2),
                high - low,
                representative.peak_price,
                representative.peak_weight,
                representative.local_baseline,
                representative.prominence_ratio,
                node_weight,
                node_weight / total_profile_weight,
                len(node_bins),
                tuple(c.candidate_id for c in candidates_here),
                representative.candidate_id,
            )
        )
    return candidates, tuple(nodes)
