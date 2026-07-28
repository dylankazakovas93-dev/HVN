"""Generation 4 forward outcome measurement.

Implements `STAGE_02_GENERATION_4_OUTCOME_SPEC.md` as amended by
`STAGE_02_GENERATION_4_AMENDMENT_02.md`.

Every measurement here is causal: an event is known only at the close of the
touch bar, and all forward measurement begins with the next completed bar. The
touch bar never contributes to a post-touch quantity.

Distances are measured from the nearest zone edge in units of the one-minute ATR
at touch time. These are displacement and residence descriptions, not trading
quantities: nothing here is an entry, stop, target, profit or loss.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from .models import Bar

NY = ZoneInfo("America/New_York")

# Frozen displacement thresholds, in ATR from the nearest zone edge.
NEAR_ZONE_ATR = Decimal("1")
DISPLACEMENT_THRESHOLDS_ATR = (Decimal("3"), Decimal("5"))
ENVELOPE_ATR = Decimal("3")
CONTINUATION_HORIZONS_MINUTES = (15, 30, 60)

UP = "UP"
DOWN = "DOWN"

# Interaction-session buckets, in America/New_York. Amendment 02 section 3.
SESSION_BUCKETS = (
    ("ETH_EVENING", 18 * 60, 24 * 60),
    ("ETH_OVERNIGHT", 0, 9 * 60 + 30),
    ("RTH_OPEN", 9 * 60 + 30, 10 * 60 + 30),
    ("RTH_MORNING", 10 * 60 + 30, 12 * 60),
    ("RTH_MIDDAY", 12 * 60, 14 * 60),
    ("RTH_AFTERNOON", 14 * 60, 16 * 60),
)


def interaction_session(moment: datetime) -> str:
    """The frozen session bucket containing `moment`, in New York time."""
    local = moment.astimezone(NY)
    minutes = local.hour * 60 + local.minute
    for name, start, end in SESSION_BUCKETS:
        if start <= minutes < end:
            return name
    return "OUT_OF_SESSION"


@dataclass(frozen=True, slots=True)
class DisplacementResult:
    """One threshold crossing, or the reason there wasn't one."""

    threshold_atr: Decimal
    reached: bool
    censored: bool
    bars_to_threshold: int | None
    minutes_to_threshold: int | None
    direction: str | None
    crossing_index: int | None

    @property
    def never_reached(self) -> bool:
        """Distinct from censored: the window was complete and nothing happened."""
        return not self.reached and not self.censored


@dataclass(frozen=True, slots=True)
class ContinuationResult:
    threshold_atr: Decimal
    horizon_minutes: int
    evaluated: bool
    continued: bool | None
    displacement_atr: Decimal | None


@dataclass(frozen=True, slots=True)
class EnvelopeResult:
    eligible: bool
    left_envelope: bool
    censored: bool
    minutes_inside: int | None


def distance_from_zone_atr(
    price: Decimal, zone_low: Decimal, zone_high: Decimal, atr: Decimal
) -> Decimal:
    """Distance from the nearest zone edge, zero inside the zone."""
    if zone_low <= price < zone_high:
        return Decimal(0)
    gap = zone_low - price if price < zone_low else price - zone_high
    return gap / atr


def _excursion_atr(
    bar: Bar, zone_low: Decimal, zone_high: Decimal, atr: Decimal
) -> tuple[Decimal, Decimal]:
    """How far above and below the zone this bar reached, in ATR.

    A bar can extend on both sides of the zone; both are returned rather than
    collapsing to a signed number, so a wide bar cannot hide one direction.
    """
    above = (bar.high - zone_high) / atr if bar.high > zone_high else Decimal(0)
    below = (zone_low - bar.low) / atr if bar.low < zone_low else Decimal(0)
    return above, below


def displacement(
    forward: list[Bar] | tuple[Bar, ...],
    *,
    zone_low: Decimal,
    zone_high: Decimal,
    atr: Decimal,
    threshold_atr: Decimal,
    window_complete: bool,
) -> DisplacementResult:
    """Bars until price first reaches `threshold_atr` from the nearest edge.

    `forward` must start at the first completed bar after the touch bar. When
    both sides reach the threshold on the same bar the larger excursion wins; an
    exact tie resolves to DOWN, deterministically.

    `window_complete` states whether the forward window ran to its natural end.
    When it did not and no crossing occurred, the event is censored rather than
    counted as a non-event.
    """
    for index, bar in enumerate(forward):
        above, below = _excursion_atr(bar, zone_low, zone_high, atr)
        hit_up = above >= threshold_atr
        hit_down = below >= threshold_atr
        if not (hit_up or hit_down):
            continue
        if hit_up and hit_down:
            direction = UP if above > below else DOWN
        else:
            direction = UP if hit_up else DOWN
        return DisplacementResult(
            threshold_atr=threshold_atr,
            reached=True,
            censored=False,
            bars_to_threshold=index + 1,
            minutes_to_threshold=index + 1,
            direction=direction,
            crossing_index=index,
        )
    return DisplacementResult(
        threshold_atr=threshold_atr,
        reached=False,
        censored=not window_complete,
        bars_to_threshold=None,
        minutes_to_threshold=None,
        direction=None,
        crossing_index=None,
    )


