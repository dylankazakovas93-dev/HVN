"""Directional impulse features for HVN zone interactions.

Three quantities, all computed from completed bars only:

```text
DirectionalDisplacement_d = sum(max(0, d * (C_t - C_t-1))) / ATR
DirectionalVolume_d       = sum(V_t * 1[d * (C_t - C_t-1) > 0]) / seasonal expected volume
Efficiency_d              = |C_now - C_start| / sum(|C_t - C_t-1|)
```

OHLCV cannot separate buyer-initiated from seller-initiated volume. The
displacement and efficiency terms exist precisely to compensate: a bar's volume
is attributed to the side its close moved, and efficiency then separates "price
travelled on a few large directional bars" from "price was noisy and happened to
finish higher". The three together are the closest clean approximation to
following participation that this data supports.

Volume is normalized by a seasonal baseline built from trailing prior sessions,
not from the last few bars. NQ volume at 09:30 and 15:00 is naturally enormous;
against a local baseline those clock times would be flagged abnormal every day.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from .models import Bar

NY = ZoneInfo("America/New_York")

UP = 1
DOWN = -1

# Frozen impulse parameters.
IMPULSE_LOOKBACK_BARS = 15
SEASONAL_TRAILING_SESSIONS = 20
FORWARD_HORIZONS_BARS = (15, 30, 60)

# Predeclared broad buckets. Amendment 04; never optimized.
RELATIVE_VOLUME_BUCKETS = (
    ("below_normal", None, Decimal("0.80")),
    ("normal", Decimal("0.80"), Decimal("1.25")),
    ("elevated", Decimal("1.25"), Decimal("2.00")),
    ("extreme", Decimal("2.00"), None),
)
DISPLACEMENT_BUCKETS = (
    ("lt_0.5", None, Decimal("0.5")),
    ("0.5_1.0", Decimal("0.5"), Decimal("1.0")),
    ("1.0_1.5", Decimal("1.0"), Decimal("1.5")),
    ("gt_1.5", Decimal("1.5"), None),
)
EFFICIENCY_BUCKETS = (
    ("low", None, Decimal("0.30")),
    ("medium", Decimal("0.30"), Decimal("0.60")),
    ("high", Decimal("0.60"), None),
)
DWELL_BUCKETS = (
    ("0-2", 0, 2),
    ("3-6", 3, 6),
    ("7-12", 7, 12),
    ("13+", 13, 10**9),
)


def bucket_of(value, buckets, *, undefined: str = "undefined") -> str:
    """First bucket whose half-open [low, high) range contains `value`."""
    if value is None:
        return undefined
    for label, low, high in buckets:
        if (low is None or value >= low) and (high is None or value < high):
            return label
    return undefined


def dwell_bucket(bars: int | None) -> str:
    if bars is None:
        return "undefined"
    for label, low, high in DWELL_BUCKETS:
        if low <= bars <= high:
            return label
    return "undefined"


# ---------------------------------------------------------------------------
# Seasonal volume baseline


class SeasonalVolume:
    """Expected volume per minute-of-day, from trailing prior sessions only.

    For a bar at 09:31 on session S, the baseline is the median volume observed
    at 09:31 across the most recent `trailing` sessions strictly before S. No
    bar from S itself, and no later session, contributes to its own baseline.

    A minute with fewer than three prior observations has no baseline; its
    relative volume is undefined rather than being compared against one or two
    samples.
    """

    MIN_OBSERVATIONS = 3

    def __init__(self, bars, *, trailing: int = SEASONAL_TRAILING_SESSIONS) -> None:
        self.trailing = trailing
        # minute-of-day -> ordered list of (session date, volume)
        self._by_minute: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
        for bar in sorted(bars, key=lambda b: b.close_time):
            local = bar.start_time.astimezone(NY)
            minute = local.hour * 60 + local.minute
            self._by_minute[minute].append((local.date(), bar.volume))
        self._sessions: dict[int, list[date]] = {
            minute: [day for day, _ in rows] for minute, rows in self._by_minute.items()
        }

    def expected(self, moment: datetime) -> Decimal | None:
        """Median volume at this minute-of-day over the trailing prior sessions."""
        local = moment.astimezone(NY)
        minute = local.hour * 60 + local.minute
        rows = self._by_minute.get(minute)
        if not rows:
            return None
        days = self._sessions[minute]
        cutoff = bisect_left(days, local.date())
        window = [volume for _, volume in rows[max(0, cutoff - self.trailing) : cutoff]]
        if len(window) < self.MIN_OBSERVATIONS:
            return None
        ordered = sorted(window)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) / 2


# ---------------------------------------------------------------------------
# Impulse


@dataclass(frozen=True, slots=True)
class Impulse:
    """One direction's participation over a window of completed bars."""

    direction: int
    bars: int
    evaluated: bool
    directional_displacement_atr: Decimal | None
    directional_volume_ratio: Decimal | None
    efficiency: Decimal | None
    net_close_change_atr: Decimal | None
    seasonal_baseline_available: bool

    @property
    def displacement_bucket(self) -> str:
        return bucket_of(self.directional_displacement_atr, DISPLACEMENT_BUCKETS)

    @property
    def volume_bucket(self) -> str:
        return bucket_of(self.directional_volume_ratio, RELATIVE_VOLUME_BUCKETS)

    @property
    def efficiency_bucket(self) -> str:
        return bucket_of(self.efficiency, EFFICIENCY_BUCKETS)


