from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import subprocess
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from hvn.episode_clustering import EpisodeEvent, cluster_episodes
from hvn.matching import (
    MatchEvent,
    _primary_lane_key,
    _width_terms,
    primary_cross_session_match,
    secondary_same_session_match,
    zone_width_atr,
)
from hvn.stage02_ledger import deterministic_csv_bytes, write_deterministic_gzip_csv
from hvn.stage02_statistics import (
    PairObservation,
    paired_summary,
    stable_grid,
    standardized_mean_difference,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "stage_02"
DETAIL = OUTPUT / "detailed"

# All five development partitions declared in PARTITIONS.json. Generation 1
# omitted 2019; see STAGE_02_AMENDMENT_02.md section 9 and D-016.
YEARS = (2019, 2021, 2023, 2025, 2026)
GENERATION = "generation_2"
AMENDMENT = "amendment_02"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse arguments. Reads no ledger, so --help exits without touching data."""
    parser = argparse.ArgumentParser(
        prog="aggregate_stage_02.py",
        description=(
            "Aggregate Stage 2 matching, statistics and gates from existing "
            "authoritative ledgers. Reads no market archive."
        ),
    )
    parser.add_argument("--generation", default=GENERATION)
    parser.add_argument("--amendment", default=AMENDMENT)
    parser.add_argument(
        "--input-root",
        type=Path,
        default=DETAIL,
        help="directory holding checkpoint_<year>.json and the year ledgers",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "outputs" / "stage_02_generation_2",
    )
    parser.add_argument(
        "--years",
        type=lambda value: tuple(int(part) for part in value.split(",")),
        default=YEARS,
    )
    # argparse already rejects unknown arguments; the partition guard is ours.
    args = parser.parse_args(argv)
    forbidden = sorted(set(args.years) & {2020, 2022, 2024})
    if forbidden:
        parser.error(f"forbidden partitions requested: {forbidden}")
    return args


def dec(value: str) -> Decimal:
    return Decimal(value)


def rows(name: str, year: int):
    with gzip.open(DETAIL / f"{name}_{year}.csv.gz", "rt", newline="") as stream:
        yield from csv.DictReader(stream)


def match_event(row: dict, *, episode_id: str = "") -> MatchEvent | None:
    if (
        row["approach_side"] == "START_INSIDE"
        or not row["absolute_15m_pre_touch_displacement_atr"]
        or not row["pre_touch_15m_close_path_efficiency"]
    ):
        return None
    low = row.get("zone_low", row.get("low"))
    high = row.get("zone_high", row.get("high"))
    width = row.get("zone_width_bins", row.get("width_bins"))
    node_id = row.get("node_id", row.get("control_zone_id"))
    return MatchEvent(
        row["event_id"],
        row["profile_id"],
        node_id,
        date.fromisoformat(row["session_date"]),
        row["relationship_id"],
        row["allocation_method"],
        dec(row["bin_ratio"]),
        dec(row["prominence_threshold"]),
        int(row["year"]),
        row["approach_side"],
        int(width),
        int(row["minute_from_interaction_start"]),
        datetime.fromisoformat(row["touch_time"]),
        dec(row["atr_1m_at_touch"]),
        dec(row["absolute_15m_pre_touch_displacement_atr"]),
        dec(row["pre_touch_15m_close_path_efficiency"]),
        dec(row["distance_from_interaction_open_to_zone_center_atr"]),
        dec(row["zone_distance_from_poc_atr"]),
        int(dec(low) / Decimal("0.25")),
        int(dec(high) / Decimal("0.25")),
        episode_id,
    )


def collapse_episodes(group: list[PairObservation]) -> list[PairObservation]:
    by_episode = defaultdict(list)
    for observation in group:
        by_episode[observation.economic_episode_id or observation.pair_id].append(
            observation
        )
    collapsed = []
    for episode_id, members in sorted(by_episode.items()):
        first = members[0]
        difference = sum(
            (member.difference for member in members), Decimal(0)
        ) / Decimal(len(members))
        collapsed.append(
            PairObservation(
                episode_id,
                first.match_design,
                first.relationship_id,
                first.control_family,
                first.allocation_method,
                first.bin_ratio,
                first.prominence_threshold,
                first.year,
                first.treated_session_date,
                first.control_session_date,
                episode_id,
                first.metric_name,
                difference,
                Decimal(0),
            )
        )
    return collapsed


def load() -> tuple[list[MatchEvent], dict[str, str], dict[str, dict], dict]:
    episode_events = []
    treated_rows = []
    control_rows = []
    metric_by_event: dict[str, dict] = defaultdict(
        lambda: {"complete": set(), "h30": None}
    )
    for year in YEARS:
        for row in rows("events", year):
            treated_rows.append(row)
            episode_events.append(
                EpisodeEvent(
                    row["event_id"],
                    row["contract"],
                    row["relationship_id"],
                    date.fromisoformat(row["session_date"]),
                    datetime.fromisoformat(row["touch_time"]),
                    int(dec(row["zone_low"]) / Decimal("0.25")),
                    int(dec(row["zone_high"]) / Decimal("0.25")),
                    row["approach_side"],
                )
            )
        control_rows.extend(rows("control_events", year))
        for row in rows("forward_metrics", year):
            if row["horizon_complete"] == "true":
                horizon = int(row["forward_horizon"])
                metric_by_event[row["event_id"]]["complete"].add(horizon)
                if horizon == 30:
                    metric_by_event[row["event_id"]]["h30"] = row
    episodes = cluster_episodes(episode_events)
    events = []
    families = {}
    for row in treated_rows:
        event = match_event(row, episode_id=episodes.get(row["event_id"], ""))
        if (
            event is not None
            and metric_by_event[event.event_id]["complete"] == {15, 30, 60, 120}
        ):
            events.append(event)
    for row in control_rows:
        event = match_event(row)
        if (
            event is not None
            and metric_by_event[event.event_id]["complete"] == {15, 30, 60, 120}
        ):
            events.append(event)
            families[event.event_id] = row["control_family"]
    return events, families, metric_by_event, episodes


def write_width_and_funnel_reports(
    *, treated, controls, families, primary, unmatched, by_event
) -> None:
    """Amendment 02 width-balance and matching-eligibility reporting.

    Width balance is reported per relationship and control family, pre-match
    over all admissible events and post-match over the realized pairs. The
    funnel counts why treated events failed to match, and separately counts
    candidate evaluations rejected by the width caliper alone.
    """
    controls_by_lane: dict[tuple, list] = defaultdict(list)
    for control in controls:
        if zone_width_atr(control) is not None:
            controls_by_lane[(families[control.event_id], _primary_lane_key(control))].append(control)

    width_rows, funnel_rows = [], []
    for relationship in sorted({event.relationship_id for event in treated}):
        for family in ("C01", "C02"):
            lane_treated = [e for e in treated if e.relationship_id == relationship]
            lane_controls = [
                e for e in controls
                if families[e.event_id] == family and e.relationship_id == relationship
            ]
            pairs = [
                pair for pair in primary
                if pair.control_family == family
                and by_event[pair.treated_event_id].relationship_id == relationship
            ]

            # Candidate evaluations rejected by the width caliper alone.
            width_rejections = 0
            for event in lane_treated:
                treated_width = zone_width_atr(event)
                if treated_width is None:
                    continue
                for control in controls_by_lane.get((family, _primary_lane_key(event)), ()):
                    if control.session_date == event.session_date:
                        continue
                    admissible, _ = _width_terms(treated_width, zone_width_atr(control))
                    if not admissible:
                        width_rejections += 1

            treated_widths = [w for w in (zone_width_atr(e) for e in lane_treated) if w is not None]
            control_widths = [w for w in (zone_width_atr(e) for e in lane_controls) if w is not None]
            matched_treated = [zone_width_atr(by_event[p.treated_event_id]) for p in pairs]
            matched_control = [zone_width_atr(by_event[p.control_event_id]) for p in pairs]
            ratios = [c / t for t, c in zip(matched_treated, matched_control)]
            post_smd = (
                standardized_mean_difference(matched_treated, matched_control)
                if pairs else None
            )
            width_rows.append(
                {
                    "relationship_id": relationship,
                    "control_family": family,
                    "matched_pairs": len(pairs),
                    "mean_treated_width_atr": _mean(matched_treated),
                    "mean_control_width_atr": _mean(matched_control),
                    "mean_absolute_width_difference_atr": _mean(
                        [abs(t - c) for t, c in zip(matched_treated, matched_control)]
                    ),
                    "mean_width_ratio": _mean(ratios),
                    "minimum_width_ratio": min(ratios) if ratios else None,
                    "maximum_width_ratio": max(ratios) if ratios else None,
                    "mean_absolute_log_width_ratio": _mean(
                        [abs((t / c).ln()) for t, c in zip(matched_treated, matched_control)]
                    ),
                    "pre_match_width_smd": (
                        standardized_mean_difference(treated_widths, control_widths)
                        if treated_widths and control_widths else None
                    ),
                    "post_match_width_smd": post_smd,
                    "post_match_width_balanced": (
                        abs(post_smd) <= Decimal("0.20") if post_smd is not None else None
                    ),
                    "width_caliper_rejections": width_rejections,
                }
            )

            reasons = defaultdict(int)
            for key, reason in unmatched.items():
                event_family, event_id = key.split("|", 1)
                if event_family != family:
                    continue
                event = by_event.get(event_id)
                if event is None or event.relationship_id != relationship:
                    continue
                reasons[reason] += 1
            funnel_rows.append(
                {
                    "relationship_id": relationship,
                    "control_family": family,
                    "treated_events": len(lane_treated),
                    "control_events": len(lane_controls),
                    "matched_pairs": len(pairs),
                    "unmatched_no_lane_controls": reasons["NO_LANE_CONTROLS"],
                    "unmatched_lane_exhausted": reasons["LANE_CONTROLS_EXHAUSTED"],
                    "unmatched_caliper_or_session": reasons["PRIMARY_CALIPER_OR_SESSION"],
                    "unmatched_invalid_treated_width": reasons["INVALID_TREATED_WIDTH"],
                    "width_caliper_rejections": width_rejections,
                }
            )

    for name, rows_out in (("width_balance", width_rows), ("matching_eligibility_funnel", funnel_rows)):
        fields = tuple(rows_out[0]) if rows_out else ("relationship_id",)
        (OUTPUT / f"{name}.csv").write_bytes(
            deterministic_csv_bytes(rows_out, fields, sort_by=fields[:2])
        )


def _mean(values):
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else None


def main(argv: list[str] | None = None) -> None:
    global OUTPUT, DETAIL, YEARS
    args = parse_args(argv)
    DETAIL = args.input_root
    OUTPUT = args.output_root
    YEARS = tuple(args.years)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    events, families, metrics, episodes = load()
    treated = [event for event in events if event.event_id.startswith("E-")]
    controls = [event for event in events if event.event_id.startswith("CE-")]
    primary, secondary, unmatched = [], [], {}
    for family in ("C01", "C02"):
        family_controls = [event for event in controls if families[event.event_id] == family]
        pairs, missing = primary_cross_session_match(
            treated, family_controls, control_family=family
        )
        primary.extend(pairs)
        unmatched.update({f"{family}|{key}": value for key, value in missing.items()})
        pairs, _ = secondary_same_session_match(
            treated, family_controls, control_family=family
        )
        secondary.extend(pairs)

    by_event = {event.event_id: event for event in events}
    primary_rows, secondary_rows, observations = [], [], []
    metric_names = (
        "inside_close_share",
        "mean_overlap_share",
        "midpoint_crossings",
        "path_efficiency",
        "continuous_residence_minutes",
        "reentry_30",
    )
    for pair_set, destination in ((primary, primary_rows), (secondary, secondary_rows)):
        for pair in pair_set:
            treated_event = by_event[pair.treated_event_id]
            control_event = by_event[pair.control_event_id]
            treated_metric = metrics[pair.treated_event_id]["h30"]
            control_metric = metrics[pair.control_event_id]["h30"]
            row = asdict(pair) | {
                "relationship_id": treated_event.relationship_id,
                "allocation_method": treated_event.allocation_method,
                "bin_ratio": treated_event.bin_ratio,
                "prominence_threshold": treated_event.prominence_threshold,
                "year": treated_event.year,
                "economic_episode_id": treated_event.economic_episode_id,
                "inside_close_share_30_treated": treated_metric["inside_close_share"],
                "inside_close_share_30_control": control_metric["inside_close_share"],
                "inside_close_share_30_difference": (
                    dec(treated_metric["inside_close_share"])
                    - dec(control_metric["inside_close_share"])
                ),
            }
            destination.append(row)
            if pair.match_design == "PRIMARY_CROSS_SESSION":
                for metric_name in metric_names:
                    tv, cv = treated_metric[metric_name], control_metric[metric_name]
                    if tv == "" or cv == "":
                        continue
                    if metric_name.startswith("reentry"):
                        tv = "1" if tv == "true" else "0"
                        cv = "1" if cv == "true" else "0"
                    observations.append(
                        PairObservation(
                            pair.pair_id,
                            pair.match_design,
                            treated_event.relationship_id,
                            pair.control_family,
                            treated_event.allocation_method,
                            treated_event.bin_ratio,
                            treated_event.prominence_threshold,
                            treated_event.year,
                            pair.treated_session_date,
                            pair.control_session_date,
                            treated_event.economic_episode_id,
                            metric_name,
                            dec(tv),
                            dec(cv),
                        )
                    )

    match_fields = tuple(primary_rows[0]) if primary_rows else ("pair_id",)
    write_deterministic_gzip_csv(
        DETAIL / "match_ledger_primary.csv.gz",
        primary_rows,
        match_fields,
        sort_by=("pair_id",),
    )
    secondary_fields = tuple(secondary_rows[0]) if secondary_rows else ("pair_id",)
    write_deterministic_gzip_csv(
        DETAIL / "match_ledger_secondary.csv.gz",
        secondary_rows,
        secondary_fields,
        sort_by=("pair_id",),
    )

    groups: dict[tuple, list[PairObservation]] = defaultdict(list)
    for observation in observations:
        if observation.metric_name == "inside_close_share":
            groups[
                (
                    observation.relationship_id,
                    observation.control_family,
                    observation.allocation_method,
                    observation.bin_ratio,
                    observation.prominence_threshold,
                    observation.year,
                )
            ].append(observation)
    result_rows = []
    for key, group in sorted(groups.items()):
        summary = paired_summary(group, resamples=10_000)
        result_rows.append(
            dict(
                zip(
                    (
                        "relationship_id",
                        "control_family",
                        "allocation_method",
                        "bin_ratio",
                        "prominence_threshold",
                        "year",
                    ),
                    key,
                )
            )
            | asdict(summary)
        )
    result_fields = tuple(result_rows[0]) if result_rows else ("relationship_id",)
    (OUTPUT / "paired_primary_results.csv").write_bytes(
        deterministic_csv_bytes(result_rows, result_fields, sort_by=result_fields[:6])
    )

    # Same-session descriptive results.
    secondary_summary = []
    secondary_groups = defaultdict(list)
    for row in secondary_rows:
        key = (
            row["relationship_id"],
            row["control_family"],
            row["allocation_method"],
            row["bin_ratio"],
            row["prominence_threshold"],
            row["year"],
        )
        secondary_groups[key].append(dec(str(row["inside_close_share_30_difference"])))
    for key, values in sorted(secondary_groups.items()):
        secondary_summary.append(
            dict(
                zip(
                    (
                        "relationship_id",
                        "control_family",
                        "allocation_method",
                        "bin_ratio",
                        "prominence_threshold",
                        "year",
                    ),
                    key,
                )
            )
            | {
                "count": len(values),
                "mean": sum(values, Decimal(0)) / Decimal(len(values)),
            }
        )
    fields = tuple(secondary_summary[0]) if secondary_summary else ("relationship_id",)
    (OUTPUT / "paired_secondary_results.csv").write_bytes(
        deterministic_csv_bytes(secondary_summary, fields, sort_by=fields[:6])
    )

    # Grid stability and relationship/control pooled gates.
    grid_rows = []
    pooled_cell = defaultdict(list)
    for row in result_rows:
        pooled_cell[
            (
                row["relationship_id"],
                row["control_family"],
                row["allocation_method"],
                dec(str(row["bin_ratio"])),
                dec(str(row["prominence_threshold"])),
            )
        ].append((int(row["count"]), dec(str(row["mean"]))))
    for relationship in sorted({key[0] for key in pooled_cell}):
        for family in ("C01", "C02"):
            for method in ("uniform_bar_volume", "tpo_range_occupancy"):
                cells = {}
                for ratio in (Decimal("0.05"), Decimal("0.10"), Decimal("0.20")):
                    for prominence in (Decimal("1.5"), Decimal("2.0"), Decimal("2.5")):
                        values = pooled_cell.get(
                            (relationship, family, method, ratio, prominence), []
                        )
                        total = sum(count for count, _ in values)
                        cells[(ratio, prominence)] = (
                            sum(Decimal(count) * effect for count, effect in values)
                            / Decimal(total)
                            if total
                            else None
                        )
                valid = [value for value in cells.values() if value is not None]
                grid_rows.append(
                    {
                        "relationship_id": relationship,
                        "control_family": family,
                        "allocation_method": method,
                        "positive_cells": sum(value > 0 for value in valid),
                        "available_cells": len(valid),
                        "median_effect": sorted(valid)[len(valid) // 2] if valid else None,
                        "minimum_effect": min(valid) if valid else None,
                        "maximum_effect": max(valid) if valid else None,
                        "stable_neighborhood": stable_grid(cells),
                    }
                )
    grid_fields = tuple(grid_rows[0]) if grid_rows else ("relationship_id",)
    (OUTPUT / "grid_stability.csv").write_bytes(
        deterministic_csv_bytes(grid_rows, grid_fields, sort_by=grid_fields[:3])
    )

    # Required compact summaries.
    checkpoints = [
        json.loads((DETAIL / f"checkpoint_{year}.json").read_text()) for year in YEARS
    ]
    opportunity_summary = [
        {
            "year": row["year"],
            "profiles": row["profiles"],
            "opportunities": row["opportunities"],
            "events": row["events"],
            "untouched_or_excluded": row["opportunities"] - row["events"],
        }
        for row in checkpoints
    ]
    control_summary = [
        {
            "year": row["year"],
            "control_opportunities": row["control_opportunities"],
            "control_events": row["control_events"],
        }
        for row in checkpoints
    ]
    for filename, summary_rows in (
        ("opportunity_summary.csv", opportunity_summary),
        ("event_summary.csv", opportunity_summary),
        ("control_summary.csv", control_summary),
    ):
        fields = tuple(summary_rows[0])
        (OUTPUT / filename).write_bytes(
            deterministic_csv_bytes(summary_rows, fields, sort_by=("year",))
        )

    match_quality = []
    for relationship in sorted({event.relationship_id for event in treated}):
        for family in ("C01", "C02"):
            eligible = [event for event in treated if event.relationship_id == relationship]
            pairs = [
                pair
                for pair in primary
                if pair.control_family == family
                and by_event[pair.treated_event_id].relationship_id == relationship
            ]
            covariates = (
                "minute_from_interaction_start",
                "atr_at_touch",
                "pre_touch_displacement_atr",
                "pre_touch_path_efficiency",
                "interaction_open_distance_atr",
                "poc_distance_atr",
            )
            smds = {}
            for covariate in covariates:
                smds[covariate] = (
                    standardized_mean_difference(
                        [getattr(by_event[pair.treated_event_id], covariate) for pair in pairs],
                        [getattr(by_event[pair.control_event_id], covariate) for pair in pairs],
                    )
                    if pairs
                    else None
                )
            finite_smds = [
                abs(value)
                for value in smds.values()
                if value is not None
            ]
            match_quality.append(
                {
                    "relationship_id": relationship,
                    "control_family": family,
                    "treated_events": len(eligible),
                    "matched_pairs": len(pairs),
                    "match_rate": Decimal(len(pairs)) / Decimal(len(eligible)) if eligible else None,
                    "control_reuse_count": len(pairs) - len({pair.control_event_id for pair in pairs}),
                    "mean_distance": (
                        sum((pair.distance for pair in pairs), Decimal(0)) / Decimal(len(pairs))
                        if pairs else None
                    ),
                    "maximum_absolute_post_match_smd": max(finite_smds) if finite_smds else None,
                    "material_imbalance": (
                        any(value > Decimal("0.20") for value in finite_smds)
                        if finite_smds else None
                    ),
                }
            )
    fields = tuple(match_quality[0]) if match_quality else ("relationship_id",)
    (OUTPUT / "match_quality.csv").write_bytes(
        deterministic_csv_bytes(match_quality, fields, sort_by=fields[:2])
    )

    write_width_and_funnel_reports(
        treated=treated,
        controls=controls,
        families=families,
        primary=primary,
        unmatched=unmatched,
        by_event=by_event,
    )

    episode_summary = [
        {
            "raw_definition_events": len(episodes),
            "unique_economic_episodes": len(set(episodes.values())),
            "definitions_per_episode_mean": (
                Decimal(len(episodes)) / Decimal(len(set(episodes.values())))
                if episodes else None
            ),
        }
    ]
    fields = tuple(episode_summary[0])
    (OUTPUT / "economic_episode_summary.csv").write_bytes(
        deterministic_csv_bytes(episode_summary, fields)
    )
    episode_rows = [
        {"event_id": event_id, "economic_episode_id": episode_id}
        for event_id, episode_id in episodes.items()
    ]
    write_deterministic_gzip_csv(
        DETAIL / "economic_episode_ledger.csv.gz",
        episode_rows,
        ("event_id", "economic_episode_id"),
        sort_by=("event_id",),
    )

    primary_observations = [
        observation
        for observation in observations
        if observation.metric_name == "inside_close_share"
    ]
    year_rows = []
    concentration_rows = []
    diagnostic_by_lane = {}
    for relationship in sorted({event.relationship_id for event in treated}):
        for family in ("C01", "C02"):
            lane = [
                observation
                for observation in primary_observations
                if observation.relationship_id == relationship
                and observation.control_family == family
            ]
            collapsed = collapse_episodes(lane)
            if not collapsed:
                continue
            base = paired_summary(collapsed, resamples=10_000)
            year_means = {}
            for year in YEARS:
                subset = [observation for observation in collapsed if observation.year == year]
                summary = paired_summary(subset, resamples=10_000) if subset else None
                year_means[year] = summary.mean if summary else None
                year_rows.append(
                    {
                        "relationship_id": relationship,
                        "control_family": family,
                        "year": year,
                        "unique_economic_episodes": len(subset),
                        "mean": summary.mean if summary else None,
                        "ci_low": summary.ci_low if summary else None,
                        "ci_high": summary.ci_high if summary else None,
                    }
                )
            ordered = sorted(
                collapsed, key=lambda observation: (-abs(observation.difference), observation.pair_id)
            )
            trim_count = math.ceil(len(ordered) * 0.01)
            trimmed = ordered[trim_count:]
            trimmed_mean = (
                sum((observation.difference for observation in trimmed), Decimal(0))
                / Decimal(len(trimmed))
                if trimmed
                else None
            )
            episode_trimmed = list(collapsed)
            for year in YEARS:
                largest = sorted(
                    [observation for observation in episode_trimmed if observation.year == year],
                    key=lambda observation: (-abs(observation.difference), observation.pair_id),
                )[:5]
                remove = {observation.pair_id for observation in largest}
                episode_trimmed = [
                    observation for observation in episode_trimmed
                    if observation.pair_id not in remove
                ]
            episode_trimmed_mean = (
                sum((observation.difference for observation in episode_trimmed), Decimal(0))
                / Decimal(len(episode_trimmed))
                if episode_trimmed else None
            )
            loo = {}
            for year in YEARS:
                subset = [observation for observation in collapsed if observation.year != year]
                loo[year] = (
                    sum((observation.difference for observation in subset), Decimal(0))
                    / Decimal(len(subset))
                    if subset else None
                )
            concentration_rows.extend(
                [
                    {
                        "relationship_id": relationship,
                        "control_family": family,
                        "diagnostic": "BASE",
                        "excluded_year": "",
                        "mean": base.mean,
                        "count": len(collapsed),
                    },
                    {
                        "relationship_id": relationship,
                        "control_family": family,
                        "diagnostic": "REMOVE_LARGEST_1_PERCENT",
                        "excluded_year": "",
                        "mean": trimmed_mean,
                        "count": len(trimmed),
                    },
                    {
                        "relationship_id": relationship,
                        "control_family": family,
                        "diagnostic": "REMOVE_TOP5_EPISODES_PER_YEAR",
                        "excluded_year": "",
                        "mean": episode_trimmed_mean,
                        "count": len(episode_trimmed),
                    },
                ]
                + [
                    {
                        "relationship_id": relationship,
                        "control_family": family,
                        "diagnostic": "LEAVE_ONE_YEAR_OUT",
                        "excluded_year": year,
                        "mean": value,
                        "count": sum(1 for observation in collapsed if observation.year != year),
                    }
                    for year, value in loo.items()
                ]
            )
            contributions = {
                year: sum(
                    (
                        observation.difference
                        for observation in collapsed
                        if observation.year == year
                    ),
                    Decimal(0),
                )
                for year in YEARS
            }
            contribution_denominator = sum(
                (abs(value) for value in contributions.values()), Decimal(0)
            )
            diagnostic_by_lane[(relationship, family)] = {
                "base": base,
                "year_means": year_means,
                "max_year_contribution": (
                    max(abs(value) for value in contributions.values())
                    / contribution_denominator
                    if contribution_denominator else None
                ),
                "trimmed_mean": trimmed_mean,
                "episode_trimmed_mean": episode_trimmed_mean,
                "loo": loo,
            }

    fields = tuple(year_rows[0]) if year_rows else ("relationship_id",)
    (OUTPUT / "year_results.csv").write_bytes(
        deterministic_csv_bytes(year_rows, fields, sort_by=("relationship_id", "control_family", "year"))
    )
    fields = tuple(concentration_rows[0]) if concentration_rows else ("relationship_id",)
    (OUTPUT / "concentration_results.csv").write_bytes(
        deterministic_csv_bytes(
            concentration_rows,
            fields,
            sort_by=("relationship_id", "control_family", "diagnostic", "excluded_year"),
        )
    )

    gate_rows = []
    for relationship in sorted({event.relationship_id for event in treated}):
        rel_pairs = [
            pair
            for pair in primary
            if by_event[pair.treated_event_id].relationship_id == relationship
        ]
        episode_count = len(
            {by_event[pair.treated_event_id].economic_episode_id for pair in rel_pairs}
        )
        year_counts = defaultdict(set)
        for pair in rel_pairs:
            event = by_event[pair.treated_event_id]
            year_counts[event.year].add(event.economic_episode_id)
        g01 = (
            "PASS"
            if episode_count >= 100 and sum(len(value) >= 20 for value in year_counts.values()) >= 3
            else "UNDERPOWERED"
        )
        lane_passes = {}
        for family in ("C01", "C02"):
            diagnostic = diagnostic_by_lane.get((relationship, family))
            if not diagnostic:
                continue
            base = diagnostic["base"]
            g02 = bool(base.mean and base.mean > 0 and base.ci_low and base.ci_low > 0)
            signed_years = sum(
                value is not None and value > 0
                for value in diagnostic["year_means"].values()
            )
            g03 = (
                signed_years >= 3
                and diagnostic["max_year_contribution"] is not None
                and diagnostic["max_year_contribution"] <= Decimal("0.50")
            )
            stable = any(
                row["stable_neighborhood"]
                for row in grid_rows
                if row["relationship_id"] == relationship
                and row["control_family"] == family
            )
            structural_support = 0
            contradiction = False
            for metric_name, expected_positive in (
                ("mean_overlap_share", True),
                ("midpoint_crossings", True),
                ("path_efficiency", False),
                ("continuous_residence_minutes", True),
                ("reentry_30", True),
            ):
                metric_group = collapse_episodes(
                    [
                        observation
                        for observation in observations
                        if observation.relationship_id == relationship
                        and observation.control_family == family
                        and observation.metric_name == metric_name
                    ]
                )
                if not metric_group:
                    continue
                summary = paired_summary(
                    metric_group,
                    expected_positive=expected_positive,
                    resamples=10_000,
                )
                supports = (
                    summary.mean > 0 and summary.ci_low > 0
                    if expected_positive
                    else summary.mean < 0 and summary.ci_high < 0
                )
                opposes = (
                    summary.mean < 0 and summary.ci_high < 0
                    if expected_positive
                    else summary.mean > 0 and summary.ci_low > 0
                )
                structural_support += int(supports)
                contradiction = contradiction or opposes
            g05 = structural_support >= 2 and not contradiction
            g06 = (
                diagnostic["trimmed_mean"] is not None
                and diagnostic["trimmed_mean"] > 0
                and diagnostic["episode_trimmed_mean"] is not None
                and diagnostic["episode_trimmed_mean"] > 0
                and all(value is not None and value > 0 for value in diagnostic["loo"].values())
            )
            quality = next(
                row for row in match_quality
                if row["relationship_id"] == relationship
                and row["control_family"] == family
            )
            g07 = (
                quality["control_reuse_count"] == 0
                and quality["material_imbalance"] is False
            )
            g08 = stable and base.mean > 0
            lane_passes[family] = {
                "G02": g02,
                "G03": g03,
                "G04": stable,
                "G05": g05,
                "G06": g06,
                "G07": g07,
                "G08": g08,
                "supporting_metrics": structural_support,
            }
        for gate in ("G01", "G02", "G03", "G04", "G05", "G06", "G07", "G08"):
            if gate == "G01":
                status = g01
            elif g01 != "PASS":
                status = "UNDERPOWERED"
            else:
                status = (
                    "PASS"
                    if any(lane.get(gate, False) for lane in lane_passes.values())
                    else "FAIL"
                )
            gate_rows.append(
                {
                    "relationship_id": relationship,
                    "gate": gate,
                    "status": status,
                    "evidence": (
                        f"unique_primary_episodes={episode_count}; "
                        f"years_20plus={sum(len(value) >= 20 for value in year_counts.values())}; "
                        f"control_lanes={lane_passes}"
                    ),
                }
            )
    fields = tuple(gate_rows[0]) if gate_rows else ("relationship_id",)
    (OUTPUT / "gate_results.csv").write_bytes(
        deterministic_csv_bytes(gate_rows, fields, sort_by=("relationship_id", "gate"))
    )

    # Commit-safe schemas and deterministic audit samples for every full local
    # ledger partition, including files above the GitHub-safe threshold.
    schemas = {}
    sample_dir = OUTPUT / "audit_samples"
    sample_dir.mkdir(exist_ok=True)
    for path in sorted(DETAIL.glob("*.csv.gz")):
        with gzip.open(path, "rt", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = tuple(reader.fieldnames or ())
            sample = []
            for index, row in enumerate(reader):
                if index == 250:
                    break
                sample.append(row)
        schemas[path.name] = {
            "fields": fields,
            "full_local_path": str(path),
        }
        write_deterministic_gzip_csv(
            sample_dir / path.name,
            sample,
            fields or ("record_id",),
            sort_by=(),
        )
    (OUTPUT / "DETAILED_LEDGER_SCHEMAS.json").write_text(
        json.dumps(schemas, indent=2, sort_keys=True) + "\n"
    )

    manifest = []
    for path in sorted(OUTPUT.rglob("*")):
        if not path.is_file() or path.name == "STAGE_02_MANIFEST.json":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.append(
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": digest,
                "commit_eligible": path.stat().st_size < 90_000_000,
            }
        )
    (OUTPUT / "STAGE_02_MANIFEST.json").write_text(
        json.dumps(
            {
                "code_sha": code_sha,
                "years_available": list(YEARS),
                "year_2019": "ABSENT_FROM_SUPPLIED_ARCHIVES",
                "files": manifest,
                "primary_pairs": len(primary),
                "secondary_pairs": len(secondary),
                "unmatched": len(unmatched),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "events": len(events),
                "primary_pairs": len(primary),
                "secondary_pairs": len(secondary),
                "episodes": len(set(episodes.values())),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
