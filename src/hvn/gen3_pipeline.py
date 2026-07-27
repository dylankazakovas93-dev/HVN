"""Generation 3 development pipeline: structure, interactions and outcomes.

Uses the frozen Pilot V4 detector for node construction and the locked outcome
engine for forward measurement. Untouched node and control opportunities are
always retained.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from .atomic_v2 import POC_ATOMIC, POC_BROAD, poc_plateau, profile_normalization, value_area
from .atomic_v3 import NONPOC_ATOMIC_HVN, select_composite_controls
from .atomic_v4 import classify_final_nodes
from .atr import wilder_atr
from .engine import construct_profile
from .gen3_outcomes import (
    APPROACH_FROM_ABOVE,
    APPROACH_FROM_BELOW,
    EXCURSION_HORIZONS,
    HORIZONS,
    acceptance_metrics,
    activity_metrics,
    confirmed_departure,
    excursion_metrics,
    market_rate_metrics,
    residence_metrics,
)
from .interactions import Relationship, relationship_window
from .models import AllocationMethod, Bar
from .sessions import profile_window
from .stage02_ledger import write_deterministic_gzip_csv
from .stage02_pipeline import (
    EXPECTED_SOURCE_MINUTES,
    FAMILY_BY_RELATIONSHIP,
    RATIOS,
    AtrSelector,
    ContractSelector,
    _consecutive,
    trading_dates,
)

MAX_FORWARD = max(HORIZONS)
PRE_TOUCH_WINDOW = 15

START_INSIDE = "START_INSIDE"
WICK_ONLY_SAME_SIDE = "WICK_ONLY_SAME_SIDE"
CLOSE_INSIDE = "CLOSE_INSIDE"
CROSS_THROUGH = "CROSS_THROUGH"

INSIDE_VALUE = "INSIDE_VALUE"
VALUE_EDGE = "VALUE_EDGE"
OUTSIDE_VALUE = "OUTSIDE_VALUE"


@dataclass
class Gen3YearResult:
    node_opportunities: list = field(default_factory=list)
    node_events: list = field(default_factory=list)
    control_opportunities: list = field(default_factory=list)
    control_events: list = field(default_factory=list)
    forward_metrics: list = field(default_factory=list)
    activity_metrics: list = field(default_factory=list)
    departure_metrics: list = field(default_factory=list)
    excursion_metrics: list = field(default_factory=list)


def value_area_class(zone_low, zone_high, area) -> str:
    """INSIDE_VALUE, VALUE_EDGE when overlapping VAL or VAH, else OUTSIDE_VALUE."""
    if area is None:
        return OUTSIDE_VALUE
    val, vah = area.low_price, area.high_price
    if zone_low < val < zone_high or zone_low < vah < zone_high:
        return VALUE_EDGE
    if val <= zone_low and zone_high <= vah:
        return INSIDE_VALUE
    return OUTSIDE_VALUE


def first_interaction(zone, bars: tuple[Bar, ...]):
    """First eligible touch, classified from information up to that bar's close."""
    previous_close = None
    for index, bar in enumerate(bars):
        if zone.touched_by(bar.low, bar.high):
            if previous_close is None or zone.contains(previous_close):
                approach = START_INSIDE
            elif previous_close < zone.atomic_low:
                approach = APPROACH_FROM_BELOW
            else:
                approach = APPROACH_FROM_ABOVE
            if zone.contains(bar.close):
                touch = CLOSE_INSIDE
            elif approach == APPROACH_FROM_BELOW and bar.close >= zone.atomic_high:
                touch = CROSS_THROUGH
            elif approach == APPROACH_FROM_ABOVE and bar.close < zone.atomic_low:
                touch = CROSS_THROUGH
            else:
                touch = WICK_ONLY_SAME_SIDE
            return index, bar, approach, touch
        previous_close = bar.close
    return None, None, None, None


