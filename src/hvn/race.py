"""Which came first: the move back off the level, or the move through it.

Every earlier stage measured at a fixed clock — where was price 10, 30 or 120
minutes later. That answers "how much did it move", not "did the level hold",
and the two come apart badly: a level can be broken by three ATR and be back
inside the band at the hundred-and-twentieth minute, and the clock test scores
that as a reversal.

This is a race. Price taps a level; two brackets are placed the same distance
either side of the band midpoint, and whichever is reached first wins:

    favourable   `distance` ATR back the way price came       the level held
    adverse      `distance` ATR onward through the level      the level broke

Run at 1, 3 and 5 ATR, which are three genuinely different questions — whether
a level turns price at all, whether it turns it far, and whether it turns it
far enough to matter.

**Ambiguity is recorded, not resolved.** A single bar whose range covers both
brackets did reach both, and OHLC does not say in which order. Guessing from
the close would bias every result in whichever direction the guess leans, so
those events get their own outcome and are excluded from the rate. On one-minute
bars at 1 ATR they are a real fraction of events, which is precisely why they
must be visible rather than absorbed.

**The reference is the touch price** — where price actually was when the tap
completed — and not any part of the band. This is the correction that the whole
design turns on.

Stage 5 and 6 referenced the band *edges* for state and the *midpoint* for
excursion, and both reward width. Arriving from below, price sits at the low
edge: an edge-referenced reversal is a few ticks while a break must cross the
entire band, so a 3-ATR-wide barrier "reversed" 74.8% of the time against 53.7%
for a narrow one, purely as geometry. A midpoint reference is no better here —
price taps the near edge, already half a band away, so on a 3-ATR band the
1-ATR favourable bracket sits *behind* price and scores at bar zero.

From the touch price both brackets are the same distance away at the moment the
clock starts, whatever the band's width. Width is correlated with the number of
stacked levels, which is the axis under test, so a width-sensitive reference
would manufacture exactly the result this study is trying to detect.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .confluence import ABOVE

FAVOURABLE = "FAVOURABLE"
ADVERSE = "ADVERSE"
AMBIGUOUS = "AMBIGUOUS"
CENSORED = "CENSORED"

DISTANCES_ATR = (Decimal(1), Decimal(3), Decimal(5))


@dataclass(frozen=True, slots=True)
class RaceResult:
    distance_atr: Decimal
    outcome: str
    bars: int | None


def race(forward, *, reference: Decimal, direction: str, atr: Decimal,
         distance: Decimal) -> RaceResult:
    """First bracket touched, walking the bars in order.

    `reference` is the touch price: the close of the bar on which the tap
    completed. `forward` starts on the bar after it, so the first bar here is
    the first bar of the outcome window rather than part of the interaction.
    """
    offset = distance * atr
    if direction == ABOVE:
        # Price arrived from below, so back the way it came is down.
        favourable_price = reference - offset
        adverse_price = reference + offset
        for index, bar in enumerate(forward):
            hit_favourable = bar.low <= favourable_price
            hit_adverse = bar.high >= adverse_price
            if hit_favourable and hit_adverse:
                return RaceResult(distance, AMBIGUOUS, index)
            if hit_favourable:
                return RaceResult(distance, FAVOURABLE, index)
            if hit_adverse:
                return RaceResult(distance, ADVERSE, index)
    else:
        favourable_price = reference + offset
        adverse_price = reference - offset
        for index, bar in enumerate(forward):
            hit_favourable = bar.high >= favourable_price
            hit_adverse = bar.low <= adverse_price
            if hit_favourable and hit_adverse:
                return RaceResult(distance, AMBIGUOUS, index)
            if hit_favourable:
                return RaceResult(distance, FAVOURABLE, index)
            if hit_adverse:
                return RaceResult(distance, ADVERSE, index)
    return RaceResult(distance, CENSORED, None)


def all_races(forward, *, reference: Decimal, direction: str, atr: Decimal,
              distances=DISTANCES_ATR) -> dict[str, RaceResult]:
    return {
        str(distance): race(
            forward, reference=reference, direction=direction, atr=atr, distance=distance
        )
        for distance in distances
    }


__all__ = [
    "ADVERSE",
    "BRACKET_GRID",
    "AMBIGUOUS",
    "CENSORED",
    "DISTANCES_ATR",
    "FAVOURABLE",
    "RaceResult",
    "all_races",
    "excursion_and_brackets",
    "race",
]


# The bracket grid, in ATR. Recording the bar at which each distance is first
# reached in each direction makes every asymmetric target/stop pair derivable
# offline: a 2 ATR target against a 1 ATR stop is `favourable_bar[2] <
# adverse_bar[1]`. Without it, every new pair costs another overnight scan.
BRACKET_GRID = tuple(Decimal(str(x / 2)) for x in range(1, 11))


def excursion_and_brackets(forward, *, reference: Decimal, direction: str,
                           atr: Decimal, grid=BRACKET_GRID):
    """Furthest travel each way, and the bar each grid distance is first reached.

    One pass over the window. `favourable` is back the way price came,
    `adverse` is onward through the level, both measured from the touch price so
    neither is a function of how wide the barrier is.

    A distance never reached records None. That is a censored observation and
    must stay distinguishable from "reached on the final bar", or every
    unresolved event would silently count as resolved at the deadline.
    """
    sign = Decimal(-1) if direction == ABOVE else Decimal(1)
    best_favourable = Decimal(0)
    best_adverse = Decimal(0)
    favourable_bar: dict[str, int | None] = {str(d): None for d in grid}
    adverse_bar: dict[str, int | None] = {str(d): None for d in grid}

    for index, bar in enumerate(forward):
        if sign < 0:
            favourable = (reference - bar.low) / atr
            adverse = (bar.high - reference) / atr
        else:
            favourable = (bar.high - reference) / atr
            adverse = (reference - bar.low) / atr
        if favourable > best_favourable:
            best_favourable = favourable
        if adverse > best_adverse:
            best_adverse = adverse
        for distance in grid:
            key = str(distance)
            if favourable_bar[key] is None and favourable >= distance:
                favourable_bar[key] = index
            if adverse_bar[key] is None and adverse >= distance:
                adverse_bar[key] = index
    return {
        "mfe_atr": float(best_favourable),
        "mae_atr": float(best_adverse),
        "favourable_bar": favourable_bar,
        "adverse_bar": adverse_bar,
    }
