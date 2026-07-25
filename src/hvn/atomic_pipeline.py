"""Generation 3 atomic HVN development pipeline.

Mirrors the Stage 2 driver's session, contract and ATR machinery exactly, but
builds atomic peaks from `peak_candidates()` rather than the broad expanded and
merged nodes. Stage 1 profile construction is `engine.construct_profile()`,
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from .atomic import extract_atomic_hvns
from .atomic_controls import select_controls
from .atomic_departure import (
    EXCURSION_HORIZONS,
    confirmed_departure,
    excursion_metrics,
)
from .atomic_interactions import first_interaction
from .atomic_proximity import BANDS, HORIZONS, proximity_metrics
from .atomic_residence import residence_metrics
from .atr import wilder_atr
from .engine import construct_profile
from .interactions import Relationship, relationship_window
from .models import AllocationMethod, Bar
from .sessions import profile_window
from .stage02_ledger import write_deterministic_gzip_csv
from .stage02_pipeline import (
    EXPECTED_SOURCE_MINUTES,
    FAMILY_BY_RELATIONSHIP,
    PROMINENCES,
    RATIOS,
    AtrSelector,
    ContractSelector,
    _config_hash,
    _consecutive,
    trading_dates,
)

# Sensitivity departure definitions, alongside the primary two-close 0.25 band.
DEPARTURE_VARIANTS: tuple[tuple[str, Decimal, int], ...] = (
    ("primary_2close_025", Decimal("0.25"), 2),
    ("sens_1close_025", Decimal("0.25"), 1),
    ("sens_2close_010", Decimal("0.10"), 2),
    ("sens_2close_050", Decimal("0.50"), 2),
)
MAX_FORWARD_MINUTES = max(HORIZONS)


@dataclass
class AtomicYearResult:
    profile_rows: list = field(default_factory=list)
    opportunity_rows: list = field(default_factory=list)
    event_rows: list = field(default_factory=list)
    control_opportunity_rows: list = field(default_factory=list)
    control_event_rows: list = field(default_factory=list)
    proximity_rows: list = field(default_factory=list)
    residence_rows: list = field(default_factory=list)
    departure_rows: list = field(default_factory=list)
    excursion_rows: list = field(default_factory=list)


def _forward_bars(bars: tuple[Bar, ...], start_index: int) -> tuple[Bar, ...]:
    return bars[start_index : start_index + MAX_FORWARD_MINUTES]


def _zone_rows(
    zone,
    *,
    kind: str,
    family: str,
    context: dict,
    interaction_bars: tuple[Bar, ...],
    atr_selector: AtrSelector,
    result: AtomicYearResult,
) -> None:
    """Detect the first touch of one zone and emit all of its metric rows."""
    zone_id = getattr(zone, "atomic_id", None) or zone.control_id
    interaction = first_interaction(
        zone,
        interaction_bars,
        atr_value=(
            atr_selector.before(interaction_bars[0].start_time).value
            if interaction_bars
            else None
        ),
    )
    base = dict(context)
    base.update(
        {
            "zone_id": zone_id,
            "zone_kind": kind,
            "control_family": family,
            "zone_low": zone.atomic_low,
            "zone_high": zone.atomic_high,
            "zone_center": zone.peak_price,
            "zone_width_points": zone.atomic_high - zone.atomic_low,
            "zone_width_bins": zone.width_bins,
        }
    )
    opportunity = dict(base)
    opportunity.update(
        {
            "touched": interaction.touched,
            "touch_time": interaction.touch_time,
            "touch_class": interaction.touch_class,
            "approach_side": interaction.approach_side,
            "exclusion_reason": interaction.exclusion_reason,
        }
    )
    target = (
        result.opportunity_rows if kind == "ATOMIC" else result.control_opportunity_rows
    )
    target.append(opportunity)
    if not interaction.touched or interaction.atr_at_touch is None:
        return

    atr = interaction.atr_at_touch
    event = dict(base)
    event.update(
        {
            "event_id": f"{'AE' if kind == 'ATOMIC' else 'CE'}-{zone_id}",
            "touch_time": interaction.touch_time,
            "touch_bar_id": interaction.touch_bar_id,
            "touch_class": interaction.touch_class,
            "approach_side": interaction.approach_side,
            "atr_at_touch": atr,
            "minute_from_interaction_start": interaction.minute_from_interaction_start,
            "zone_width_atr": (zone.atomic_high - zone.atomic_low) / atr,
        }
    )
    events = result.event_rows if kind == "ATOMIC" else result.control_event_rows
    events.append(event)

    forward = _forward_bars(interaction_bars, interaction.forward_start_index)
    event_id = event["event_id"]

    for proximity in proximity_metrics(zone, forward, atr):
        row = {
            "event_id": event_id,
            "zone_kind": kind,
            "control_family": family,
            "horizon": proximity.horizon,
            "horizon_complete": proximity.complete,
            "bars_observed": proximity.bars_observed,
            "mean_distance_atr": proximity.mean_distance_atr,
            "median_distance_atr": proximity.median_distance_atr,
            "p75_distance_atr": proximity.p75_distance_atr,
            "p90_distance_atr": proximity.p90_distance_atr,
            "mean_peak_distance_atr": proximity.mean_peak_distance_atr,
            "peak_crossings": proximity.peak_crossings,
            "side_changes": proximity.side_changes,
            "close_path_efficiency": proximity.close_path_efficiency,
        }
        for name, _ in BANDS:
            row[f"close_share_{name}"] = proximity.close_share[name]
            row[f"range_overlap_{name}"] = proximity.range_overlap_share[name]
            row[f"revisit_{name}"] = proximity.revisit_after_leaving[name]
        result.proximity_rows.append(row)

    for residence in residence_metrics(zone, forward, atr):
        result.residence_rows.append(
            {
                "event_id": event_id,
                "zone_kind": kind,
                "control_family": family,
                "band": residence.band,
                "total_minutes": residence.total_minutes,
                "longest_run_minutes": residence.longest_run_minutes,
                "first_entry_minute": residence.first_entry_minute,
                "first_exit_minute": residence.first_exit_minute,
                "continuous_residence_minutes": residence.continuous_residence_minutes,
                "reentry_count": residence.reentry_count,
                "first_reentry_delay_minutes": residence.first_reentry_delay_minutes,
                "never_entered": residence.never_entered,
                "never_left": residence.never_left,
                "right_censored": residence.right_censored,
                "residence_bucket": residence.residence_bucket,
                "normalized_residence": residence.normalized_residence,
            }
        )

    primary_bucket = next(
        r.residence_bucket for r in residence_metrics(zone, forward, atr)
        if r.band == "b025"
    )
    for label, expansion, consecutive in DEPARTURE_VARIANTS:
        departure = confirmed_departure(
            zone, forward, atr, expansion=expansion, consecutive=consecutive
        )
        result.departure_rows.append(
            {
                "event_id": event_id,
                "zone_kind": kind,
                "control_family": family,
                "definition": label,
                "departed": departure.departed,
                "side": departure.side,
                "minutes_to_departure": departure.minutes_to_departure,
                "departed_boundary": departure.departed_boundary,
                "right_censored": departure.right_censored,
                "residence_bucket": primary_bucket,
            }
        )
        if label != "primary_2close_025":
            continue
        for excursion in excursion_metrics(zone, forward, atr, departure):
            row = {
                "event_id": event_id,
                "zone_kind": kind,
                "control_family": family,
                "residence_bucket": primary_bucket,
                "side": departure.side,
                "horizon": excursion.horizon,
                "horizon_complete": excursion.complete,
                "bars_observed": excursion.bars_observed,
                "directional_displacement_atr": excursion.directional_displacement_atr,
                "mfe_atr": excursion.mfe_atr,
                "mae_atr": excursion.mae_atr,
                "max_distance_from_peak_atr": excursion.max_distance_from_peak_atr,
                "average_speed_atr_per_minute": excursion.average_speed_atr_per_minute,
                "average_speed_points_per_minute": excursion.average_speed_points_per_minute,
                "max_rolling_5m_speed_atr_per_minute": excursion.max_rolling_5m_speed_atr_per_minute,
                "reclaimed_band": excursion.reclaimed_band,
                "revisited_exact_zone": excursion.revisited_exact_zone,
                "crossed_to_opposite_side": excursion.crossed_to_opposite_side,
            }
            for threshold, minutes in excursion.minutes_to_threshold.items():
                row[f"minutes_to_{threshold.replace('.', '')}atr"] = minutes
            result.excursion_rows.append(row)


def run_atomic_year(
    bars: tuple[Bar, ...], *, year: int, code_sha: str
) -> AtomicYearResult:
    dates = trading_dates(bars)
    bars_by_symbol = {
        symbol: tuple(bar for bar in bars if bar.symbol == symbol)
        for symbol in sorted({bar.symbol for bar in bars})
    }
    atr_selectors = {
        symbol: AtrSelector(wilder_atr(symbol_bars))
        for symbol, symbol_bars in bars_by_symbol.items()
    }
    selector = ContractSelector(bars_by_symbol)
    result = AtomicYearResult()

    for position, current_date in enumerate(dates):
        if position == 0:
            continue
        prior_date = dates[position - 1]
        for relationship in Relationship:
            family = FAMILY_BY_RELATIONSHIP[relationship]
            source_date = (
                prior_date if family.value == "prior_rth" else current_date
            )
            pwindow = profile_window(family, source_date)
            iwindow = relationship_window(
                relationship, source_date=prior_date, interaction_date=current_date
            )
            try:
                symbol = selector.choose(pwindow.source_start)
            except ValueError:
                continue
            selected_all = bars_by_symbol[symbol]
            source = sorted(
                [
                    bar
                    for bar in selected_all
                    if pwindow.source_start <= bar.start_time < pwindow.source_end
                ],
                key=lambda bar: bar.close_time,
            )
            if not _consecutive(source, EXPECTED_SOURCE_MINUTES[family]):
                continue
            interaction_bars = tuple(
                bar
                for bar in selected_all
                if iwindow.start <= bar.start_time < iwindow.end
            )
            if not interaction_bars:
                continue
            for method in AllocationMethod:
                for ratio in RATIOS:
                    try:
                        profile = construct_profile(
                            source,
                            (atr_selectors[symbol].before(pwindow.source_start),),
                            pwindow,
                            method,
                            ratio,
                            code_sha=code_sha,
                            data_partition=f"development_{year}",
                        )
                    except ValueError:
                        continue
                    result.profile_rows.append(
                        {
                            "profile_id": profile.profile_id,
                            "relationship_id": relationship.value,
                            "family": family.value,
                            "session_date": current_date,
                            "contract": symbol,
                            "method": method.value,
                            "ratio": ratio,
                            "bin_count": len(profile.bins),
                            "atr_value": profile.atr_value,
                            "source_bar_count": len(source),
                            "year": year,
                        }
                    )
                    for prominence in PROMINENCES:
                        atomics = extract_atomic_hvns(profile, prominence)
                        config_hash = _config_hash(
                            relationship, method, ratio, prominence
                        )
                        for atomic in atomics:
                            context = {
                                "profile_id": profile.profile_id,
                                "relationship_id": relationship.value,
                                "allocation_method": method.value,
                                "bin_ratio": ratio,
                                "prominence_threshold": prominence,
                                "session_date": current_date,
                                "contract": symbol,
                                "year": year,
                                "config_hash": config_hash,
                                "code_sha": code_sha,
                                "contains_poc": atomic.contains_poc,
                                "is_plateau": atomic.is_plateau,
                                "peak_weight": atomic.peak_weight,
                                "prominence_ratio": atomic.prominence_ratio,
                            }
                            _zone_rows(
                                atomic,
                                kind="ATOMIC",
                                family="",
                                context=context,
                                interaction_bars=interaction_bars,
                                atr_selector=atr_selectors[symbol],
                                result=result,
                            )
                            for control in select_controls(profile, atomic, atomics):
                                control_context = dict(context)
                                control_context["matched_atomic_id"] = (
                                    control.matched_atomic_id
                                )
                                control_context["peak_weight"] = control.window_weight
                                control_context["prominence_ratio"] = None
                                control_context["contains_poc"] = False
                                _zone_rows(
                                    control,
                                    kind="CONTROL",
                                    family=control.control_family,
                                    context=control_context,
                                    interaction_bars=interaction_bars,
                                    atr_selector=atr_selectors[symbol],
                                    result=result,
                                )
    return result


LEDGERS = (
    ("atomic_profiles", "profile_rows", ("profile_id",)),
    ("atomic_opportunities", "opportunity_rows", ("zone_id",)),
    ("atomic_events", "event_rows", ("event_id",)),
    ("control_opportunities", "control_opportunity_rows", ("zone_id",)),
    ("control_events", "control_event_rows", ("event_id",)),
    ("proximity_metrics", "proximity_rows", ("event_id", "horizon")),
    ("residence_metrics", "residence_rows", ("event_id", "band")),
    ("departures", "departure_rows", ("event_id", "definition")),
    ("departure_excursions", "excursion_rows", ("event_id", "horizon")),
)


def write_atomic_year(result: AtomicYearResult, output: Path, *, year: int) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, attribute, sort_fields in LEDGERS:
        rows = getattr(result, attribute)
        fields = (
            tuple(sorted({key for row in rows for key in row}))
            if rows
            else ("record_id",)
        )
        write_deterministic_gzip_csv(
            output / f"{name}_{year}.csv.gz",
            rows,
            fields,
            sort_by=tuple(f for f in sort_fields if f in fields),
        )