def compute_impulse(
    window: list[Bar] | tuple[Bar, ...],
    *,
    direction: int,
    atr: Decimal,
    seasonal: SeasonalVolume | None = None,
) -> Impulse:
    """The three impulse quantities over `window`, in `direction`.

    `window` must be completed bars in time order. Close-to-close changes are
    taken within the window, so a window of n bars contributes n-1 changes and
    at least two bars are required.
    """
    if len(window) < 2 or atr <= 0:
        return Impulse(direction, len(window), False, None, None, None, None, False)

    directional_move = Decimal(0)
    directional_volume = Decimal(0)
    expected_volume = Decimal(0)
    total_absolute_move = Decimal(0)
    # With no baseline supplied there is nothing to be available; reporting True
    # here would claim a seasonal comparison that was never made.
    baseline_available = seasonal is not None

    for previous, current in zip(window, window[1:]):
        change = current.close - previous.close
        total_absolute_move += abs(change)
        if Decimal(direction) * change > 0:
            directional_move += abs(change)
            directional_volume += current.volume
        if seasonal is not None:
            expected = seasonal.expected(current.start_time)
            if expected is None:
                baseline_available = False
            else:
                expected_volume += expected

    displacement = directional_move / atr
    net = (window[-1].close - window[0].close) / atr
    efficiency = (
        abs(window[-1].close - window[0].close) / total_absolute_move
        if total_absolute_move > 0
        else Decimal(0)
    )
    volume_ratio = (
        directional_volume / expected_volume
        if seasonal is not None and baseline_available and expected_volume > 0
        else None
    )
    return Impulse(
        direction=direction,
        bars=len(window),
        evaluated=True,
        directional_displacement_atr=displacement,
        directional_volume_ratio=volume_ratio,
        efficiency=efficiency,
        net_close_change_atr=net,
        seasonal_baseline_available=baseline_available,
    )


def dominant_direction(window: list[Bar] | tuple[Bar, ...]) -> int:
    """The side carrying the larger summed close-to-close movement.

    An exact tie resolves DOWN, deterministically, matching the displacement
    engine's convention elsewhere in the project.
    """
    up = Decimal(0)
    down = Decimal(0)
    for previous, current in zip(window, window[1:]):
        change = current.close - previous.close
        if change > 0:
            up += change
        elif change < 0:
            down += -change
    return UP if up > down else DOWN


@dataclass(frozen=True, slots=True)
class ForwardOutcome:
    horizon_bars: int
    evaluated: bool
    continued: bool | None
    reverted: bool | None
    signed_move_atr: Decimal | None


def forward_outcome(
    forward: list[Bar] | tuple[Bar, ...],
    *,
    direction: int,
    reference_close: Decimal,
    atr: Decimal,
    horizon_bars: int,
) -> ForwardOutcome:
    """Did price keep going in `direction` `horizon_bars` after the impulse?

    Continuation and reversion are complementary and both reported, so a table
    can never be read as though "not continued" were missing data. An event with
    too few forward bars is not evaluated rather than being scored short.
    """
    if len(forward) < horizon_bars or atr <= 0:
        return ForwardOutcome(horizon_bars, False, None, None, None)
    move = (forward[horizon_bars - 1].close - reference_close) / atr
    signed = move * Decimal(direction)
    return ForwardOutcome(
        horizon_bars=horizon_bars,
        evaluated=True,
        continued=signed > 0,
        reverted=signed < 0,
        signed_move_atr=signed,
    )
