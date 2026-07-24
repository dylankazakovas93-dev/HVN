from __future__ import annotations

import hashlib
from bisect import bisect_left
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from .acceptance_metrics import horizon_metrics, residence_metrics
from .atr import atr_before, wilder_atr
from .control_zones import mass_matched_controls, neutral_controls
from .engine import construct_profile
from .episode_clustering import EpisodeEvent, cluster_episodes
from .hvn import extract_hvns
from .interactions import (
    ApproachSide,
    Relationship,
    Zone,
    complete_forward_bars,
    find_first_interaction,
    pre_touch_features,
    price_to_ticks,
    relationship_window,
)
from .matching import MatchEvent, primary_cross_session_match, secondary_same_session_match
from .models import AllocationMethod, Bar, ProfileFamily
from .sessions import profile_window
from .stage02_ledger import write_deterministic_gzip_csv

RATIOS = (Decimal("0.05"), Decimal("0.10"), Decimal("0.20"))
PROMINENCES = (Decimal("1.5"), Decimal("2.0"), Decimal("2.5"))
HORIZONS = (15, 30, 60, 120)
EXPECTED_SOURCE_MINUTES = {
    ProfileFamily.PRIOR_RTH: 390,
    ProfileFamily.FULL_OVERNIGHT: 930,
    ProfileFamily.MIDNIGHT: 570,
    ProfileFamily.OPENING_HOUR: 60,
}
FAMILY_BY_RELATIONSHIP = {
    Relationship.PRIOR_RTH_TO_ETH: ProfileFamily.PRIOR_RTH,
    Relationship.PRIOR_RTH_TO_RTH: ProfileFamily.PRIOR_RTH,
    Relationship.OVERNIGHT_TO_RTH: ProfileFamily.FULL_OVERNIGHT,
    Relationship.MIDNIGHT_TO_RTH: ProfileFamily.MIDNIGHT,
    Relationship.OPENING_HOUR_TO_RTH: ProfileFamily.OPENING_HOUR,
}


@dataclass(slots=True)
class YearResult:
    profile_rows: list[dict]
    opportunity_rows: list[dict]
    event_rows: list[dict]
    control_opportunity_rows: list[dict]
    control_event_rows: list[dict]
    metric_rows: list[dict]
    match_events: list[MatchEvent]
    episode_events: list[EpisodeEvent]


def choose_contract(bars: tuple[Bar, ...], source_start: datetime) -> str:
    volumes: dict[str, Decimal] = defaultdict(Decimal)
    lower = source_start - timedelta(hours=72)
    for bar in bars:
        if lower <= bar.start_time < source_start:
            volumes[bar.symbol] += bar.volume
    if not volumes:
        raise ValueError("no causal contract-selection history")
    return min(volumes, key=lambda symbol: (-volumes[symbol], symbol))


class ContractSelector:
    def __init__(self, bars_by_symbol: dict[str, tuple[Bar, ...]]) -> None:
        self._times = {
            symbol: tuple(bar.start_time for bar in bars)
            for symbol, bars in bars_by_symbol.items()
        }
        self._prefix = {}
        for symbol, bars in bars_by_symbol.items():
            running = [Decimal(0)]
            for bar in bars:
                running.append(running[-1] + bar.volume)
            self._prefix[symbol] = tuple(running)

    def choose(self, source_start: datetime) -> str:
        lower = source_start - timedelta(hours=72)
        volumes = {}
        for symbol, times in self._times.items():
            left = bisect_left(times, lower)
            right = bisect_left(times, source_start)
            volume = self._prefix[symbol][right] - self._prefix[symbol][left]
            if volume:
                volumes[symbol] = volume
        if not volumes:
            raise ValueError("no causal contract-selection history")
        return min(volumes, key=lambda symbol: (-volumes[symbol], symbol))


