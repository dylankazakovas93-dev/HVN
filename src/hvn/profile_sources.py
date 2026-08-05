"""Stage 4 profile sources: the same tick grid, anchored five different ways.

Stage 3 asked one profile where volume sat. This asks several, because the
confluence question is whether *independent* constructions agree on a price, and
two views of the same window are not independent.

    P1  rolling composite    trailing 20 sessions, re-anchored hourly
    P2  single hour          one completed hour, standalone
    P3  globex developing    18:00 ET to the anchor
    P4  cash developing      09:30 ET to the anchor
    P5  prior RTH            the previous session's full 09:30-16:00

P1 is `rolling_profile.build_rolling_profile`, carried over untouched. This
module adds P2-P5 and the level extractors that run on any of them.

Every window is causal by construction: a window selector never returns a bar
that closed after the anchor, and the prior-RTH selector reaches back to a
session that had already ended when the anchor was stamped.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from .engine import TICK_SIZE, intersected_bin_indices
from .models import Bar
from .rolling_profile import NY, RollingProfile, session_date

P2_SINGLE_HOUR = "P2_SINGLE_HOUR"
P3_GLOBEX_DEVELOPING = "P3_GLOBEX_DEVELOPING"
P4_CASH_DEVELOPING = "P4_CASH_DEVELOPING"
P5_PRIOR_RTH = "P5_PRIOR_RTH"

GLOBEX_OPEN = time(18, 0)
CASH_OPEN = time(9, 30)
CASH_CLOSE = time(16, 0)

# Value area, both definitions. Predeclared; never searched.
VALUE_AREA_FRACTION = Decimal("0.70")
SIGMA_MULTIPLES = (Decimal(1), Decimal(2), Decimal(3), Decimal(4))

# TPO extreme thresholds T1-T3.
TPO_SINGLE_PRINT = 1
TPO_AT_MOST_TWO = 2
TPO_BOTTOM_DECILE = Decimal("10.0")


def _local(moment: datetime):
    return moment.astimezone(NY)


def single_hour_window(bars, anchor: datetime) -> list[Bar]:
    """The completed hour ending at the anchor."""
    start = anchor - timedelta(hours=1)
    return [b for b in bars if start < b.close_time <= anchor]


def globex_developing_window(bars, anchor: datetime) -> list[Bar]:
    """From the 18:00 ET open of the anchor's session to the anchor."""
    session = session_date(anchor)
    return [
        b
        for b in bars
        if b.close_time <= anchor and session_date(b.close_time) == session
    ]


def cash_developing_window(bars, anchor: datetime) -> list[Bar]:
    """From 09:30 ET to the anchor, within the anchor's session.

    Empty before the cash open, which is a real state and not an error: at
    03:00 there is no cash profile yet, so this source casts no vote.
    """
    session = session_date(anchor)
    return [
        b
        for b in bars
        if b.close_time <= anchor
        and session_date(b.close_time) == session
        and _local(b.close_time).time() > CASH_OPEN
    ]


def prior_rth_window(bars, anchor: datetime) -> list[Bar]:
    """The previous session's full cash hours, complete before the anchor."""
    session = session_date(anchor)
    earlier = sorted(
        {
            s
            for s in (session_date(b.close_time) for b in bars if b.close_time < anchor)
            if s < session
        }
    )
    if not earlier:
        return []
    previous = earlier[-1]
    return [
        b
        for b in bars
        if session_date(b.close_time) == previous
        and CASH_OPEN < _local(b.close_time).time() <= CASH_CLOSE
        and b.close_time < anchor
    ]


WINDOWS = {
    P2_SINGLE_HOUR: single_hour_window,
    P3_GLOBEX_DEVELOPING: globex_developing_window,
    P4_CASH_DEVELOPING: cash_developing_window,
    P5_PRIOR_RTH: prior_rth_window,
}


def profile_from_window(
    window: list[Bar], anchor: datetime, *, atr: Decimal, label: str
) -> RollingProfile | None:
    """Tick-grid volume and TPO over an arbitrary bar window.

    Allocation is uniform across the bar's intersected ticks, identical to the
    Stage 3 construction, so profiles from different anchors stay comparable.
    """
    if len(window) < 2:
        return None
    volume: dict[int, Decimal] = {}
    tpo: dict[int, int] = {}
    for bar in window:
        indices = intersected_bin_indices(bar.low, bar.high, TICK_SIZE)
        share = bar.volume / Decimal(len(indices))
        for index in indices:
            volume[index] = volume.get(index, Decimal(0)) + share
            tpo[index] = tpo.get(index, 0) + 1
    low_index, high_index = min(volume), max(volume)
    for index in range(low_index, high_index + 1):
        volume.setdefault(index, Decimal(0))
        tpo.setdefault(index, 0)
    return RollingProfile(
        anchor_time=anchor,
        sessions=(label,),
        low_index=low_index,
        high_index=high_index,
        volume=volume,
        tpo=tpo,
        bars_used=len(window),
        atr_value=atr,
    )


