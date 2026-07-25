"""Generation 3 first-interaction detection for atomic HVNs.

An atomic opportunity is a frozen atomic peak plus its eligible interaction
window. The event is its first eligible post-freeze touch. Events become
available only at the touch-bar close, and every forward measurement starts
with the next completed one-minute bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .atomic import AtomicHvn
from .models import Bar

START_INSIDE = "START_INSIDE"
APPROACH_FROM_BELOW = "APPROACH_FROM_BELOW"
APPROACH_FROM_ABOVE = "APPROACH_FROM_ABOVE"

WICK_ONLY_SAME_SIDE = "WICK_ONLY_SAME_SIDE"
CLOSE_INSIDE = "CLOSE_INSIDE"
CROSS_THROUGH = "CROSS_THROUGH"


@dataclass(frozen=True, slots=True)
class AtomicInteraction:
    atomic_id: str
    touched: bool
    touch_bar_id: str | None
    touch_time: datetime | None
    approach_side: str | None
    touch_class: str | None
    atr_at_touch: Decimal | None
    forward_start_index: int | None
    minute_from_interaction_start: int | None
    exclusion_reason: str = ""


def _approach_side(previous_close: Decimal | None, atomic: AtomicHvn) -> str:
    """Side the market came from, judged on the last close before the touch."""
    if previous_close is None:
        return START_INSIDE
    if atomic.contains(previous_close):
        return START_INSIDE
    return APPROACH_FROM_BELOW if previous_close < atomic.atomic_low else APPROACH_FROM_ABOVE


def _touch_class(bar: Bar, atomic: AtomicHvn, approach_side: str) -> str:
    """Classify the touch bar itself, using only that bar and the approach."""
    if atomic.contains(bar.close):
        return CLOSE_INSIDE
    if approach_side == APPROACH_FROM_BELOW and bar.close >= atomic.atomic_high:
        return CROSS_THROUGH
    if approach_side == APPROACH_FROM_ABOVE and bar.close < atomic.atomic_low:
        return CROSS_THROUGH
    if approach_side == START_INSIDE:
        # Began inside and closed outside: it left rather than crossed through.
        return WICK_ONLY_SAME_SIDE
    return WICK_ONLY_SAME_SIDE


def first_interaction(
    atomic: AtomicHvn,
    bars: tuple[Bar, ...],
    *,
    atr_at_touch_by_index: dict[int, Decimal] | None = None,
    atr_value: Decimal | None = None,
) -> AtomicInteraction:
    """First eligible touch of `atomic` within `bars`.

    `bars` must be the eligible interaction window in chronological order, all
    strictly after the profile freeze time. Only information available at or
    before the touch bar's close is used.
    """
    previous_close: Decimal | None = None
    for index, bar in enumerate(bars):
        if atomic.touched_by(bar.low, bar.high):
            approach = _approach_side(previous_close, atomic)
            atr = (
                atr_at_touch_by_index.get(index)
                if atr_at_touch_by_index is not None
                else atr_value
            )
            if atr is None or atr <= 0:
                return AtomicInteraction(
                    atomic.atomic_id, False, None, None, None, None, None, None, None,
                    "no_frozen_atr_at_touch",
                )
            return AtomicInteraction(
                atomic_id=atomic.atomic_id,
                touched=True,
                touch_bar_id=bar.source_row_id,
                touch_time=bar.close_time,
                approach_side=approach,
                touch_class=_touch_class(bar, atomic, approach),
                atr_at_touch=atr,
                # Forward measurement begins with the next completed bar.
                forward_start_index=index + 1,
                minute_from_interaction_start=index,
            )
        previous_close = bar.close
    return AtomicInteraction(
        atomic.atomic_id, False, None, None, None, None, None, None, None, "never_touched"
    )
