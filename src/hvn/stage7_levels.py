"""Every level at one anchor, from one-second data, at one strictness tier.

The Stage 6 assembly took one-minute bars and built eight of its nine sources
from them. This takes half-hour histograms and builds **all nine** from them:
the composite, the single-hour profile, the two developing profiles, the prior
RTH profile, and the four anchored VWAPs with their sigma and percentage bands.

Nothing else changes. The sources are the same nine, the kinds are the same, and
the causality claim is carried in the same `LevelSet` so the runner can assert
at every anchor that no bucket later than the anchor contributed. That assertion
is not decoration: nine sources is nine chances to leak the future, and a leak
would not crash, it would produce an excellent result.

Windows land exactly on the half-hour grid, which is why the cache is bucketed
at thirty minutes rather than an hour — 09:30 is a real boundary here.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from .bucket_histogram import NANOS_PER_BUCKET, BucketStore, bucket_start
from .confluence import Level, LevelSet
from .profile_sources import (
    P2_SINGLE_HOUR,
    P3_GLOBEX_DEVELOPING,
    P4_CASH_DEVELOPING,
    P5_PRIOR_RTH,
    poc_index,
    value_area_pct,
    value_area_sigma,
)
from .rolling_profile import LOW_NODE, detect_nodes, rolling_activity
from .stage4_levels import (
    BAND_HALF_WIDTH_ATR,
    HIGH_NODE_KIND,
    LOW_NODE_INSIDE,
    LOW_NODE_OUTSIDE,
    P1_ROLLING,
    POC_KIND,
    SIGMA_EDGE,
    TPO_EXTREME,
    VALUE_EDGE,
    VWAP_BAND,
)
from .tiers import Tier
from .vwap_sources import (
    P6_VWAP_GLOBEX,
    P7_VWAP_CASH,
    P8_VWAP_PRIOR_RTH,
    P9_VWAP_ROLLING,
)

NY = ZoneInfo("America/New_York")
ROLLING_SESSIONS = 20
CASH_OPEN = time(9, 30)
CASH_CLOSE = time(16, 0)
GLOBEX_OPEN = time(18, 0)

PROFILE_SOURCES = (P1_ROLLING, P2_SINGLE_HOUR, P3_GLOBEX_DEVELOPING,
                   P4_CASH_DEVELOPING, P5_PRIOR_RTH)
VWAP_SOURCES = (P6_VWAP_GLOBEX, P7_VWAP_CASH, P8_VWAP_PRIOR_RTH, P9_VWAP_ROLLING)


def bucket_index(moment: datetime) -> int:
    return int(moment.timestamp() * 1_000_000_000) // NANOS_PER_BUCKET


def _at(session: str, clock: time, *, days_back: int = 0) -> datetime:
    """A wall-clock time on a session's date, in New York, as an instant."""
    day = datetime.fromisoformat(session).date() - timedelta(days=days_back)
    return datetime.combine(day, clock, tzinfo=NY)


def seconds_extremes(
    profile, *, share: Decimal, atr: Decimal | None = None
) -> list[tuple[Decimal, Decimal]]:
    """Contiguous price runs whose time-at-price sits in the bottom `share`.

    The old T1/T2 thresholds were absolute bar counts, which meant something
    definite for thirty-minute TPO letters and nothing at all for a window of
    one-second bars — a nine-hour window has 32,400 of them. A share of the
    traded ticks is the same idea stated in a way that survives the resolution
    change, and it is what the tier axis varies.

    The share is a **count cap**, not a value cut. Taking every tick at or below
    the share-quantile *value* does not control the count at all: seconds-at-
    price is heavily tied at the thin end, so one tie at the cut admits hundreds
    of ticks and the strict tier emitted as many levels as the loose one. The
    lowest `share` of ticks by count, ties broken by price, is what the axis was
    supposed to mean.

    Runs narrower than the node minimum are dropped, matching `detect_nodes`. A
    two-tick gap is not a level in one detector and an artifact in the other.
    """
    traded = [i for i in profile.indices if profile.tpo.get(i, 0) > 0]
    if not traded:
        return []
    keep = max(1, int(len(traded) * float(share)))
    chosen = sorted(sorted(traded, key=lambda i: (profile.tpo[i], i))[:keep])
    minimum = 3
    if atr is not None:
        from .session_histogram import TICK_SIZE

        minimum = max(
            3,
            int(
                (Decimal("0.40") * atr / TICK_SIZE).to_integral_value(
                    rounding="ROUND_CEILING"
                )
            ),
        )
    runs: list[list[int]] = []
    for index in chosen:
        if runs and index == runs[-1][-1] + 1:
            runs[-1].append(index)
        else:
            runs.append([index])
    return [
        (profile.tick_low(r[0]), profile.tick_high(r[-1]))
        for r in runs
        if len(r) >= minimum
    ]