def build_source_profile(
    bars, anchor: datetime, *, atr: Decimal, source: str
) -> RollingProfile | None:
    """Profile for one of P2-P5, or None when that source has no window yet."""
    window = WINDOWS[source](bars, anchor)
    return profile_from_window(window, anchor, atr=atr, label=source)


# ---------------------------------------------------------------------------
# Value area, both definitions


def poc_index(profile: RollingProfile) -> int | None:
    """Highest-volume tick; ties break to the lower index for determinism."""
    best, best_index = Decimal(-1), None
    for index in profile.indices:
        value = profile.volume.get(index, Decimal(0))
        if value > best:
            best, best_index = value, index
    return best_index


def value_area_pct(
    profile: RollingProfile, fraction: Decimal = VALUE_AREA_FRACTION
) -> tuple[Decimal, Decimal] | None:
    """The `fraction` of volume nearest the POC, expanded a tick-pair at a time.

    The conventional construction: from the POC, compare the volume of the pair
    of ticks above against the pair below and absorb the heavier side, until the
    target share of total volume is inside.
    """
    total = sum(profile.volume.values(), Decimal(0))
    centre = poc_index(profile)
    if centre is None or total <= 0:
        return None
    target = total * fraction
    low = high = centre
    inside = profile.volume.get(centre, Decimal(0))
    while inside < target and (low > profile.low_index or high < profile.high_index):
        above = sum(
            (profile.volume.get(high + step, Decimal(0)) for step in (1, 2)),
            Decimal(0),
        )
        below = sum(
            (profile.volume.get(low - step, Decimal(0)) for step in (1, 2)),
            Decimal(0),
        )
        if high >= profile.high_index:
            above = Decimal(-1)
        if low <= profile.low_index:
            below = Decimal(-1)
        if above >= below:
            high = min(profile.high_index, high + 2)
            inside += max(above, Decimal(0))
        else:
            low = max(profile.low_index, low - 2)
            inside += max(below, Decimal(0))
    return profile.tick_low(low), profile.tick_high(high)


def volume_weighted_moments(profile: RollingProfile) -> tuple[Decimal, Decimal] | None:
    """Volume-weighted mean price and standard deviation over the profile."""
    total = sum(profile.volume.values(), Decimal(0))
    if total <= 0:
        return None
    mean = sum(
        (
            profile.volume.get(i, Decimal(0)) * (profile.tick_low(i) + TICK_SIZE / 2)
            for i in profile.indices
        ),
        Decimal(0),
    ) / total
    variance = sum(
        (
            profile.volume.get(i, Decimal(0))
            * (profile.tick_low(i) + TICK_SIZE / 2 - mean) ** 2
            for i in profile.indices
        ),
        Decimal(0),
    ) / total
    return mean, variance.sqrt()


def value_area_sigma(
    profile: RollingProfile, multiple: Decimal
) -> tuple[Decimal, Decimal] | None:
    """Bands at `multiple` volume-weighted standard deviations about the mean."""
    moments = volume_weighted_moments(profile)
    if moments is None:
        return None
    mean, sigma = moments
    return mean - multiple * sigma, mean + multiple * sigma


# ---------------------------------------------------------------------------
# TPO extremes: thin by time rather than by volume


def _runs(indices: list[int]) -> list[tuple[int, int]]:
    """Contiguous index runs, so adjacent thin ticks become one level."""
    out: list[tuple[int, int]] = []
    for index in sorted(indices):
        if out and index == out[-1][1] + 1:
            out[-1] = (out[-1][0], index)
        else:
            out.append((index, index))
    return out


def tpo_extremes(profile: RollingProfile, *, threshold: str) -> list[tuple[Decimal, Decimal]]:
    """Price intervals whose time-at-price is extreme, by one of T1-T3.

    T1 and T2 are absolute counts; T3 is the bottom decile of TPO among ticks
    that actually traded, which adapts to how long the window is. All three are
    reported, none is selected on result.
    """
    traded = [i for i in profile.indices if profile.tpo.get(i, 0) > 0]
    if not traded:
        return []
    if threshold == "T1":
        chosen = [i for i in traded if profile.tpo[i] <= TPO_SINGLE_PRINT]
    elif threshold == "T2":
        chosen = [i for i in traded if profile.tpo[i] <= TPO_AT_MOST_TWO]
    elif threshold == "T3":
        counts = sorted(profile.tpo[i] for i in traded)
        cut = counts[min(len(counts) - 1, int(len(counts) / 10))]
        chosen = [i for i in traded if profile.tpo[i] <= cut]
    else:
        raise ValueError(f"unknown TPO threshold {threshold!r}")
    return [
        (profile.tick_low(low), profile.tick_high(high)) for low, high in _runs(chosen)
    ]