def envelope_residence(
    forward: list[Bar] | tuple[Bar, ...],
    *,
    touch_close: Decimal,
    zone_low: Decimal,
    zone_high: Decimal,
    atr: Decimal,
    window_complete: bool,
    envelope_atr: Decimal = ENVELOPE_ATR,
    near_atr: Decimal = NEAR_ZONE_ATR,
) -> EnvelopeResult:
    """Minutes inside a +/- envelope, for touches closing near the zone.

    Eligibility is decided on the touch bar's close, which is known at the touch
    bar's close and so uses no future information.
    """
    if distance_from_zone_atr(touch_close, zone_low, zone_high, atr) > near_atr:
        return EnvelopeResult(False, False, False, None)
    for index, bar in enumerate(forward):
        above, below = _excursion_atr(bar, zone_low, zone_high, atr)
        if above >= envelope_atr or below >= envelope_atr:
            return EnvelopeResult(True, True, False, index)
    return EnvelopeResult(True, False, not window_complete, len(forward))


def continuation(
    forward: list[Bar] | tuple[Bar, ...],
    crossing: DisplacementResult,
    *,
    zone_low: Decimal,
    zone_high: Decimal,
    atr: Decimal,
    horizon_minutes: int,
) -> ContinuationResult:
    """Is price still further from the zone, on the same side, `h` minutes on?

    Measured from the close of the crossing bar. An event that never reached the
    threshold, or whose horizon runs past the available bars, is not evaluated
    rather than being counted as a failure to continue.
    """
    if not crossing.reached or crossing.crossing_index is None:
        return ContinuationResult(crossing.threshold_atr, horizon_minutes, False, None, None)
    target = crossing.crossing_index + horizon_minutes
    if target >= len(forward):
        return ContinuationResult(crossing.threshold_atr, horizon_minutes, False, None, None)

    at_crossing = forward[crossing.crossing_index].close
    at_horizon = forward[target].close
    if crossing.direction == UP:
        moved = (at_horizon - zone_high) / atr
        reference = (at_crossing - zone_high) / atr
    else:
        moved = (zone_low - at_horizon) / atr
        reference = (zone_low - at_crossing) / atr
    return ContinuationResult(
        threshold_atr=crossing.threshold_atr,
        horizon_minutes=horizon_minutes,
        evaluated=True,
        continued=moved >= reference,
        displacement_atr=moved,
    )


def returned_inside(
    forward: list[Bar] | tuple[Bar, ...],
    crossing: DisplacementResult,
    *,
    zone_low: Decimal,
    zone_high: Decimal,
) -> tuple[bool, int | None]:
    """Did price come back inside the zone after reaching the threshold?"""
    if not crossing.reached or crossing.crossing_index is None:
        return False, None
    for offset, bar in enumerate(forward[crossing.crossing_index + 1 :], start=1):
        if not (bar.high < zone_low or bar.low >= zone_high):
            return True, offset
    return False, None


# ---------------------------------------------------------------------------
# Distribution reporting


BAR_BUCKETS = (
    ("1", 1, 1),
    ("2", 2, 2),
    ("3", 3, 3),
    ("4", 4, 4),
    ("5", 5, 5),
    ("6-10", 6, 10),
    ("11-20", 11, 20),
    ("21-60", 21, 60),
    ("61-120", 61, 120),
    ("121+", 121, 10**9),
)


def bar_count_distribution(results: list[DisplacementResult]) -> list[dict]:
    """Share of events reaching the threshold on bar 1, bar 2, and so on.

    `never_reached` and `censored` are separate rows, and every share is taken
    over the complete event count so the column sums to 100%.
    """
    total = len(results)
    if not total:
        return []
    rows = []
    reached = [r for r in results if r.reached]
    for label, low, high in BAR_BUCKETS:
        count = sum(1 for r in reached if low <= (r.bars_to_threshold or 0) <= high)
        rows.append({"bars": label, "events": count})
    rows.append({"bars": "never_reached", "events": sum(1 for r in results if r.never_reached)})
    rows.append({"bars": "censored", "events": sum(1 for r in results if r.censored)})
    _allocate_shares(rows, total)
    assert sum(r["events"] for r in rows) == total, "distribution must be exhaustive"
    return rows


def _allocate_shares(rows: list[dict], total: int) -> None:
    """Percentage shares that sum to exactly 100.00.

    Independent rounding of each share does not sum to 100 — five sevenths of a
    seven-event population round to 100.02. Largest-remainder allocation gives
    each row its floor and hands the leftover hundredths to the largest
    remainders, breaking ties by row order so the result is deterministic.
    """
    scaled = [Decimal(r["events"]) * Decimal(10000) / Decimal(total) for r in rows]
    floors = [v.to_integral_value(rounding="ROUND_FLOOR") for v in scaled]
    leftover = int(Decimal(10000) - sum(floors))
    order = sorted(
        range(len(rows)),
        key=lambda i: (-(scaled[i] - floors[i]), i),
    )
    for position in order[:leftover]:
        floors[position] += 1
    for row, hundredths in zip(rows, floors):
        row["share_pct"] = (hundredths / Decimal(100)).quantize(Decimal("0.01"))


def median_bars(results: list[DisplacementResult]) -> int | None:
    values = sorted(r.bars_to_threshold for r in results if r.reached)
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) // 2
