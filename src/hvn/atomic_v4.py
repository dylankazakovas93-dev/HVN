"""Final Generation 3 atomic-node detector — Amendment 03.

Adds two gates to the Amendment 02 composite floors: global significance
(`peak_activity_percentile >= 90.0` within the node's own completed profile)
and mild local distinctness (`local_activity_prominence >= 1.10`). Everything
else — the profile model, candidate geometry, the four density floors, POC
rules and both value areas — is unchanged.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from .atomic_v2 import MAX_ATOMIC_WIDTH_BINS, POC_ATOMIC, POC_BROAD, poc_plateau, profile_normalization
from .atomic_v3 import (
    COMPOSITE_ACTIVITY_TOO_LOW,
    MIN_PEAK_VOLUME_DENSITY,
    MIN_POC_VOLUME_DENSITY,
    MIN_ZONE_ACTIVITY_DENSITY,
    MIN_ZONE_TPO_DENSITY,
    MIN_ZONE_VOLUME_DENSITY,
    OVERLAPS_VOLUME_POC,
    PEAK_VOLUME_DENSITY_TOO_LOW,
    WIDTH_TOO_LARGE,
    ZONE_TPO_DENSITY_TOO_LOW,
    ZONE_VOLUME_DENSITY_TOO_LOW,
    CompositeNode,
    _prominence_from,
    classify_composite_nodes,
    density_ratios,
)
from .models import FrozenProfile

# Frozen Amendment 03 gates. Final; never tuned.
MIN_PEAK_ACTIVITY_PERCENTILE = Decimal("90.0")
MIN_LOCAL_ACTIVITY_PROMINENCE = Decimal("1.10")

ACTIVITY_PERCENTILE_TOO_LOW = "ACTIVITY_PERCENTILE_TOO_LOW"
LOCAL_ACTIVITY_PROMINENCE_TOO_LOW = "LOCAL_ACTIVITY_PROMINENCE_TOO_LOW"

# Frozen first-failure ordering.
REJECTION_ORDER = (
    "INVALID_PROFILE_TOTAL",
    "INVALID_TPO_TOTAL",
    "INVALID_ACTIVE_BIN_COUNT",
    WIDTH_TOO_LARGE,
    OVERLAPS_VOLUME_POC,
    ZONE_VOLUME_DENSITY_TOO_LOW,
    PEAK_VOLUME_DENSITY_TOO_LOW,
    ZONE_TPO_DENSITY_TOO_LOW,
    COMPOSITE_ACTIVITY_TOO_LOW,
    ACTIVITY_PERCENTILE_TOO_LOW,
    LOCAL_ACTIVITY_PROMINENCE_TOO_LOW,
)


def activity_percentile_100(values: dict) -> dict:
    """Percentile on a 0-100 scale over active bins, ties sharing the lowest.

    percentile = 100 * |{active bins strictly below x}| / |{active bins}|

    Exact Decimal arithmetic over integer counts, so the result is identical on
    any platform and uses no future data.
    """
    active = sorted(v for v in values.values() if v > 0)
    if not active:
        return {}
    total = Decimal(len(active))
    ranks: dict[Decimal, Decimal] = {}
    for index, value in enumerate(active):
        if value not in ranks:
            ranks[value] = Decimal(100) * Decimal(index) / total
    return {k: ranks[v] for k, v in values.items() if v > 0}


def classify_final_nodes(
    profile: FrozenProfile, tpo_by_index: dict
) -> tuple[tuple[CompositeNode, ...], object]:
    """Amendment 02 classification, then the two Amendment 03 gates.

    POC nodes bypass both new gates: the POC is already the profile's maximum
    allocated-volume location. Non-POC nodes that failed an earlier Amendment 02
    condition keep that earlier reason, preserving the frozen ordering.
    """
    nodes, norm = classify_composite_nodes(profile, tpo_by_index)
    if not norm.valid:
        return nodes, norm

    _, _, activity = density_ratios(profile, tpo_by_index, norm)
    percentiles = activity_percentile_100(activity)
    bins_by_index = {b.bin_index: b for b in profile.bins}

    out = []
    for node in nodes:
        if node.node_class in (POC_ATOMIC, POC_BROAD) or not node.accepted:
            # POC bypasses the new gates; an already-rejected node keeps its
            # earlier, higher-priority reason.
            out.append(
                replace(
                    node,
                    activity_percentile=percentiles.get(
                        node.peak_bin_index, Decimal(0)
                    ),
                )
            )
            continue

        run = [
            bins_by_index[i]
            for i in range(node.start_bin_index, node.end_bin_index + 1)
            if i in bins_by_index
        ]
        percentile = percentiles.get(node.peak_bin_index, Decimal(0))
        prominence = _prominence_from(profile, run, activity)

        reason = ""
        if percentile < MIN_PEAK_ACTIVITY_PERCENTILE:
            reason = ACTIVITY_PERCENTILE_TOO_LOW
        elif prominence is None or prominence < MIN_LOCAL_ACTIVITY_PROMINENCE:
            reason = LOCAL_ACTIVITY_PROMINENCE_TOO_LOW

        out.append(
            replace(
                node,
                activity_percentile=percentile,
                local_activity_prominence=prominence,
                accepted=reason == "",
                rejection_reason=reason,
            )
        )
    return tuple(out), norm
