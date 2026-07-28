"""Generation 4 partition driver: zones, controls, touches, forward metrics.

One partition in, one event ledger and one set of aggregate tables out. Causal
throughout: a zone is frozen before its interaction window opens, an event is
known only at the close of its touch bar, and forward measurement starts with
the next completed bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from .gen4_controls import select_controls
from .gen4_outcomes import (
    CONTINUATION_HORIZONS_MINUTES,
    DISPLACEMENT_HORIZONS_MINUTES,
    DISPLACEMENT_THRESHOLDS_ATR,
    band_residence,
    continuation,
    continuation_after_exit,
    displacement,
    envelope_residence,
    excursion_at_horizon,
    interaction_session,
    returned_inside,
)
from .gen5_impulse import (
    IMPULSE_LOOKBACK_BARS,
    FORWARD_HORIZONS_BARS,
    SeasonalVolume,
    compute_impulse,
    dominant_direction,
    dwell_bucket,
    forward_outcome,
)
from .interactions import ApproachSide, Relationship, TouchClass, relationship_window
from .models import Bar, ProfileFamily
from .zones_v4 import NONPOC_HVN_ZONE, POC_HVN_ZONE

RELATIONSHIPS_BY_FAMILY: dict[ProfileFamily, tuple[Relationship, ...]] = {
    ProfileFamily.PRIOR_RTH: (
        Relationship.PRIOR_RTH_TO_ETH,
        Relationship.PRIOR_RTH_TO_RTH,
    ),
    ProfileFamily.FULL_OVERNIGHT: (Relationship.OVERNIGHT_TO_RTH,),
    ProfileFamily.MIDNIGHT: (Relationship.MIDNIGHT_TO_RTH,),
    ProfileFamily.OPENING_HOUR: (Relationship.OPENING_HOUR_TO_RTH,),
}


@dataclass(frozen=True, slots=True)
class Touch:
    index: int
    bar: Bar
    approach_side: str
    touch_class: str


def _approach_side(previous_close: Decimal | None, low: Decimal, high: Decimal) -> str:
    if previous_close is None:
        return ApproachSide.START_INSIDE.value
    if previous_close < low:
        return ApproachSide.BELOW.value
    if previous_close >= high:
        return ApproachSide.ABOVE.value
    return ApproachSide.START_INSIDE.value


def _touch_class(bar: Bar, low: Decimal, high: Decimal) -> str:
    inside_close = low <= bar.close < high
    crossed = bar.low < low and bar.high >= high
    if crossed and not inside_close:
        return TouchClass.CROSS_THROUGH.value
    if inside_close:
        return TouchClass.CLOSE_INSIDE.value
    return TouchClass.WICK_ONLY_SAME_SIDE.value


def find_touches(
    window_bars: list[Bar], low: Decimal, high: Decimal
) -> list[Touch]:
    """Every bar that intersects the interval, with its approach and class.

    Consecutive intersecting bars are one touch: a touch ends when price leaves
    the interval, so a bar that merely continues an existing interaction is not
    counted as a new one.
    """
    touches: list[Touch] = []
    inside_run = False
    for index, bar in enumerate(window_bars):
        intersects = not (bar.high < low or bar.low >= high)
        if not intersects:
            inside_run = False
            continue
        if inside_run:
            continue
        inside_run = True
        previous_close = window_bars[index - 1].close if index else None
        touches.append(
            Touch(
                index=index,
                bar=bar,
                approach_side=_approach_side(previous_close, low, high),
                touch_class=_touch_class(bar, low, high),
            )
        )
    return touches


def measure_event(
    window_bars: list[Bar],
    touch: Touch,
    *,
    low: Decimal,
    high: Decimal,
    atr: Decimal,
    seasonal: SeasonalVolume | None = None,
) -> dict:
    """Every forward quantity for one touch, from the next completed bar on."""
    forward = window_bars[touch.index + 1 :]
    # The window is complete when enough bars remain for the longest horizon a
    # measurement can need; otherwise a non-event is censoring, not evidence.
    longest = max(CONTINUATION_HORIZONS_MINUTES)
    window_complete = len(forward) >= longest

    row: dict = {
        "touch_time": touch.bar.close_time.isoformat(),
        "interaction_session": interaction_session(touch.bar.close_time),
        "approach_side": touch.approach_side,
        "touch_class": touch.touch_class,
        "atr_1m_at_touch": atr,
        "touch_close": touch.bar.close,
        "forward_bars_available": len(forward),
        "window_complete": window_complete,
    }

    for threshold in DISPLACEMENT_THRESHOLDS_ATR:
        key = f"{int(threshold)}atr"
        result = displacement(
            forward,
            zone_low=low,
            zone_high=high,
            atr=atr,
            threshold_atr=threshold,
            window_complete=window_complete,
        )
        row[f"reached_{key}"] = result.reached
        row[f"censored_{key}"] = result.censored
        row[f"never_reached_{key}"] = result.never_reached
        row[f"bars_to_{key}"] = result.bars_to_threshold
        row[f"direction_at_{key}"] = result.direction
        for horizon in CONTINUATION_HORIZONS_MINUTES:
            cont = continuation(
                forward,
                result,
                zone_low=low,
                zone_high=high,
                atr=atr,
                horizon_minutes=horizon,
            )
            row[f"continued_{key}_{horizon}m"] = cont.continued
            row[f"continuation_evaluated_{key}_{horizon}m"] = cont.evaluated
            row[f"displacement_{key}_{horizon}m_atr"] = cont.displacement_atr
        came_back, minutes = returned_inside(
            forward, result, zone_low=low, zone_high=high
        )
        row[f"returned_inside_after_{key}"] = came_back
        row[f"minutes_to_return_after_{key}"] = minutes

    envelope = envelope_residence(
        forward,
        touch_close=touch.bar.close,
        zone_low=low,
        zone_high=high,
        atr=atr,
        window_complete=window_complete,
    )
    row["envelope_eligible"] = envelope.eligible
    row["envelope_left"] = envelope.left_envelope
    row["envelope_censored"] = envelope.censored
    row["envelope_minutes_inside"] = envelope.minutes_inside

    # Amendment 03: time-capped displacement, which cannot saturate the way an
    # open-ended threshold does.
    for horizon in DISPLACEMENT_HORIZONS_MINUTES:
        reach = excursion_at_horizon(
            forward,
            zone_low=low,
            zone_high=high,
            atr=atr,
            horizon_minutes=horizon,
        )
        row[f"excursion_evaluated_{horizon}m"] = reach.evaluated
        row[f"max_excursion_{horizon}m_atr"] = reach.max_abs_atr
        row[f"max_up_{horizon}m_atr"] = reach.max_up_atr
        row[f"max_down_{horizon}m_atr"] = reach.max_down_atr
        row[f"net_close_{horizon}m_atr"] = reach.net_close_atr

    # Amendment 03: residence inside a 5 ATR band, and what happens on exit.
    band = band_residence(
        forward,
        zone_low=low,
        zone_high=high,
        atr=atr,
        window_complete=window_complete,
    )
    row["band_left"] = band.left_band
    row["band_censored"] = band.censored
    row["band_minutes_inside"] = band.minutes_inside
    row["band_exit_direction"] = band.exit_direction
    row["breakout_volume_ratio"] = band.breakout_volume_ratio
    for horizon in CONTINUATION_HORIZONS_MINUTES:
        after = continuation_after_exit(
            forward,
            band,
            zone_low=low,
            zone_high=high,
            atr=atr,
            horizon_minutes=horizon,
        )
        row[f"band_continued_{horizon}m"] = after.continued
        row[f"band_continuation_evaluated_{horizon}m"] = after.evaluated
        row[f"band_displacement_{horizon}m_atr"] = after.displacement_atr

    # Amendment 04: directional impulse into and out of the zone, and whether
    # the move that followed continued or reverted.
    row |= _impulse_block(window_bars, touch, low=low, high=high, atr=atr, seasonal=seasonal)
    return row


def _impulse_block(
    window_bars: list[Bar],
    touch: Touch,
    *,
    low: Decimal,
    high: Decimal,
    atr: Decimal,
    seasonal: SeasonalVolume | None,
) -> dict:
    """Approach and departure impulse, dwell, and the forward outcome.

    The approach window ends at the touch bar and is therefore known at the
    touch bar's close. The departure window begins at the next completed bar,
    and the forward outcome is measured from the end of that departure window,
    so no quantity used to classify an event overlaps the outcome it predicts.
    """
    forward = window_bars[touch.index + 1 :]
    out: dict = {}

    approach = window_bars[max(0, touch.index - IMPULSE_LOOKBACK_BARS + 1) : touch.index + 1]
    approach_direction = dominant_direction(approach) if len(approach) >= 2 else None
    for label, direction in (("up", 1), ("down", -1)):
        result = compute_impulse(approach, direction=direction, atr=atr, seasonal=seasonal)
        out[f"approach_{label}_displacement_atr"] = result.directional_displacement_atr
        out[f"approach_{label}_volume_ratio"] = result.directional_volume_ratio
        out[f"approach_{label}_efficiency"] = result.efficiency
    out["approach_impulse_direction"] = approach_direction
    out["approach_impulse_evaluated"] = approach_direction is not None

    # Dwell: completed bars price stays within 1 ATR of the zone after the touch.
    dwell = band_residence(
        forward,
        zone_low=low,
        zone_high=high,
        atr=atr,
        window_complete=len(forward) >= max(FORWARD_HORIZONS_BARS),
        band_atr=Decimal(1),
    )
    out["dwell_bars"] = dwell.minutes_inside
    out["dwell_bucket"] = dwell_bucket(dwell.minutes_inside)
    out["dwell_left"] = dwell.left_band
    out["dwell_censored"] = dwell.censored

    departure = forward[:IMPULSE_LOOKBACK_BARS]
    if len(departure) < 2:
        out["departure_impulse_evaluated"] = False
        return out
    direction = dominant_direction(departure)
    result = compute_impulse(departure, direction=direction, atr=atr, seasonal=seasonal)
    out["departure_impulse_evaluated"] = result.evaluated
    out["departure_direction"] = "UP" if direction == 1 else "DOWN"
    out["departure_displacement_atr"] = result.directional_displacement_atr
    out["departure_displacement_bucket"] = result.displacement_bucket
    out["departure_volume_ratio"] = result.directional_volume_ratio
    out["departure_volume_bucket"] = result.volume_bucket
    out["departure_efficiency"] = result.efficiency
    out["departure_efficiency_bucket"] = result.efficiency_bucket
    out["departure_net_close_atr"] = result.net_close_change_atr
    out["departure_seasonal_baseline"] = result.seasonal_baseline_available

    reference = departure[-1].close
    after = forward[IMPULSE_LOOKBACK_BARS:]
    for horizon in FORWARD_HORIZONS_BARS:
        outcome = forward_outcome(
            after,
            direction=direction,
            reference_close=reference,
            atr=atr,
            horizon_bars=horizon,
        )
        out[f"impulse_outcome_evaluated_{horizon}b"] = outcome.evaluated
        out[f"impulse_continued_{horizon}b"] = outcome.continued
        out[f"impulse_reverted_{horizon}b"] = outcome.reverted
        out[f"impulse_signed_move_{horizon}b_atr"] = outcome.signed_move_atr
    return out


def interaction_bars(
    bars_by_symbol: dict[str, tuple[Bar, ...]],
    symbol: str,
    relationship: Relationship,
    *,
    source_date: date,
    interaction_date: date,
) -> list[Bar]:
    window = relationship_window(
        relationship, source_date=source_date, interaction_date=interaction_date
    )
    return sorted(
        (
            b
            for b in bars_by_symbol[symbol]
            if window.start <= b.start_time < window.end
        ),
        key=lambda b: b.close_time,
    )


def events_for_interval(
    window_bars: list[Bar],
    *,
    interval_id: str,
    population: str,
    zone_class: str,
    low: Decimal,
    high: Decimal,
    atr: Decimal,
    base: dict,
    seasonal=None,
) -> tuple[list[dict], dict]:
    """First-touch and re-touch rows for one interval, plus its touch summary.

    Conditional metrics are computed on the first touch only. Re-touches are
    counted and carried as their own rows so the two are never pooled.
    """
    touches = find_touches(window_bars, low, high)
    summary = base | {
        "interval_id": interval_id,
        "population": population,
        "zone_class": zone_class,
        "touched": bool(touches),
        "touch_count": len(touches),
        "retouch_count": max(0, len(touches) - 1),
        "minutes_to_first_touch": touches[0].index if touches else None,
        "zone_low": low,
        "zone_high": high,
        "zone_width_points": high - low,
        "zone_width_atr": (high - low) / atr,
    }
    rows: list[dict] = []
    for order, touch in enumerate(touches):
        measured = measure_event(
            window_bars, touch, low=low, high=high, atr=atr, seasonal=seasonal
        )
        rows.append(
            base
            | measured
            | {
                "interval_id": interval_id,
                "event_id": f"{interval_id}-T{order:03d}",
                "population": population,
                "zone_class": zone_class,
                "touch_order": order,
                "is_first_touch": order == 0,
                "zone_low": low,
                "zone_high": high,
                "zone_width_points": high - low,
                "zone_width_atr": (high - low) / atr,
            }
        )
    return rows, summary


def zone_population(zone_class: str) -> str:
    """POC and non-POC are reported separately and never pooled."""
    if zone_class == POC_HVN_ZONE:
        return "POC"
    if zone_class == NONPOC_HVN_ZONE:
        return "NONPOC"
    return "OTHER"


__all__ = [
    "RELATIONSHIPS_BY_FAMILY",
    "Touch",
    "events_for_interval",
    "find_touches",
    "interaction_bars",
    "measure_event",
    "select_controls",
    "zone_population",
]