def trading_dates(bars: tuple[Bar, ...]) -> tuple[date, ...]:
    counts: dict[tuple[date, str], int] = defaultdict(int)
    for bar in bars:
        local = bar.start_time
        if (local.hour, local.minute) >= (9, 30) and (local.hour, local.minute) < (16, 0):
            counts[(local.date(), bar.symbol)] += 1
    return tuple(
        sorted(
            day
            for day in {day for day, _ in counts}
            if max(count for (candidate, _), count in counts.items() if candidate == day) >= 300
        )
    )


def _consecutive(bars: list[Bar], expected: int) -> bool:
    if len(bars) != expected:
        return False
    return all(
        bars[index].close_time == bars[index + 1].start_time
        for index in range(len(bars) - 1)
    )


def _config_hash(
    relationship: Relationship,
    method: AllocationMethod,
    ratio: Decimal,
    prominence: Decimal,
) -> str:
    return hashlib.sha256(
        f"AMD01|{relationship.value}|{method.value}|{ratio}|{prominence}".encode()
    ).hexdigest()[:20]


def _metric_rows(
    *,
    event_id: str,
    opportunity_id: str,
    zone_type: str,
    control_family: str,
    profile,
    relationship: Relationship,
    session_date: date,
    zone: Zone,
    interaction,
    features,
    interaction_bars,
    code_sha: str,
) -> list[dict]:
    rows = []
    complete_120, reason_120 = complete_forward_bars(
        interaction_bars,
        touch_bar=interaction.bar,
        window=relationship_window(
            relationship,
            source_date=profile.window.source_start.date(),
            interaction_date=session_date,
        ),
        horizon=120,
    )
    residence = (
        residence_metrics(
            complete_120,
            zone,
            atr_at_touch=features.atr_1m_at_touch,
            complete_followup_minutes=len(complete_120),
        )
        if complete_120
        else None
    )
    for horizon in HORIZONS:
        forward, reason = complete_forward_bars(
            interaction_bars,
            touch_bar=interaction.bar,
            window=relationship_window(
                relationship,
                source_date=profile.window.source_start.date(),
                interaction_date=session_date,
            ),
            horizon=horizon,
        )
        metrics = horizon_metrics(interaction.bar, forward, zone) if forward else None
        rows.append(
            {
                "event_id": event_id,
                "opportunity_id": opportunity_id,
                "zone_type": zone_type,
                "control_family": control_family,
                "profile_id": profile.profile_id,
                "relationship_id": relationship.value,
                "session_date": session_date,
                "year": session_date.year,
                "contract": interaction.bar.symbol,
                "allocation_method": profile.allocation_method.value,
                "bin_ratio": profile.bin_ratio,
                "prominence_threshold": "",
                "zone_low": zone.low,
                "zone_high": zone.high,
                "zone_width_points": zone.high - zone.low,
                "zone_width_atr": features.zone_width_atr,
                "touch_time": interaction.event_time,
                "touch_class": interaction.touch_class.value,
                "approach_side": interaction.approach_side.value,
                "forward_horizon": horizon,
                "horizon_complete": bool(forward),
                "censor_reason": reason,
                "inside_close_share": metrics.inside_close_share if metrics else None,
                "mean_overlap_share": metrics.mean_overlap_share if metrics else None,
                "midpoint_crossings": metrics.midpoint_crossings if metrics else None,
                "path_efficiency": metrics.path_efficiency if metrics else None,
                "first_inside_close_5": metrics.first_inside_close_5 if metrics else None,
                "first_inside_close_15": metrics.first_inside_close_15 if metrics else None,
                "continuous_residence_minutes": residence.continuous_residence_minutes if residence else None,
                "continuous_residence_normalized": residence.continuous_residence_normalized if residence else None,
                "residence_censored": residence.residence_censored if residence else bool(reason_120),
                "first_full_exit_time": (
                    complete_120[residence.first_full_exit_index].close_time
                    if residence and residence.first_full_exit_index is not None
                    else None
                ),
                "first_full_exit_side": residence.first_full_exit_side if residence else None,
                "reentry_15": residence.reentry_15 if residence else None,
                "reentry_30": residence.reentry_30 if residence else None,
                "reentry_60": residence.reentry_60 if residence else None,
                "source_row_ids_or_range": "|".join(bar.source_row_id for bar in forward),
                "config_hash": "",
                "code_sha": code_sha,
            }
        )
    return rows