def _emit(
    zone,
    *,
    kind: str,
    control_family: str,
    context: dict,
    interaction_bars: tuple[Bar, ...],
    atr: Decimal,
    result: Gen3YearResult,
) -> None:
    """Opportunity row always; event and outcome rows only when touched."""
    index, touch_bar, approach, touch_class = first_interaction(zone, interaction_bars)
    zone_id = zone.atomic_id
    base = dict(context) | {
        "zone_id": zone_id,
        "zone_kind": kind,
        "control_family": control_family,
        "zone_low": zone.atomic_low,
        "zone_high": zone.atomic_high,
        "zone_width_points": zone.atomic_high - zone.atomic_low,
        "zone_width_atr": (zone.atomic_high - zone.atomic_low) / atr if atr > 0 else None,
    }
    opportunity = base | {
        "touched": index is not None,
        "touch_time": touch_bar.close_time if touch_bar else None,
        "minutes_to_touch": index + 1 if index is not None else None,
        "approach_side": approach,
        "touch_class": touch_class,
    }
    (result.node_opportunities if kind == "NODE" else result.control_opportunities).append(
        opportunity
    )
    if index is None or atr <= 0:
        return

    event_id = f"{'NE' if kind == 'NODE' else 'CE'}-{zone_id}"
    pre = interaction_bars[max(0, index - PRE_TOUCH_WINDOW) : index]
    forward = interaction_bars[index + 1 : index + 1 + MAX_FORWARD]
    low, high = zone.atomic_low, zone.atomic_high

    event = base | {
        "event_id": event_id,
        "touch_time": touch_bar.close_time,
        "touch_bar_id": touch_bar.source_row_id,
        "approach_side": approach,
        "touch_class": touch_class,
        "atr_at_touch": atr,
        "minute_from_interaction_start": index,
        "forward_bars_available": len(forward),
        "touch_bar_range_ratio": (touch_bar.high - touch_bar.low) / atr,
        "touch_bar_node_overlap_share": (
            (min(touch_bar.high, high) - max(touch_bar.low, low))
            / (touch_bar.high - touch_bar.low)
            if touch_bar.high > touch_bar.low
            else (Decimal(1) if low <= touch_bar.low < high else Decimal(0))
        ),
    }
    (result.node_events if kind == "NODE" else result.control_events).append(event)

    shared = {"event_id": event_id, "zone_kind": kind, "control_family": control_family}
    accept = {r.horizon: r for r in acceptance_metrics(forward, low, high)}
    reside = {r.horizon: r for r in residence_metrics(forward, low, high, atr)}
    rates = {r.horizon: r for r in market_rate_metrics(forward, pre)}
    for horizon in HORIZONS:
        a, s, m = accept[horizon], reside[horizon], rates[horizon]
        result.forward_metrics.append(
            shared | {
                "horizon": horizon,
                "horizon_complete": a.complete,
                "bars_observed": a.bars_observed,
                "inside_close_share": a.inside_close_share,
                "mean_range_overlap_share": a.mean_range_overlap_share,
                "first_inside_close_minute": a.first_inside_close_minute,
                "midpoint_crossings": a.midpoint_crossings,
                "full_rotation_count": a.full_rotation_count,
                "any_rotation": a.any_rotation,
                "close_path_efficiency": a.close_path_efficiency,
                "inside_residence_minutes": s.inside_residence_minutes,
                "continuous_residence": s.continuous_residence_after_first_inside_close,
                "longest_inside_run": s.longest_inside_close_run,
                "local_band_occupancy_share": s.local_band_occupancy_share,
                "reentry_count": s.reentry_count,
                "normalized_residence": s.normalized_residence,
                "market_volume_rate_ratio": m.volume_rate_ratio,
                "market_range_rate_ratio": m.range_rate_ratio,
                "market_rate_undefined_reason": m.undefined_reason,
            }
        )

    width = high - low
    for name, band_low, band_high in (
        ("atr", low - atr, high + atr),
        ("width", low - 2 * width, high + 2 * width),
    ):
        for row in activity_metrics(forward, low, high, band_low, band_high,
                                    band_name=name):
            result.activity_metrics.append(
                shared | {
                    "horizon": row.horizon,
                    "band": row.band,
                    "node_volume": row.node_volume,
                    "band_volume": row.band_volume,
                    "node_tpo": row.node_tpo,
                    "band_tpo": row.band_tpo,
                    "bars_touching_node": row.bars_touching_node,
                    "bars_touching_band": row.bars_touching_band,
                    "node_touch_bar_share": row.node_touch_bar_share,
                    "node_volume_capture_share": row.node_volume_capture_share,
                    "node_tpo_capture_share": row.node_tpo_capture_share,
                    "node_width_share": row.node_width_share,
                    "volume_concentration_ratio": row.volume_concentration_ratio,
                    "tpo_concentration_ratio": row.tpo_concentration_ratio,
                    "activity_concentration_ratio": row.activity_concentration_ratio,
                    "undefined_reason": row.undefined_reason,
                }
            )

    departure = confirmed_departure(forward, low, high, approach)
    result.departure_metrics.append(
        shared | {
            "departed": departure.departed,
            "side": departure.side,
            "minutes_to_departure": departure.minutes_to_departure,
            "departure_class": departure.departure_class,
        }
    )
    for row in excursion_metrics(forward, low, high, atr, departure):
        result.excursion_metrics.append(
            shared | {
                "horizon": row.horizon,
                "horizon_complete": row.complete,
                "bars_observed": row.bars_observed,
                "departure_class": departure.departure_class,
                "directional_excursion_points": row.directional_excursion_points,
                "adverse_excursion_points": row.adverse_excursion_points,
                "directional_excursion_atr": row.directional_excursion_atr,
                "adverse_excursion_atr": row.adverse_excursion_atr,
                "directional_excursion_widths": row.directional_excursion_widths,
                "adverse_excursion_widths": row.adverse_excursion_widths,
                "reentered": row.reentered,
                "minutes_to_reentry": row.minutes_to_reentry,
            }
        )


