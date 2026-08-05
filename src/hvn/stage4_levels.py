"""Every level visible at one anchor, from all nine sources, with causality proved.

This is the assembly point. Each source contributes zero or more `Level`s, and
the set carries the latest bar close that fed any of them so the runner can
assert — at every anchor, not once at startup — that nothing later than the
anchor contributed. A leak would not crash; it would produce an excellent
result. So it is checked rather than trusted.

Sources that have no window yet simply cast no vote. Before the cash open there
is no cash profile and no cash VWAP, and on the first session of a partition
there is no prior RTH. Those are real states, not errors.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .confluence import Level, LevelSet
from .profile_sources import (
    P2_SINGLE_HOUR,
    P3_GLOBEX_DEVELOPING,
    P4_CASH_DEVELOPING,
    P5_PRIOR_RTH,
    SIGMA_MULTIPLES,
    WINDOWS,
    poc_index,
    profile_from_window,
    tpo_extremes,
    value_area_pct,
    value_area_sigma,
)
from .rolling_profile import (
    HIGH_NODE,
    LOW_NODE,
    detect_nodes,
    rolling_activity,
)
from .vwap_sources import (
    P6_VWAP_GLOBEX,
    P7_VWAP_CASH,
    P8_VWAP_PRIOR_RTH,
    P9_VWAP_ROLLING,
    PERCENT_BANDS,
    SIGMA_BANDS,
    VWAP_WINDOWS,
    anchored_vwap,
    band_levels,
)

P1_ROLLING = "P1_ROLLING"
PROFILE_SOURCES = (P1_ROLLING, P2_SINGLE_HOUR, P3_GLOBEX_DEVELOPING,
                   P4_CASH_DEVELOPING, P5_PRIOR_RTH)
VWAP_SOURCES = (P6_VWAP_GLOBEX, P7_VWAP_CASH, P8_VWAP_PRIOR_RTH, P9_VWAP_ROLLING)

TPO_THRESHOLDS = ("T1", "T2", "T3")

# Level kinds, so a cluster can be described by what agreed rather than only by
# how many sources did.
LOW_NODE_OUTSIDE = "LOW_NODE_OUTSIDE_VALUE"
LOW_NODE_INSIDE = "LOW_NODE_INSIDE_VALUE"
HIGH_NODE_KIND = "HIGH_NODE"
VALUE_EDGE = "VALUE_EDGE"
SIGMA_EDGE = "SIGMA_EDGE"
POC_KIND = "POC"
TPO_EXTREME = "TPO_EXTREME"
VWAP_BAND = "VWAP_BAND"

# A VWAP band is a line, not a region. It is given a nominal width so it can
# join the confluence test on the same footing as a node interval.
BAND_HALF_WIDTH_ATR = Decimal("0.25")


def _profile_levels(profile, source: str, atr: Decimal) -> list[Level]:
    """Nodes, value edges, sigma edges, POC and TPO extremes from one profile."""
    out: list[Level] = []
    activity = rolling_activity(profile)
    value = value_area_pct(profile)

    if activity.valid:
        for node in detect_nodes(profile, activity):
            if node.node_class == LOW_NODE:
                inside = (
                    value is not None
                    and value[0] <= node.peak_price < value[1]
                )
                kind = LOW_NODE_INSIDE if inside else LOW_NODE_OUTSIDE
            else:
                kind = HIGH_NODE_KIND
            out.append(
                Level(source, kind, node.node_low, node.node_high,
                      detail=f"pct={node.activity_percentile}")
            )

    if value is not None:
        for edge, label in ((value[0], "VAL"), (value[1], "VAH")):
            out.append(
                Level(source, VALUE_EDGE, edge - BAND_HALF_WIDTH_ATR * atr,
                      edge + BAND_HALF_WIDTH_ATR * atr, detail=label)
            )

    for multiple in SIGMA_MULTIPLES:
        band = value_area_sigma(profile, multiple)
        if band is None:
            continue
        for edge, side in ((band[0], "-"), (band[1], "+")):
            out.append(
                Level(source, SIGMA_EDGE, edge - BAND_HALF_WIDTH_ATR * atr,
                      edge + BAND_HALF_WIDTH_ATR * atr,
                      detail=f"{side}{multiple}s")
            )

    centre = poc_index(profile)
    if centre is not None:
        out.append(
            Level(source, POC_KIND, profile.tick_low(centre),
                  profile.tick_high(centre), detail="POC")
        )

    for threshold in TPO_THRESHOLDS:
        for low, high in tpo_extremes(profile, threshold=threshold):
            out.append(Level(source, TPO_EXTREME, low, high, detail=threshold))
    return out


def _vwap_levels(vwap, atr: Decimal) -> list[Level]:
    out: list[Level] = []
    for definition in (SIGMA_BANDS, PERCENT_BANDS):
        for label, price in band_levels(vwap, definition=definition).items():
            out.append(
                Level(
                    vwap.source,
                    VWAP_BAND,
                    price - BAND_HALF_WIDTH_ATR * atr,
                    price + BAND_HALF_WIDTH_ATR * atr,
                    detail=f"{definition}:{label}",
                )
            )
    return out


def build_level_set(
    bars, anchor: datetime, *, atr: Decimal, rolling_profile=None
) -> LevelSet:
    """Assemble every source's levels at one anchor.

    `rolling_profile` is passed in because the runner has already built it and
    it is the most expensive object in the loop; rebuilding it here would double
    the cost of the scan for nothing.
    """
    levels: list[Level] = []
    latest: datetime | None = None

    def note(window):
        nonlocal latest
        for bar in window:
            if latest is None or bar.close_time > latest:
                latest = bar.close_time

    if rolling_profile is not None:
        levels += _profile_levels(rolling_profile, P1_ROLLING, atr)
        latest = rolling_profile.anchor_time

    for source in (P2_SINGLE_HOUR, P3_GLOBEX_DEVELOPING, P4_CASH_DEVELOPING,
                   P5_PRIOR_RTH):
        window = WINDOWS[source](bars, anchor)
        note(window)
        profile = profile_from_window(window, anchor, atr=atr, label=source)
        if profile is None:
            continue
        levels += _profile_levels(profile, source, atr)

    for source in VWAP_SOURCES:
        window = VWAP_WINDOWS[source](bars, anchor)
        note(window)
        vwap = anchored_vwap(window, anchor, source=source)
        if vwap is None:
            continue
        levels += _vwap_levels(vwap, atr)

    return LevelSet(anchor_time=anchor, levels=tuple(levels), latest_bar_close=latest)


__all__ = [
    "HIGH_NODE",
    "PROFILE_SOURCES",
    "VWAP_SOURCES",
    "build_level_set",
]