def run_year(bars: tuple[Bar, ...], *, year: int, code_sha: str) -> YearResult:
    dates = trading_dates(bars)
    bars_by_symbol = {
        symbol: tuple(bar for bar in bars if bar.symbol == symbol)
        for symbol in sorted({bar.symbol for bar in bars})
    }
    atr_by_symbol = {
        symbol: wilder_atr(symbol_bars)
        for symbol, symbol_bars in bars_by_symbol.items()
    }
    selector = ContractSelector(bars_by_symbol)
    result = YearResult([], [], [], [], [], [], [], [])
    seen_controls: set[tuple[str, str, str]] = set()
    seen_control_events: set[tuple[str, str, str]] = set()

    for position, current_date in enumerate(dates):
        if position == 0:
            continue
        prior_date = dates[position - 1]
        for relationship in Relationship:
            family = FAMILY_BY_RELATIONSHIP[relationship]
            source_date = prior_date if family == ProfileFamily.PRIOR_RTH else current_date
            pwindow = profile_window(family, source_date)
            iwindow = relationship_window(
                relationship, source_date=prior_date, interaction_date=current_date
            )
            try:
                symbol = selector.choose(pwindow.source_start)
                interaction_symbol = selector.choose(iwindow.start)
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
            context_bars = tuple(
                bar
                for bar in selected_all
                if iwindow.start - timedelta(minutes=30)
                <= bar.start_time
                < iwindow.end
            )
            prior_eth_bars = (
                tuple(
                    bar
                    for bar in selected_all
                    if relationship == Relationship.PRIOR_RTH_TO_RTH
                    and relationship_window(
                        Relationship.PRIOR_RTH_TO_ETH,
                        source_date=prior_date,
                        interaction_date=current_date,
                    ).start
                    <= bar.start_time
                    < relationship_window(
                        Relationship.PRIOR_RTH_TO_ETH,
                        source_date=prior_date,
                        interaction_date=current_date,
                    ).end
                )
                if relationship == Relationship.PRIOR_RTH_TO_RTH
                else ()
            )
            contract_transition = interaction_symbol != symbol
            for method in AllocationMethod:
                for ratio in RATIOS:
                    try:
                        profile = construct_profile(
                            source,
                            atr_by_symbol[symbol],
                            pwindow,
                            method,
                            ratio,
                            code_sha=code_sha,
                            data_partition=f"development_{year}",
                        )
                    except ValueError:
                        continue
                    poc = next(
                        bin_.bin_center
                        for bin_ in profile.bins
                        if bin_.bin_index == profile.poc_bin_index
                    )
                    result.profile_rows.append(
                        {
                            "profile_id": profile.profile_id,
                            "relationship_id": relationship.value,
                            "family": family.value,
                            "session_date": current_date,
                            "contract": symbol,
                            "method": method.value,
                            "ratio": ratio,
                            "source_bar_count": len(source),
                        }
                    )
                    for prominence in PROMINENCES:
                        candidates, nodes = extract_hvns(profile, prominence)
                        config_hash = _config_hash(relationship, method, ratio, prominence)
                        for node in nodes:
                            opportunity_id = (
                                f"O-{relationship.value}-{current_date}-{profile.profile_id}-"
                                f"{prominence}-{node.hvn_id}"
                            )
                            zone = Zone(
                                node.hvn_id,
                                price_to_ticks(node.hvn_low),
                                price_to_ticks(node.hvn_high),
                            )
                            interaction = (
                                find_first_interaction(
                                    interaction_bars,
                                    zone,
                                    iwindow,
                                    source_contract=symbol,
                                    prior_eth_bars=prior_eth_bars,
                                )
                                if not contract_transition
                                else None
                            )
                            row = {
                                "opportunity_id": opportunity_id,
                                "profile_id": profile.profile_id,
                                "node_id": node.hvn_id,
                                "relationship_id": relationship.value,
                                "allocation_method": method.value,
                                "bin_ratio": ratio,
                                "prominence_threshold": prominence,
                                "source_contract": symbol,
                                "source_session_date": source_date,
                                "source_start": pwindow.source_start,
                                "source_end": pwindow.source_end,
                                "profile_freeze_time": pwindow.freeze_time,
                                "interaction_start": iwindow.start,
                                "interaction_end": iwindow.end,
                                "hvn_low": node.hvn_low,
                                "hvn_high": node.hvn_high,
                                "hvn_center": node.hvn_center,
                                "hvn_width_points": node.hvn_width,
                                "hvn_width_bins": node.node_bin_count,
                                "hvn_width_atr": node.hvn_width / profile.atr_value,
                                "peak_weight": node.peak_weight,
                                "local_baseline": node.local_baseline,
                                "prominence_ratio": node.prominence_ratio,
                                "node_weight": node.node_total_weight,
                                "node_weight_share": node.node_weight_share,
                                "poc_distance_points": abs(node.hvn_center - poc),
                                "poc_distance_atr": abs(node.hvn_center - poc) / profile.atr_value,
                                "eligible": not contract_transition and bool(interaction and interaction.eligible),
                                "exclusion_reason": "CONTRACT_TRANSITION" if contract_transition else (
                                    interaction.exclusion_reason if interaction else ""
                                ),
                                "touched": bool(interaction and interaction.touched),
                                "first_touch_bar_id": interaction.bar.source_row_id if interaction and interaction.bar else "",
                                "first_touch_time": interaction.event_time if interaction else None,
                                "touch_class": interaction.touch_class.value if interaction and interaction.touch_class else "",
                                "approach_side": interaction.approach_side.value if interaction and interaction.approach_side else "",
                                "touched_during_prior_eth": interaction.touched_during_prior_eth if interaction else None,
                                "data_year": year,
                                "config_hash": config_hash,
                                "code_sha": code_sha,
                            }
                            result.opportunity_rows.append(row)
                            if interaction and interaction.touched and interaction.bar:
                                event_id = "E-" + hashlib.sha256(opportunity_id.encode()).hexdigest()[:20]
                                try:
                                    atr_point = atr_before(
                                        atr_by_symbol[symbol], interaction.event_time
                                    )
                                    features = pre_touch_features(
                                        context_bars,
                                        touch_bar=interaction.bar,
                                        zone=zone,
                                        window=iwindow,
                                        interaction_open=interaction_bars[0].open,
                                        atr_at_touch=atr_point.value,
                                        source_profile_low=profile.profile_range_low,
                                        source_profile_high=profile.profile_range_high,
                                        poc_price=poc,
                                        profile_freeze_time=pwindow.freeze_time,
                                        approach_side=interaction.approach_side,
                                        touch_class=interaction.touch_class,
                                        prior_eth_touch_flag=interaction.touched_during_prior_eth,
                                    )
                                except (ValueError, IndexError):
                                    continue
                                event_row = asdict(features) | {
                                    "event_id": event_id,
                                    "opportunity_id": opportunity_id,
                                    "profile_id": profile.profile_id,
                                    "node_id": node.hvn_id,
                                    "relationship_id": relationship.value,
                                    "session_date": current_date,
                                    "year": year,
                                    "contract": symbol,
                                    "allocation_method": method.value,
                                    "bin_ratio": ratio,
                                    "prominence_threshold": prominence,
                                    "zone_low": node.hvn_low,
                                    "zone_high": node.hvn_high,
                                    "zone_width_bins": node.node_bin_count,
                                    "config_hash": config_hash,
                                    "code_sha": code_sha,
                                }
                                result.event_rows.append(event_row)
                                metric_rows = _metric_rows(
                                    event_id=event_id,
                                    opportunity_id=opportunity_id,
                                    zone_type="HVN",
                                    control_family="",
                                    profile=profile,
                                    relationship=relationship,
                                    session_date=current_date,
                                    zone=zone,
                                    interaction=interaction,
                                    features=features,
                                    interaction_bars=interaction_bars,
                                    code_sha=code_sha,
                                )
                                for metric_row in metric_rows:
                                    metric_row["prominence_threshold"] = prominence
                                    metric_row["config_hash"] = config_hash
                                result.metric_rows.extend(metric_rows)
                                if interaction.approach_side != ApproachSide.START_INSIDE:
                                    result.match_events.append(
                                        MatchEvent(
                                            event_id,
                                            profile.profile_id,
                                            node.hvn_id,
                                            current_date,
                                            relationship.value,
                                            method.value,
                                            ratio,
                                            prominence,
                                            year,
                                            interaction.approach_side.value,
                                            node.node_bin_count,
                                            features.minute_from_interaction_start,
                                            interaction.event_time,
                                            features.atr_1m_at_touch,
                                            features.absolute_15m_pre_touch_displacement_atr or Decimal(0),
                                            features.pre_touch_15m_close_path_efficiency or Decimal(0),
                                            features.distance_from_interaction_open_to_zone_center_atr,
                                            features.zone_distance_from_poc_atr,
                                            zone.low_ticks,
                                            zone.high_ticks,
                                        )
                                    )
                                    result.episode_events.append(
                                        EpisodeEvent(
                                            event_id,
                                            symbol,
                                            relationship.value,
                                            current_date,
                                            interaction.event_time,
                                            zone.low_ticks,
                                            zone.high_ticks,
                                            interaction.approach_side.value,
                                        )
                                    )

                            for family_name, controls in (
                                (
                                    "C01",
                                    neutral_controls(
                                        profile, nodes, width_bins=node.node_bin_count
                                    ),
                                ),
                                (
                                    "C02",
                                    mass_matched_controls(
                                        profile,
                                        nodes,
                                        candidates,
                                        treated=node,
                                        width_bins=node.node_bin_count,
                                    ),
                                ),
                            ):
                                for control in controls:
                                    control_key = (
                                        relationship.value,
                                        str(prominence),
                                        control.control_zone_id,
                                    )
                                    if control_key not in seen_controls:
                                        seen_controls.add(control_key)
                                        result.control_opportunity_rows.append(
                                            asdict(control)
                                            | {
                                                "relationship_id": relationship.value,
                                                "profile_id": profile.profile_id,
                                                "session_date": current_date,
                                                "year": year,
                                                "prominence_threshold": prominence,
                                                "touched": False,
                                            }
                                        )
                                    czone = Zone(
                                        control.control_zone_id,
                                        price_to_ticks(control.low),
                                        price_to_ticks(control.high),
                                    )
                                    ci = find_first_interaction(
                                        interaction_bars,
                                        czone,
                                        iwindow,
                                        source_contract=symbol,
                                    )
                                    if not ci.touched or not ci.bar:
                                        continue
                                    control_event_key = (
                                        relationship.value,
                                        str(prominence),
                                        control.control_zone_id,
                                    )
                                    if control_event_key in seen_control_events:
                                        continue
                                    seen_control_events.add(control_event_key)
                                    ceid = "CE-" + hashlib.sha256(
                                        "|".join(control_event_key).encode()
                                    ).hexdigest()[:20]
                                    atr_point = atr_before(atr_by_symbol[symbol], ci.event_time)
                                    cf = pre_touch_features(
                                        context_bars,
                                        touch_bar=ci.bar,
                                        zone=czone,
                                        window=iwindow,
                                        interaction_open=interaction_bars[0].open,
                                        atr_at_touch=atr_point.value,
                                        source_profile_low=profile.profile_range_low,
                                        source_profile_high=profile.profile_range_high,
                                        poc_price=poc,
                                        profile_freeze_time=pwindow.freeze_time,
                                        approach_side=ci.approach_side,
                                        touch_class=ci.touch_class,
                                        prior_eth_touch_flag=ci.touched_during_prior_eth,
                                    )
                                    result.control_event_rows.append(
                                        asdict(cf)
                                        | asdict(control)
                                        | {
                                            "event_id": ceid,
                                            "relationship_id": relationship.value,
                                            "profile_id": profile.profile_id,
                                            "session_date": current_date,
                                            "year": year,
                                            "allocation_method": method.value,
                                            "bin_ratio": ratio,
                                            "prominence_threshold": prominence,
                                        }
                                    )
                                    control_metrics = _metric_rows(
                                        event_id=ceid,
                                        opportunity_id=control.control_zone_id,
                                        zone_type="CONTROL",
                                        control_family=family_name,
                                        profile=profile,
                                        relationship=relationship,
                                        session_date=current_date,
                                        zone=czone,
                                        interaction=ci,
                                        features=cf,
                                        interaction_bars=interaction_bars,
                                        code_sha=code_sha,
                                    )
                                    for metric_row in control_metrics:
                                        metric_row["prominence_threshold"] = prominence
                                        metric_row["config_hash"] = config_hash
                                    result.metric_rows.extend(control_metrics)
                                    if ci.approach_side != ApproachSide.START_INSIDE:
                                        result.match_events.append(
                                            MatchEvent(
                                                ceid,
                                                profile.profile_id,
                                                control.control_zone_id,
                                                current_date,
                                                relationship.value,
                                                method.value,
                                                ratio,
                                                prominence,
                                                year,
                                                ci.approach_side.value,
                                                control.width_bins,
                                                cf.minute_from_interaction_start,
                                                ci.event_time,
                                                cf.atr_1m_at_touch,
                                                cf.absolute_15m_pre_touch_displacement_atr or Decimal(0),
                                                cf.pre_touch_15m_close_path_efficiency or Decimal(0),
                                                cf.distance_from_interaction_open_to_zone_center_atr,
                                                cf.zone_distance_from_poc_atr,
                                                czone.low_ticks,
                                                czone.high_ticks,
                                            )
                                        )
    return result


