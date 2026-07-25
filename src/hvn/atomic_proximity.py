"""Generation 3 ATR-normalized proximity and rotation metrics.

ATR is frozen at first touch. Every measurement uses completed bars strictly
after the touch bar. The principal outcome is the share of completed closes
within the atomic zone expanded by 0.25 ATR.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .atomic import AtomicHvn
from .models import Bar

# Band expansions in ATR. 0.25 is primary; the rest are sensitivities.
BANDS: tuple[tuple[str, Decimal], ...] = (
    ("exact", Decimal(0)),
    ("b010", Decimal("0.10")),
    ("b025", Decimal("0.25")),
    ("b050", Decimal("0.50")),
)
PRIMARY_BAND = "b025"
HORIZONS: tuple[int, ...] = (5, 15, 30, 60, 120)


def quantile(sorted_values: list[Decimal], fraction: Decimal) -> Decimal | None:
    """Exact type-7 interpolation, matching the rest of the project."""
    if not sorted_values:
        return None
    position = (Decimal(len(sorted_values)) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    remainder = position - Decimal(lower)
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * remainder


def _mean(values: list[Decimal]) -> Decimal | None:
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else None


@dataclass(frozen=True, slots=True)
class ProximityResult:
    horizon: int
    complete: bool
    bars_observed: int
    mean_distance_atr: Decimal | None
    median_distance_atr: Decimal | None
    p75_distance_atr: Decimal | None
    p90_distance_atr: Decimal | None
    mean_peak_distance_atr: Decimal | None
    close_share: dict[str, Decimal | None]
    range_overlap_share: dict[str, Decimal | None]
    peak_crossings: int
    side_changes: int
    close_path_efficiency: Decimal | None
    revisit_after_leaving: dict[str, bool | None]


def _range_overlaps_band(bar: Bar, low: Decimal, high: Decimal) -> bool:
    return not (bar.high < low or bar.low >= high)


def proximity_metrics(
    atomic: AtomicHvn,
    forward_bars: tuple[Bar, ...],
    atr: Decimal,
    *,
    horizons: tuple[int, ...] = HORIZONS,
) -> tuple[ProximityResult, ...]:
    """Proximity and rotation at each horizon, over completed forward bars.

    A horizon is complete only when the full number of forward bars exists;
    otherwise the horizon is marked incomplete and reported as censored rather
    than turned into a partial label.
    """
    results = []
    for horizon in horizons:
        window = forward_bars[:horizon]
        complete = len(forward_bars) >= horizon
        distances = [atomic.distance_atr(bar.close, atr) for bar in window]
        peak_distances = [atomic.peak_distance_atr(bar.close, atr) for bar in window]
        ordered = sorted(distances)

        close_share: dict[str, Decimal | None] = {}
        range_share: dict[str, Decimal | None] = {}
        revisit: dict[str, bool | None] = {}
        for name, expansion in BANDS:
            low, high = atomic.band(expansion, atr)
            inside = [low <= bar.close < high for bar in window]
            overlaps = [_range_overlaps_band(bar, low, high) for bar in window]
            close_share[name] = (
                Decimal(sum(inside)) / Decimal(len(window)) if window else None
            )
            range_share[name] = (
                Decimal(sum(overlaps)) / Decimal(len(window)) if window else None
            )
            revisit[name] = _revisited_after_leaving(inside)

        crossings, side_changes = _rotation(atomic, window)
        results.append(
            ProximityResult(
                horizon=horizon,
                complete=complete,
                bars_observed=len(window),
                mean_distance_atr=_mean(distances),
                median_distance_atr=quantile(ordered, Decimal("0.50")),
                p75_distance_atr=quantile(ordered, Decimal("0.75")),
                p90_distance_atr=quantile(ordered, Decimal("0.90")),
                mean_peak_distance_atr=_mean(peak_distances),
                close_share=close_share,
                range_overlap_share=range_share,
                peak_crossings=crossings,
                side_changes=side_changes,
                close_path_efficiency=_path_efficiency(window),
                revisit_after_leaving=revisit,
            )
        )
    return tuple(results)


def _revisited_after_leaving(inside: list[bool]) -> bool | None:
    """True when the band was entered, left, and entered again.

    None when the band was never entered, or entered and never left, because
    there is no revisit opportunity to observe.
    """
    if not any(inside):
        return None
    first = inside.index(True)
    tail = inside[first:]
    if all(tail):
        return None
    left_at = tail.index(False)
    return any(tail[left_at:])


def _rotation(atomic: AtomicHvn, window: tuple[Bar, ...]) -> tuple[int, int]:
    """Completed-close crossings of the peak centre, and side changes.

    A close exactly at the peak price is treated as neither side and does not
    itself register a crossing; the next decisive close does.
    """
    crossings = 0
    side_changes = 0
    previous_side: int | None = None
    for bar in window:
        if bar.close > atomic.peak_price:
            side = 1
        elif bar.close < atomic.peak_price:
            side = -1
        else:
            continue
        if previous_side is not None and side != previous_side:
            crossings += 1
            side_changes += 1
        previous_side = side
    return crossings, side_changes


def _path_efficiency(window: tuple[Bar, ...]) -> Decimal | None:
    """Net close-to-close displacement over total absolute close-to-close travel."""
    if len(window) < 2:
        return None
    net = abs(window[-1].close - window[0].close)
    travel = sum(
        (abs(window[i].close - window[i - 1].close) for i in range(1, len(window))),
        Decimal(0),
    )
    if travel == 0:
        return Decimal(0)
    return net / travel
