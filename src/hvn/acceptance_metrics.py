from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .interactions import Zone, close_inside, price_to_ticks
from .models import Bar


@dataclass(frozen=True, slots=True)
class HorizonMetrics:
    inside_close_share: Decimal
    mean_overlap_share: Decimal
    midpoint_crossings: int
    path_efficiency: Decimal
    first_inside_close_5: bool | None
    first_inside_close_15: bool | None


@dataclass(frozen=True, slots=True)
class ResidenceMetrics:
    status: str
    continuous_residence_minutes: int | None
    continuous_residence_normalized: Decimal | None
    residence_censored: bool
    first_full_exit_index: int | None
    first_full_exit_side: str | None
    reentry_15: bool | None
    reentry_30: bool | None
    reentry_60: bool | None


def range_overlap_share(bar: Bar, zone: Zone) -> Decimal:
    low, high = price_to_ticks(bar.low), price_to_ticks(bar.high)
    if low == high:
        return Decimal(int(zone.low_ticks <= low < zone.high_ticks))
    overlap = max(
        0,
        min(high, zone.high_ticks - 1) - max(low, zone.low_ticks) + 1,
    )
    return Decimal(overlap) / Decimal(high - low + 1)


def midpoint_crossings(bars: list[Bar] | tuple[Bar, ...], zone: Zone) -> int:
    midpoint_twice = zone.low_ticks + zone.high_ticks
    previous_side = 0
    crossings = 0
    for bar in bars:
        close_twice = 2 * price_to_ticks(bar.close)
        side = -1 if close_twice < midpoint_twice else 1 if close_twice > midpoint_twice else 0
        if side == 0:
            continue
        if previous_side and side != previous_side:
            crossings += 1
        previous_side = side
    return crossings


def close_path_efficiency(touch_close: Decimal, bars: list[Bar] | tuple[Bar, ...]) -> Decimal:
    if not bars:
        raise ValueError("path requires at least one forward bar")
    previous = touch_close
    travelled = Decimal(0)
    for bar in bars:
        travelled += abs(bar.close - previous)
        previous = bar.close
    if travelled == 0:
        return Decimal(0)
    return abs(bars[-1].close - touch_close) / travelled


def horizon_metrics(
    touch_bar: Bar,
    forward: list[Bar] | tuple[Bar, ...],
    zone: Zone,
) -> HorizonMetrics:
    if not forward:
        raise ValueError("complete forward horizon cannot be empty")
    inside = [close_inside(bar, zone) for bar in forward]
    overlap = [range_overlap_share(bar, zone) for bar in forward]
    return HorizonMetrics(
        Decimal(sum(inside)) / Decimal(len(forward)),
        sum(overlap, Decimal(0)) / Decimal(len(overlap)),
        midpoint_crossings(forward, zone),
        close_path_efficiency(touch_bar.close, forward),
        any(inside[:5]) if len(forward) >= 5 else None,
        any(inside[:15]) if len(forward) >= 15 else None,
    )


def _fully_outside(bar: Bar, zone: Zone) -> str | None:
    if price_to_ticks(bar.high) < zone.low_ticks:
        return "BELOW"
    if price_to_ticks(bar.low) >= zone.high_ticks:
        return "ABOVE"
    return None


def residence_metrics(
    forward: list[Bar] | tuple[Bar, ...],
    zone: Zone,
    *,
    atr_at_touch: Decimal,
    complete_followup_minutes: int,
) -> ResidenceMetrics:
    first_inside = next(
        (index for index, bar in enumerate(forward) if close_inside(bar, zone)),
        None,
    )
    if first_inside is None:
        return ResidenceMetrics(
            "NO_INSIDE_CLOSE", None, None, False, None, None, None, None, None
        )
    exit_index = None
    exit_side = None
    for index in range(first_inside + 1, len(forward)):
        side = _fully_outside(forward[index], zone)
        if side is not None:
            exit_index, exit_side = index, side
            break
    if exit_index is None:
        return ResidenceMetrics(
            "RIGHT_CENSORED", None, None, True, None, None, None, None, None
        )
    minutes = exit_index - first_inside
    normalized = (
        Decimal(minutes) * atr_at_touch / (zone.high - zone.low)
    )

    reentries: dict[int, bool | None] = {}
    for horizon in (15, 30, 60):
        available = len(forward) - exit_index - 1
        if available < horizon and complete_followup_minutes < exit_index + 1 + horizon:
            reentries[horizon] = None
        else:
            reentries[horizon] = any(
                _bar_overlap
                for _bar_overlap in (
                    _overlaps(forward[index], zone)
                    for index in range(exit_index + 1, min(len(forward), exit_index + 1 + horizon))
                )
            )
    return ResidenceMetrics(
        "OBSERVED",
        minutes,
        normalized,
        False,
        exit_index,
        exit_side,
        reentries[15],
        reentries[30],
        reentries[60],
    )


def _overlaps(bar: Bar, zone: Zone) -> bool:
    low, high = price_to_ticks(bar.low), price_to_ticks(bar.high)
    return max(low, zone.low_ticks) <= min(high, zone.high_ticks - 1)

