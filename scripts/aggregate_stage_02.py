from __future__ import annotations

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
from hvn.matching import MatchEvent, primary_cross_session_match, secondary_same_session_match
from hvn.stage02_ledger import deterministic_csv_bytes, write_deterministic_gzip_csv
from hvn.stage02_statistics import PairObservation, paired_summary, stable_grid

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "stage_02"
DETAIL = OUTPUT / "detailed"
YEARS = (2021, 2023, 2025, 2026)


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


def main() -> None:
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
                }
            )
    fields = tuple(match_quality[0]) if match_quality else ("relationship_id",)
    (OUTPUT / "match_quality.csv").write_bytes(
        deterministic_csv_bytes(match_quality, fields, sort_by=fields[:2])
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

    # Conservative gates: full diagnostics are explicit, and any missing
    # required corroboration or balance evidence prevents a pass.
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
        for gate in ("G01", "G02", "G03", "G04", "G05", "G06", "G07", "G08"):
            gate_rows.append(
                {
                    "relationship_id": relationship,
                    "gate": gate,
                    "status": g01 if gate == "G01" else (
                        "BLOCKED" if g01 == "PASS" else "UNDERPOWERED"
                    ),
                    "evidence": (
                        f"unique_primary_episodes={episode_count}; "
                        f"years_20plus={sum(len(value) >= 20 for value in year_counts.values())}"
                    ),
                }
            )
    fields = tuple(gate_rows[0]) if gate_rows else ("relationship_id",)
    (OUTPUT / "gate_results.csv").write_bytes(
        deterministic_csv_bytes(gate_rows, fields, sort_by=("relationship_id", "gate"))
    )

    # Placeholders required by the locked artifact contract; diagnostics are
    # derived from primary pairs and explicitly marked pending where not valid.
    for filename, label in (
        ("year_results.csv", "see paired_primary_results.csv"),
        ("concentration_results.csv", "pending full primary support"),
    ):
        (OUTPUT / filename).write_bytes(
            deterministic_csv_bytes(
                [{"status": label}], ("status",)
            )
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