def profile_levels(profile, source: str, *, atr: Decimal, spec: Tier) -> list[Level]:
    """Nodes, value edges, sigma edges, POC and time-at-price runs from one profile."""
    out: list[Level] = []
    activity = rolling_activity(profile)
    value = value_area_pct(profile)

    if activity.valid:
        nodes = detect_nodes(
            profile,
            activity,
            high_percentile=spec.high_node_percentile,
            high_min_activity=spec.high_node_min_activity,
            low_percentile=spec.low_node_percentile,
            low_max_activity=spec.low_node_max_activity,
        )
        for node in nodes:
            if node.node_class == LOW_NODE:
                inside = value is not None and value[0] <= node.peak_price < value[1]
                kind = LOW_NODE_INSIDE if inside else LOW_NODE_OUTSIDE
            else:
                kind = HIGH_NODE_KIND
            out.append(
                Level(source, kind, node.node_low, node.node_high,
                      detail=f"pct={node.activity_percentile}")
            )

    if spec.include_value_edges and value is not None:
        for edge, label in ((value[0], "VAL"), (value[1], "VAH")):
            out.append(
                Level(source, VALUE_EDGE, edge - BAND_HALF_WIDTH_ATR * atr,
                      edge + BAND_HALF_WIDTH_ATR * atr, detail=label)
            )

    for multiple in spec.sigma_multiples:
        band = value_area_sigma(profile, multiple)
        if band is None:
            continue
        for edge, side in ((band[0], "-"), (band[1], "+")):
            out.append(
                Level(source, SIGMA_EDGE, edge - BAND_HALF_WIDTH_ATR * atr,
                      edge + BAND_HALF_WIDTH_ATR * atr, detail=f"{side}{multiple}s")
            )

    if spec.include_poc:
        centre = poc_index(profile)
        if centre is not None:
            out.append(
                Level(source, POC_KIND, profile.tick_low(centre),
                      profile.tick_high(centre), detail="POC")
            )

    for low, high in seconds_extremes(
        profile, share=spec.seconds_bottom_share, atr=atr
    ):
        out.append(
            Level(source, TPO_EXTREME, low, high,
                  detail=f"share={spec.seconds_bottom_share}")
        )
    return out


def vwap_levels(mean: Decimal, dispersion: Decimal, source: str, *,
                atr: Decimal, spec: Tier) -> list[Level]:
    out: list[Level] = []
    prices: list[tuple[str, Decimal]] = []
    for multiple in spec.vwap_sigma_multiples:
        offset = multiple * dispersion
        prices.append((f"SIGMA:+{multiple}s", mean + offset))
        prices.append((f"SIGMA:-{multiple}s", mean - offset))
    for fraction in spec.vwap_percent_offsets:
        offset = mean * fraction
        label = f"{fraction * 100:.2f}%"
        prices.append((f"PERCENT:+{label}", mean + offset))
        prices.append((f"PERCENT:-{label}", mean - offset))
    for label, price in prices:
        out.append(
            Level(source, VWAP_BAND, price - BAND_HALF_WIDTH_ATR * atr,
                  price + BAND_HALF_WIDTH_ATR * atr, detail=label)
        )
    return out


def source_windows(store: BucketStore, session: str, anchor: datetime) -> dict[str, list[int]]:
    """The bucket range feeding each of the nine sources, all strictly before the anchor.

    Every window ends at `anchor` exclusive. A bucket labelled 14:00 covers
    14:00-14:30, so a bucket is admissible only when its *close* is at or before
    the anchor — which is exactly `bucket < bucket_index(anchor)`.
    """
    end = bucket_index(anchor)
    trailing = store.trailing(session, ROLLING_SESSIONS)
    composite = [b for name in trailing for b in store.buckets(name) if b < end]

    globex_open = bucket_index(_at(session, GLOBEX_OPEN, days_back=1))
    cash_open = bucket_index(_at(session, CASH_OPEN))

    previous = store.trailing(session, 2)
    prior_session = previous[0] if len(previous) == 2 else None
    if prior_session is None:
        prior = []
    else:
        prior = store.range(
            bucket_index(_at(prior_session, CASH_OPEN)),
            min(bucket_index(_at(prior_session, CASH_CLOSE)), end),
        )

    return {
        P1_ROLLING: composite,
        P2_SINGLE_HOUR: store.range(max(globex_open, end - 2), end),
        P3_GLOBEX_DEVELOPING: store.range(globex_open, end),
        P4_CASH_DEVELOPING: store.range(cash_open, end) if end > cash_open else [],
        P5_PRIOR_RTH: prior,
        P6_VWAP_GLOBEX: store.range(globex_open, end),
        P7_VWAP_CASH: store.range(cash_open, end) if end > cash_open else [],
        P8_VWAP_PRIOR_RTH: prior,
        P9_VWAP_ROLLING: composite,
    }


def build_level_set(
    store: BucketStore, session: str, anchor: datetime, *, atr: Decimal, spec: Tier
) -> LevelSet:
    """Assemble every source's levels at one anchor, from buckets only.

    A source with no window yet casts no vote. Before the cash open there is no
    cash profile and no cash VWAP; on the first session of a partition there is
    no prior RTH. Those are real states, not errors.
    """
    windows = source_windows(store, session, anchor)
    levels: list[Level] = []
    latest: datetime | None = None

    def note(buckets):
        nonlocal latest
        for bucket in buckets:
            close = bucket_start(bucket) + timedelta(seconds=NANOS_PER_BUCKET // 1_000_000_000)
            if latest is None or close > latest:
                latest = close

    for source in PROFILE_SOURCES:
        buckets = windows[source]
        if not buckets:
            continue
        note(buckets)
        profile = store.profile(buckets, atr=atr, anchor=anchor)
        if profile is None:
            continue
        levels += profile_levels(profile, source, atr=atr, spec=spec)

    for source in VWAP_SOURCES:
        buckets = windows[source]
        if not buckets:
            continue
        note(buckets)
        moments = store.moments(buckets)
        if moments is None:
            continue
        mean, dispersion, _ = moments
        levels += vwap_levels(mean, dispersion, source, atr=atr, spec=spec)

    return LevelSet(anchor_time=anchor, levels=tuple(levels), latest_bar_close=latest)


__all__ = [
    "PROFILE_SOURCES",
    "VWAP_SOURCES",
    "build_level_set",
    "bucket_index",
    "seconds_extremes",
    "source_windows",
]
