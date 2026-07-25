"""Generation 3 confirmed departure and post-departure excursion.

Primary departure: two consecutive completed one-minute closes outside the
same side of the atomic zone +/- 0.25 ATR. Departure time is the close of the
second confirming bar, and excursion measurement begins with the bar after it.
Neither confirmation bar enters the excursion metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .atomic import AtomicHvn
from .models import Bar

ABOVE = "ABOVE"
BELOW = "BELOW"

EXCURSION_HORIZONS: tuple[int, ...] = (5, 15, 30, 60, 120)
THRESHOLDS: tuple[Decimal, ...] = (
    Decimal("0.25"),
    Decimal("0.50"),
    Decimal("1.00"),
    Decimal("1.50"),
    Decimal("2.00"),
)
ROLLING_WINDOW = 5


@dataclass(frozen=True, slots=True)
class Departure:
    departed: bool
    side: str | None
    confirm_index: int | None       # index of the second confirming bar
    excursion_start_index: int | None
    departed_boundary: Decimal | None
    minutes_to_departure: int | None
    right_censored: bool


@dataclass(frozen=True, slots=True)
class ExcursionResult:
    horizon: int
    complete: bool
    bars_observed: int
    directional_displacement_atr: Decimal | None
    mfe_atr: Decimal | None
    mae_atr: Decimal | None
    max_distance_from_peak_atr: Decimal | None
    average_speed_atr_per_minute: Decimal | None
    average_speed_points_per_minute: Decimal | None
    max_rolling_5m_speed_atr_per_minute: Decimal | None
    minutes_to_threshold: dict[str, int | None]
    reclaimed_band: bool
    revisited_exact_zone: bool
    crossed_to_opposite_side: bool


def confirmed_departure(
    atomic: AtomicHvn,
    forward_bars: tuple[Bar, ...],
    atr: Decimal,
    *,
    expansion: Decimal = Decimal("0.25"),
    consecutive: int = 2,
) -> Departure:
    """First run of `consecutive` closes outside the same side of the band."""
    low, high = atomic.band(expansion, atr)
    streak_side: str | None = None
    streak = 0
    for index, bar in enumerate(forward_bars):
        if bar.close >= high:
            side = ABOVE
        elif bar.close < low:
            side = BELOW
        else:
            side = None
        if side is None or side != streak_side:
            streak_side, streak = side, (1 if side else 0)
        else:
            streak += 1
        if side is not None and streak >= consecutive:
            return Departure(
                departed=True,
                side=side,
                confirm_index=index,
                excursion_start_index=index + 1,
                departed_boundary=high if side == ABOVE else low,
                minutes_to_departure=index + 1,
                right_censored=False,
            )
    return Departure(False, None, None, None, None, None, right_censored=True)


def _signed(side: str, value: Decimal) -> Decimal:
    return value if side == ABOVE else -value


def excursion_metrics(
    atomic: AtomicHvn,
    forward_bars: tuple[Bar, ...],
    atr: Decimal,
    departure: Departure,
    *,
    horizons: tuple[int, ...] = EXCURSION_HORIZONS,
    expansion: Decimal = Decimal("0.25"),
) -> tuple[ExcursionResult, ...]:
    """Excursion in the departure direction, starting after confirmation."""
    if not departure.departed or departure.excursion_start_index is None:
        return ()
    path = forward_bars[departure.excursion_start_index :]
    boundary = departure.departed_boundary
    side = departure.side
    band_low, band_high = atomic.band(expansion, atr)

    results = []
    for horizon in horizons:
        window = path[:horizon]
        complete = len(path) >= horizon
        if not window:
            results.append(
                ExcursionResult(
                    horizon, complete, 0, None, None, None, None, None, None, None,
                    {str(t): None for t in THRESHOLDS}, False, False, False,
                )
            )
            continue

        # Favourable is further in the departure direction; adverse is back
        # toward and past the zone.
        favourable = [_signed(side, bar.high - boundary) if side == ABOVE
                      else _signed(side, bar.low - boundary) for bar in window]
        adverse = [_signed(side, bar.low - boundary) if side == ABOVE
                   else _signed(side, bar.high - boundary) for bar in window]
        displacement = _signed(side, window[-1].close - boundary) / atr
        mfe = max(favourable) / atr
        mae = min(adverse) / atr
        max_peak_distance = max(
            atomic.peak_distance_atr(bar.high, atr) if side == ABOVE
            else atomic.peak_distance_atr(bar.low, atr)
            for bar in window
        )
        minutes = Decimal(len(window))
        points = _signed(side, window[-1].close - boundary)

        minutes_to_threshold: dict[str, int | None] = {}
        for threshold in THRESHOLDS:
            reached = None
            for offset, value in enumerate(favourable, start=1):
                if value / atr >= threshold:
                    reached = offset
                    break
            minutes_to_threshold[str(threshold)] = reached

        results.append(
            ExcursionResult(
                horizon=horizon,
                complete=complete,
                bars_observed=len(window),
                directional_displacement_atr=displacement,
                mfe_atr=mfe,
                mae_atr=mae,
                max_distance_from_peak_atr=max_peak_distance,
                average_speed_atr_per_minute=displacement / minutes,
                average_speed_points_per_minute=points / minutes,
                max_rolling_5m_speed_atr_per_minute=_max_rolling_speed(
                    window, boundary, side, atr
                ),
                minutes_to_threshold=minutes_to_threshold,
                reclaimed_band=any(
                    band_low <= bar.close < band_high for bar in window
                ),
                revisited_exact_zone=any(
                    atomic.touched_by(bar.low, bar.high) for bar in window
                ),
                crossed_to_opposite_side=any(
                    bar.close < band_low if side == ABOVE else bar.close >= band_high
                    for bar in window
                ),
            )
        )
    return tuple(results)


def _max_rolling_speed(
    window: tuple[Bar, ...], boundary: Decimal, side: str, atr: Decimal
) -> Decimal | None:
    """Fastest directional close-to-close movement over any 5-minute window."""
    if len(window) < ROLLING_WINDOW:
        return None
    best: Decimal | None = None
    for start in range(len(window) - ROLLING_WINDOW + 1):
        chunk = window[start : start + ROLLING_WINDOW]
        moved = _signed(side, chunk[-1].close - chunk[0].close) / atr
        speed = moved / Decimal(ROLLING_WINDOW)
        best = speed if best is None else max(best, speed)
    return best