def match_all(
    match_events: list[MatchEvent],
) -> tuple[list, list, dict[str, str]]:
    episode_ids = cluster_episodes([])  # explicit empty-safe initialization
    treated = [event for event in match_events if event.event_id.startswith("E-")]
    controls = [event for event in match_events if event.event_id.startswith("CE-")]
    primary = []
    secondary = []
    unmatched = {}
    for family in ("C01", "C02"):
        family_controls = [
            event for event in controls if f"-{family}-" in event.node_id
        ]
        pairs, missing = primary_cross_session_match(
            treated, family_controls, control_family=family
        )
        primary.extend(pairs)
        unmatched.update(missing)
        pairs, _ = secondary_same_session_match(
            treated, family_controls, control_family=family
        )
        secondary.extend(pairs)
    return primary, secondary, episode_ids


def write_year_result(result: YearResult, output: Path, *, year: int) -> None:
    output.mkdir(parents=True, exist_ok=True)
    match_event_rows = [asdict(event) for event in result.match_events]
    episode_event_rows = [asdict(event) for event in result.episode_events]
    for name, rows, sort_fields in (
        ("profiles", result.profile_rows, ("profile_id", "relationship_id")),
        ("opportunities", result.opportunity_rows, ("opportunity_id",)),
        ("events", result.event_rows, ("event_id",)),
        ("control_opportunities", result.control_opportunity_rows, ("control_zone_id",)),
        ("control_events", result.control_event_rows, ("event_id",)),
        ("forward_metrics", result.metric_rows, ("event_id", "forward_horizon")),
        ("match_events", match_event_rows, ("event_id",)),
        ("episode_events", episode_event_rows, ("event_id",)),
    ):
        fields = tuple(sorted({key for row in rows for key in row})) if rows else ("record_id",)
        write_deterministic_gzip_csv(
            output / f"{name}_{year}.csv.gz",
            rows,
            fields,
            sort_by=tuple(field for field in sort_fields if field in fields),
        )