def run_gen3_year(bars: tuple[Bar, ...], *, year: int, code_sha: str) -> Gen3YearResult:
    dates = trading_dates(bars)
    by_symbol = {
        s: tuple(b for b in bars if b.symbol == s)
        for s in sorted({b.symbol for b in bars})
    }
    atrs = {s: AtrSelector(wilder_atr(v)) for s, v in by_symbol.items()}
    selector = ContractSelector(by_symbol)
    result = Gen3YearResult()

    for position, current in enumerate(dates):
        if position == 0:
            continue
        prior = dates[position - 1]
        for relationship in Relationship:
            family = FAMILY_BY_RELATIONSHIP[relationship]
            source_date = prior if family.value == "prior_rth" else current
            pwindow = profile_window(family, source_date)
            iwindow = relationship_window(
                relationship, source_date=prior, interaction_date=current
            )
            try:
                symbol = selector.choose(pwindow.source_start)
            except ValueError:
                continue
            selected = by_symbol[symbol]
            source = sorted(
                [b for b in selected
                 if pwindow.source_start <= b.start_time < pwindow.source_end],
                key=lambda b: b.close_time,
            )
            if not _consecutive(source, EXPECTED_SOURCE_MINUTES[family]):
                continue
            interaction_bars = tuple(
                b for b in selected if iwindow.start <= b.start_time < iwindow.end
            )
            if not interaction_bars:
                continue
            atr_point = atrs[symbol].before(pwindow.source_start)

            for ratio in RATIOS:
                built = {}
                for method in AllocationMethod:
                    try:
                        built[method] = construct_profile(
                            source, (atr_point,), pwindow, method, ratio,
                            code_sha=code_sha, data_partition=f"development_{year}",
                        )
                    except ValueError:
                        built = {}
                        break
                if not built:
                    continue
                volume_profile = built[AllocationMethod.UNIFORM_VOLUME]
                tpo_profile = built[AllocationMethod.TPO]
                tpo_by_index = {b.bin_index: b.profile_weight for b in tpo_profile.bins}
                norm = profile_normalization(volume_profile, tpo_by_index)
                if not norm.valid:
                    continue
                bins_by_index = {b.bin_index: b for b in volume_profile.bins}
                v_area = value_area(
                    {b.bin_index: b.profile_weight for b in volume_profile.bins},
                    bins_by_index, norm.v_total,
                )
                t_area = value_area(tpo_by_index, bins_by_index, norm.t_total)
                nodes, _ = classify_final_nodes(volume_profile, tpo_by_index)
                atr = volume_profile.atr_value

                context = {
                    "profile_id": volume_profile.profile_id,
                    "relationship_id": relationship.value,
                    "family": family.value,
                    "session_date": current,
                    "contract": symbol,
                    "bin_ratio": ratio,
                    "year": year,
                    "code_sha": code_sha,
                }
                for node in nodes:
                    if not node.accepted:
                        continue
                    node_context = context | {
                        "node_class": node.node_class,
                        "geometry": node.geometry,
                        "width_bins": node.width_bins,
                        "zone_volume_density_ratio": node.zone_volume_density_ratio,
                        "zone_tpo_density_ratio": node.zone_tpo_density_ratio,
                        "zone_activity_density_ratio": node.zone_activity_density_ratio,
                        "activity_percentile": node.activity_percentile,
                        "local_activity_prominence": node.local_activity_prominence,
                        "value_area_class": value_area_class(
                            node.zone_low, node.zone_high, v_area
                        ),
                        "tpo_value_area_class": value_area_class(
                            node.zone_low, node.zone_high, t_area
                        ),
                        "distance_to_volume_poc_atr": (
                            abs(node.peak_price - v_area.poc_price) / atr
                            if v_area else None
                        ),
                    }
                    _emit(node, kind="NODE", control_family="", context=node_context,
                          interaction_bars=interaction_bars, atr=atr, result=result)

                    taken: set = set()
                    for control in select_composite_controls(
                        volume_profile, tpo_by_index, nodes, node, taken=taken
                    ):
                        taken |= set(range(control.start_bin_index,
                                           control.end_bin_index + 1))
                        control_context = context | {
                            "node_class": node.node_class,
                            "matched_node_id": control.matched_node_id,
                            "width_bins": control.width_bins,
                            "zone_volume_density_ratio":
                                control.zone_volume_density_ratio,
                            "zone_tpo_density_ratio": control.zone_tpo_density_ratio,
                            "zone_activity_density_ratio":
                                control.zone_activity_density_ratio,
                            "value_area_class": value_area_class(
                                control.control_low, control.control_high, v_area
                            ),
                            "distance_to_volume_poc_atr": (
                                abs(control.control_center - v_area.poc_price) / atr
                                if v_area else None
                            ),
                        }
                        _emit(control, kind="CONTROL",
                              control_family=control.control_family,
                              context=control_context,
                              interaction_bars=interaction_bars, atr=atr,
                              result=result)
    return result


LEDGERS = (
    ("node_opportunities", "node_opportunities", ("zone_id",)),
    ("node_events", "node_events", ("event_id",)),
    ("control_opportunities", "control_opportunities", ("zone_id",)),
    ("control_events", "control_events", ("event_id",)),
    ("forward_metrics", "forward_metrics", ("event_id", "horizon")),
    ("activity_metrics", "activity_metrics", ("event_id", "band", "horizon")),
    ("departure_metrics", "departure_metrics", ("event_id",)),
    ("excursion_metrics", "excursion_metrics", ("event_id", "horizon")),
)


def write_gen3_year(result: Gen3YearResult, output: Path, *, year: int) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, attribute, sort_fields in LEDGERS:
        rows = getattr(result, attribute)
        fields = (
            tuple(sorted({k for r in rows for k in r})) if rows else ("record_id",)
        )
        write_deterministic_gzip_csv(
            output / f"{name}_{year}.csv.gz", rows, fields,
            sort_by=tuple(f for f in sort_fields if f in fields),
        )
