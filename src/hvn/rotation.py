"""Rotation away from a node: distance and speed together, then persistence.

"Price left the node" is not a rotation. A 0.2 ATR drift and a 3 ATR thrust both
satisfy it, and so does 3 ATR taken over forty bars. A rotation is a *velocity*
claim, so it needs a distance and a deadline in the same condition:

```text
rotation(D, B)  price reached D ATR from the nearest node edge within B bars
rotation_rate   ATR per bar actually achieved
sustained(N)    still at least D ATR away, on the same side, N bars later
```

Measurement starts on the bar after the tap ends, so nothing used to identify
the interaction contributes to the move away from it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import Bar

UP = "UP"
DOWN = "DOWN"

# Frozen rotation grid. Distance in ATR from the nearest node edge, deadline in
# completed bars. Predeclared; never searched.
ROTATION_DISTANCES_ATR = (Decimal("0.5"), Decimal("1.0"), Decimal("2.0"), Decimal("3.0"))
ROTATION_DEADLINES_BARS = (3, 5, 10)
SUSTAIN_HORIZONS_BARS = (5, 10, 20)


@dataclass(frozen=True, slots=True)
class Rotation:
    distance_atr: Decimal
    deadline_bars: int
    rotated: bool
    censored: bool
    bars_taken: int | None
    direction: str | None
    rate_atr_per_bar: Decimal | None


@dataclass(frozen=True, slots=True)
class Sustain:
    horizon_bars: int
    evaluated: bool
    sustained: bool | None
    distance_at_horizon_atr: Decimal | None


def _excursions(
    bar: Bar, node_low: Decimal, node_high: Decimal, atr: Decimal
) -> tuple[Decimal, Decimal]:
    above = (bar.high - node_high) / atr if bar.high > node_high else Decimal(0)
    below = (node_low - bar.low) / atr if bar.low < node_low else Decimal(0)
    return above, below


def find_rotation(
    forward: list[Bar] | tuple[Bar, ...],
    *,
    node_low: Decimal,
    node_high: Decimal,
    atr: Decimal,
    distance_atr: Decimal,
    deadline_bars: int,
) -> Rotation:
    """Did price cover `distance_atr` within `deadline_bars` of the tap ending?

    Both conditions must hold together: this is a speed test, not a distance
    test. A move that reaches the distance on bar `deadline_bars + 1` is not a
    rotation at this setting, and is correctly recorded as one at a looser
    deadline.

    Fewer available bars than the deadline is censoring, not a non-event.
    """
    window = forward[:deadline_bars]
    if len(window) < deadline_bars:
        return Rotation(
            distance_atr, deadline_bars, False, True, None, None, None
        )
    for index, bar in enumerate(window):
        above, below = _excursions(bar, node_low, node_high, atr)
        hit_up = above >= distance_atr
        hit_down = below >= distance_atr
        if not (hit_up or hit_down):
            continue
        if hit_up and hit_down:
            direction = UP if above > below else DOWN
            reached = max(above, below)
        else:
            direction = UP if hit_up else DOWN
            reached = above if hit_up else below
        bars = index + 1
        return Rotation(
            distance_atr=distance_atr,
            deadline_bars=deadline_bars,
            rotated=True,
            censored=False,
            bars_taken=bars,
            direction=direction,
            rate_atr_per_bar=(reached / Decimal(bars)),
        )
    return Rotation(distance_atr, deadline_bars, False, False, None, None, None)


def check_sustain(
    forward: list[Bar] | tuple[Bar, ...],
    rotation: Rotation,
    *,
    node_low: Decimal,
    node_high: Decimal,
    atr: Decimal,
    horizon_bars: int,
) -> Sustain:
    """Is price still that far away, on the same side, `horizon_bars` later?

    Measured on the close, from the rotation bar. A rotation that immediately
    gives the distance back is the case this separates from one that holds.
    """
    if not rotation.rotated or rotation.bars_taken is None:
        return Sustain(horizon_bars, False, None, None)
    target = rotation.bars_taken - 1 + horizon_bars
    if target >= len(forward):
        return Sustain(horizon_bars, False, None, None)
    close = forward[target].close
    if rotation.direction == UP:
        distance = (close - node_high) / atr
    else:
        distance = (node_low - close) / atr
    return Sustain(
        horizon_bars=horizon_bars,
        evaluated=True,
        sustained=distance >= rotation.distance_atr,
        distance_at_horizon_atr=distance,
    )


@dataclass(frozen=True, slots=True)
class MaxExcursion:
    evaluated: bool
    max_distance_atr: Decimal | None
    bars_to_max: int | None
    direction: str | None
    rate_atr_per_bar: Decimal | None


def max_excursion(
    forward: list[Bar] | tuple[Bar, ...],
    *,
    node_low: Decimal,
    node_high: Decimal,
    atr: Decimal,
    window_bars: int,
) -> MaxExcursion:
    """Furthest price got, and how fast, regardless of any threshold.

    Recording this continuously means the rotation grid can be re-cut later from
    the observed distribution without recomputing anything from source bars.
    """
    window = forward[:window_bars]
    if not window:
        return MaxExcursion(False, None, None, None, None)
    best = Decimal(0)
    best_index = 0
    best_direction = None
    for index, bar in enumerate(window):
        above, below = _excursions(bar, node_low, node_high, atr)
        reached = max(above, below)
        if reached > best:
            best = reached
            best_index = index
            best_direction = UP if above >= below else DOWN
    bars = best_index + 1
    return MaxExcursion(
        evaluated=True,
        max_distance_atr=best,
        bars_to_max=bars,
        direction=best_direction,
        rate_atr_per_bar=best / Decimal(bars),
    )
