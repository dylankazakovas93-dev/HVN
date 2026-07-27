"""Generation 3 forward-outcome metrics.

Implements STAGE_02_GENERATION_3_OUTCOME_SPEC.md and
STAGE_02_GENERATION_3_ACTIVITY_SPEC.md. Every function consumes only completed
post-touch bars; the touch bar itself is never passed in.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .models import Bar

TICK = Decimal("0.25")
HORIZONS: tuple[int, ...] = (5, 15, 30, 60, 120)
PRIMARY_HORIZON = 30
EXCURSION_HORIZONS: tuple[int, ...] = (15, 30, 60)

BELOW, INSIDE, ABOVE = -1, 0, 1
SAME_SIDE_REJECTION = "SAME_SIDE_REJECTION"
OPPOSITE_SIDE_TRAVERSAL = "OPPOSITE_SIDE_TRAVERSAL"
APPROACH_FROM_BELOW = "APPROACH_FROM_BELOW"
APPROACH_FROM_ABOVE = "APPROACH_FROM_ABOVE"


def _mean(values) -> Decimal | None:
    values = list(values)
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else None


def _sqrt(value: Decimal) -> Decimal:
    if value <= 0:
        return Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 40
        return value.sqrt()


def close_state(price: Decimal, low: Decimal, high: Decimal) -> int:
    """-1 below the node, 0 inside, +1 above. Node is [low, high)."""
    if price < low:
        return BELOW
    if price >= high:
        return ABOVE
    return INSIDE


def overlap_share(bar: Bar, low: Decimal, high: Decimal) -> Decimal:
    """Share of the bar's range lying inside [low, high).

    A zero-range bar contributes 1 when its price is inside the zone, else 0.
    """
    span = bar.high - bar.low
    if span <= 0:
        return Decimal(1) if low <= bar.low < high else Decimal(0)
    lower = max(bar.low, low)
    upper = min(bar.high, high)
    if upper <= lower:
        return Decimal(0)
    return (upper - lower) / span


# --------------------------------------------------------------------------
# Acceptance and rotation
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AcceptanceResult:
    horizon: int
    complete: bool
    bars_observed: int
    inside_close_share: Decimal | None
    mean_range_overlap_share: Decimal | None
    first_inside_close_minute: int | None
    midpoint_crossings: int
    full_rotation_count: int
    any_rotation: bool
    close_path_efficiency: Decimal | None


def acceptance_metrics(
    forward: tuple[Bar, ...],
    node_low: Decimal,
    node_high: Decimal,
    *,
    horizons: tuple[int, ...] = HORIZONS,
) -> tuple[AcceptanceResult, ...]:
    midpoint = (node_low + node_high) / 2
    out = []
    for horizon in horizons:
        window = forward[:horizon]
        complete = len(forward) >= horizon
        if not window:
            out.append(AcceptanceResult(horizon, complete, 0, None, None, None,
                                        0, 0, False, None))
            continue
        states = [close_state(b.close, node_low, node_high) for b in window]
        inside = [s == INSIDE for s in states]
        first_inside = inside.index(True) + 1 if any(inside) else None
        out.append(
            AcceptanceResult(
                horizon=horizon,
                complete=complete,
                bars_observed=len(window),
                inside_close_share=Decimal(sum(inside)) / Decimal(len(window)),
                mean_range_overlap_share=_mean(
                    overlap_share(b, node_low, node_high) for b in window
                ),
                first_inside_close_minute=first_inside,
                midpoint_crossings=_midpoint_crossings(window, midpoint),
                full_rotation_count=(rotations := _full_rotations(states)),
                any_rotation=rotations > 0,
                close_path_efficiency=_close_path_efficiency(window),
            )
        )
    return tuple(out)


def _midpoint_crossings(window: tuple[Bar, ...], midpoint: Decimal) -> int:
    """Close-path crossings of the frozen node midpoint.

    A close exactly at the midpoint is neutral and carries the previous
    non-neutral side forward, so crossing counts stay deterministic.
    """
    crossings = 0
    previous: int | None = None
    for bar in window:
        if bar.close > midpoint:
            side = 1
        elif bar.close < midpoint:
            side = -1
        else:
            continue
        if previous is not None and side != previous:
            crossings += 1
        previous = side
    return crossings


def _full_rotations(states: list[int]) -> int:
    """Completed alternating rotations through the node.

    A rotation needs a confirmed outside state, an intervening node interaction
    or inside close, then a confirmed outside state on the opposite side.
    """
    rotations = 0
    anchor: int | None = None
    touched_since = False
    for state in states:
        if state == INSIDE:
            touched_since = True
            continue
        if anchor is None:
            anchor = state
            touched_since = False
            continue
        if state != anchor and touched_since:
            rotations += 1
            anchor = state
            touched_since = False
        elif state != anchor:
            anchor = state
    return rotations


def _close_path_efficiency(window: tuple[Bar, ...]) -> Decimal | None:
    if len(window) < 2:
        return None
    net = abs(window[-1].close - window[0].close)
    travel = sum(
        (abs(window[i].close - window[i - 1].close) for i in range(1, len(window))),
        Decimal(0),
    )
    return Decimal(0) if travel == 0 else net / travel


# --------------------------------------------------------------------------
# Residence
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResidenceResult:
    horizon: int
    inside_residence_minutes: int
    continuous_residence_after_first_inside_close: int
    longest_inside_close_run: int
    local_band_occupancy_share: Decimal | None
    reentry_count: int
    normalized_residence: Decimal | None


def residence_metrics(
    forward: tuple[Bar, ...],
    node_low: Decimal,
    node_high: Decimal,
    atr: Decimal,
    *,
    horizons: tuple[int, ...] = HORIZONS,
) -> tuple[ResidenceResult, ...]:
    width = node_high - node_low
    band_low, band_high = node_low - atr, node_high + atr
    out = []
    for horizon in horizons:
        window = forward[:horizon]
        if not window:
            out.append(ResidenceResult(horizon, 0, 0, 0, None, 0, None))
            continue
        inside = [close_state(b.close, node_low, node_high) == INSIDE for b in window]
        runs = _runs(inside)
        first_run = runs[0][1] if runs else 0
        band = [band_low <= b.close < band_high for b in window]
        out.append(
            ResidenceResult(
                horizon=horizon,
                inside_residence_minutes=sum(inside),
                continuous_residence_after_first_inside_close=first_run,
                longest_inside_close_run=max((n for _, n in runs), default=0),
                local_band_occupancy_share=Decimal(sum(band)) / Decimal(len(window)),
                reentry_count=max(len(runs) - 1, 0),
                normalized_residence=(
                    Decimal(sum(inside)) * atr / width if width > 0 else None
                ),
            )
        )
    return tuple(out)


def _runs(flags: list[bool]) -> list[tuple[int, int]]:
    out, start = [], None
    for index, flag in enumerate(flags):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            out.append((start, index - start))
            start = None
    if start is not None:
        out.append((start, len(flags) - start))
    return out


# --------------------------------------------------------------------------
# Post-touch activity concentration
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ActivityResult:
    horizon: int
    band: str
    node_volume: Decimal
    band_volume: Decimal
    node_tpo: int
    band_tpo: int
    # Binary zone-touch frequency, preserved separately. These never enter the
    # composite concentration metric.
    bars_touching_node: int
    bars_touching_band: int
    node_touch_bar_share: Decimal | None
    node_volume_capture_share: Decimal | None
    node_tpo_capture_share: Decimal | None
    node_width_share: Decimal | None
    volume_concentration_ratio: Decimal | None
    tpo_concentration_ratio: Decimal | None
    activity_concentration_ratio: Decimal | None
    undefined_reason: str


def _tick_range(low: Decimal, high: Decimal) -> tuple[Decimal, int]:
    """First tick at or above `low`, and the count of ticks up to `high`."""
    first = (low / TICK).to_integral_value(rounding="ROUND_CEILING") * TICK
    if first > high:
        return first, 0
    count = int((high - first) / TICK) + 1
    return first, count


def activity_metrics(
    forward: tuple[Bar, ...],
    node_low: Decimal,
    node_high: Decimal,
    band_low: Decimal,
    band_high: Decimal,
    *,
    band_name: str,
    horizons: tuple[int, ...] = HORIZONS,
) -> tuple[ActivityResult, ...]:
    """Volume and TPO captured by the node relative to its reference band.

    Post-touch bar volume is allocated uniformly across the ticks the bar
    occupies, matching the Stage 1 allocation convention. TPO occupancy is
    **bin-level**: each bar adds one TPO to every bin it occupies, so a bar
    spanning the whole reference band yields a TPO concentration ratio of
    exactly 1 regardless of node width.
    """
    _, node_ticks = _tick_range(node_low, node_high - TICK)
    _, band_ticks = _tick_range(band_low, band_high - TICK)
    out = []
    for horizon in horizons:
        window = forward[:horizon]
        node_volume = band_volume = Decimal(0)
        node_tpo = band_tpo = 0
        bars_touching_node = bars_touching_band = 0
        for bar in window:
            first, count = _tick_range(bar.low, bar.high)
            if count <= 0:
                continue
            per_tick = bar.volume / Decimal(count)
            in_node = in_band = 0
            for step in range(count):
                price = first + TICK * step
                if band_low <= price < band_high:
                    in_band += 1
                    if node_low <= price < node_high:
                        in_node += 1
            node_volume += per_tick * Decimal(in_node)
            band_volume += per_tick * Decimal(in_band)
            # Bin-level TPO: one per occupied bin, not one per intersecting bar.
            node_tpo += in_node
            band_tpo += in_band
            bars_touching_node += 1 if in_node else 0
            bars_touching_band += 1 if in_band else 0

        reason = ""
        if not window:
            reason = "NO_FORWARD_BARS"
        elif band_volume <= 0:
            reason = "ZERO_BAND_VOLUME"
        elif band_tpo <= 0:
            reason = "ZERO_BAND_TPO"
        elif band_ticks <= 0:
            reason = "ZERO_BAND_WIDTH"

        touch_share = (
            Decimal(bars_touching_node) / Decimal(bars_touching_band)
            if bars_touching_band
            else None
        )
        if reason:
            out.append(ActivityResult(horizon, band_name, node_volume, band_volume,
                                      node_tpo, band_tpo, bars_touching_node,
                                      bars_touching_band, touch_share,
                                      None, None, None, None, None, None, reason))
            continue

        v_share = node_volume / band_volume
        t_share = Decimal(node_tpo) / Decimal(band_tpo)
        width_share = Decimal(node_ticks) / Decimal(band_ticks)
        # Formed as a single division so the repeating width share cannot
        # compound into the ratio: (V_node * band_ticks) / (V_band * node_ticks).
        v_ratio = (node_volume * Decimal(band_ticks)) / (
            band_volume * Decimal(node_ticks)
        )
        t_ratio = (Decimal(node_tpo) * Decimal(band_ticks)) / (
            Decimal(band_tpo) * Decimal(node_ticks)
        )
        out.append(
            ActivityResult(
                horizon=horizon,
                band=band_name,
                node_volume=node_volume,
                band_volume=band_volume,
                node_tpo=node_tpo,
                band_tpo=band_tpo,
                bars_touching_node=bars_touching_node,
                bars_touching_band=bars_touching_band,
                node_touch_bar_share=touch_share,
                node_volume_capture_share=v_share,
                node_tpo_capture_share=t_share,
                node_width_share=width_share,
                volume_concentration_ratio=v_ratio,
                tpo_concentration_ratio=t_ratio,
                activity_concentration_ratio=_sqrt(v_ratio * t_ratio),
                undefined_reason="",
            )
        )
    return tuple(out)


@dataclass(frozen=True, slots=True)
class MarketRateResult:
    horizon: int
    volume_rate_ratio: Decimal | None
    range_rate_ratio: Decimal | None
    undefined_reason: str


def market_rate_metrics(
    forward: tuple[Bar, ...],
    pre_touch: tuple[Bar, ...],
    *,
    horizons: tuple[int, ...] = HORIZONS,
) -> tuple[MarketRateResult, ...]:
    """Overall market activity after the tap, not node-local concentration."""
    pre_volume = _mean(b.volume for b in pre_touch)
    pre_range = _mean(b.high - b.low for b in pre_touch)
    out = []
    for horizon in horizons:
        window = forward[:horizon]
        if not window:
            out.append(MarketRateResult(horizon, None, None, "NO_FORWARD_BARS"))
            continue
        post_volume = _mean(b.volume for b in window)
        post_range = _mean(b.high - b.low for b in window)
        reason = ""
        if pre_volume is None or pre_volume <= 0:
            reason = "ZERO_PRE_TOUCH_VOLUME"
        elif pre_range is None or pre_range <= 0:
            reason = "ZERO_PRE_TOUCH_RANGE"
        out.append(
            MarketRateResult(
                horizon,
                None if reason else post_volume / pre_volume,
                None if reason else post_range / pre_range,
                reason,
            )
        )
    return tuple(out)


# --------------------------------------------------------------------------
# Departure and excursion
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DepartureResult:
    departed: bool
    side: int | None
    confirm_index: int | None
    excursion_start_index: int | None
    minutes_to_departure: int | None
    departure_class: str


def confirmed_departure(
    forward: tuple[Bar, ...],
    node_low: Decimal,
    node_high: Decimal,
    approach_side: str,
) -> DepartureResult:
    """Two consecutive completed closes fully outside the node on one side."""
    streak_side: int | None = None
    streak = 0
    for index, bar in enumerate(forward):
        state = close_state(bar.close, node_low, node_high)
        if state == INSIDE:
            streak_side, streak = None, 0
            continue
        if state != streak_side:
            streak_side, streak = state, 1
        else:
            streak += 1
        if streak >= 2:
            if approach_side == APPROACH_FROM_BELOW:
                classification = (
                    SAME_SIDE_REJECTION if state == BELOW else OPPOSITE_SIDE_TRAVERSAL
                )
            elif approach_side == APPROACH_FROM_ABOVE:
                classification = (
                    SAME_SIDE_REJECTION if state == ABOVE else OPPOSITE_SIDE_TRAVERSAL
                )
            else:
                classification = ""
            return DepartureResult(True, state, index, index + 1, index + 1,
                                   classification)
    return DepartureResult(False, None, None, None, None, "")


@dataclass(frozen=True, slots=True)
class ExcursionResult:
    horizon: int
    complete: bool
    bars_observed: int
    directional_excursion_points: Decimal | None
    adverse_excursion_points: Decimal | None
    directional_excursion_atr: Decimal | None
    adverse_excursion_atr: Decimal | None
    directional_excursion_widths: Decimal | None
    adverse_excursion_widths: Decimal | None
    reentered: bool
    minutes_to_reentry: int | None


def excursion_metrics(
    forward: tuple[Bar, ...],
    node_low: Decimal,
    node_high: Decimal,
    atr: Decimal,
    departure: DepartureResult,
    *,
    horizons: tuple[int, ...] = EXCURSION_HORIZONS,
) -> tuple[ExcursionResult, ...]:
    """Excursion after the confirmation bar. Never called profit, MFE or MAE."""
    if not departure.departed or departure.excursion_start_index is None:
        return ()
    path = forward[departure.excursion_start_index :]
    width = node_high - node_low
    edge = node_high if departure.side == ABOVE else node_low
    sign = Decimal(1) if departure.side == ABOVE else Decimal(-1)

    out = []
    for horizon in horizons:
        window = path[:horizon]
        complete = len(path) >= horizon
        if not window:
            out.append(ExcursionResult(horizon, complete, 0, None, None, None,
                                       None, None, None, False, None))
            continue
        extremes = [
            sign * ((bar.high if departure.side == ABOVE else bar.low) - edge)
            for bar in window
        ]
        adverse = [
            sign * ((bar.low if departure.side == ABOVE else bar.high) - edge)
            for bar in window
        ]
        directional = max(extremes)
        against = min(adverse)
        reentry = next(
            (
                offset
                for offset, bar in enumerate(window, start=1)
                if close_state(bar.close, node_low, node_high) == INSIDE
            ),
            None,
        )
        out.append(
            ExcursionResult(
                horizon=horizon,
                complete=complete,
                bars_observed=len(window),
                directional_excursion_points=directional,
                adverse_excursion_points=against,
                directional_excursion_atr=directional / atr,
                adverse_excursion_atr=against / atr,
                directional_excursion_widths=(
                    directional / width if width > 0 else None
                ),
                adverse_excursion_widths=against / width if width > 0 else None,
                reentered=reentry is not None,
                minutes_to_reentry=reentry,
            )
        )
    return tuple(out)
