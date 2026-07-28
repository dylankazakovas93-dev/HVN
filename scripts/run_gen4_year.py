"""Generation 4 partition runner: one development year, end to end.

Builds frozen tick profiles and zones, selects width-matched controls, finds
causal touches inside each relationship's interaction window, measures the
displacement, envelope and continuation family, and writes the event ledgers
plus the aggregate tables required by
`research/hvn/STAGE_02_GENERATION_4_AMENDMENT_02.md`.

POC and non-POC populations are carried separately throughout. Every table is
produced both per anchor split by interaction session and per anchor combined.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from hvn.atr import wilder_atr
from hvn.gen4_controls import select_controls
from hvn.gen4_outcomes import (
    CONTINUATION_HORIZONS_MINUTES,
    DISPLACEMENT_THRESHOLDS_ATR,
    BAR_BUCKETS,
)
from hvn.gen4_pipeline import (
    RELATIONSHIPS_BY_FAMILY,
    events_for_interval,
    interaction_bars,
    zone_population,
)
from hvn.io import databento_rows_with_audit
from hvn.models import ProfileFamily
from hvn.sessions import profile_window
from hvn.stage02_ledger import deterministic_csv_bytes, write_deterministic_gzip_csv
from hvn.stage02_pipeline import (
    EXPECTED_SOURCE_MINUTES,
    AtrSelector,
    ContractSelector,
    _consecutive,
    trading_dates,
)
from hvn.zones_v4 import NONPOC_HVN_ZONE, POC_HVN_ZONE, classify_zones, construct_tick_profile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "stage_02_generation_4_study"
PRESERVED = tuple(
    ROOT / "outputs" / name
    for name in (
        "stage_02",
        "stage_02_generation_2",
        "stage_02_generation_3_atomic",
        "stage_02_generation_3_atomic_pilot_v2",
        "stage_02_generation_3_atomic_pilot_v3",
        "stage_02_generation_3_atomic_pilot_v4",
        "stage_02_generation_3_final",
        "stage_02_generation_4_hvn_zones_pilot",
        "stage_02_generation_4_hvn_zones_pilot_a01",
    )
)
SOURCES = {
    2019: ("nq2018.zip", "glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst"),
    2021: ("nq2021.zip", "glbx-mdp3-20210101-20221230.ohlcv-1m.csv.zst"),
    2023: ("nq2023.zip", "glbx-mdp3-20230101-20241230.ohlcv-1m.csv.zst"),
    2025: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
    2026: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
}
FORBIDDEN_YEARS = (2018, 2020, 2022, 2024)
UNDERPOWERED_EPISODES = 30


def archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="run_gen4_year.py")
    parser.add_argument("--year", type=int, choices=sorted(SOURCES), required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    output = args.output_root.resolve()
    for preserved in PRESERVED:
        if output == preserved or preserved in output.parents:
            parser.error(f"refusing to write into a preserved generation: {output}")
    args.output_root = output
    return args


def build(bars, *, year, code_sha):
    dates = trading_dates(bars)
    by_symbol = {
        s: tuple(b for b in bars if b.symbol == s)
        for s in sorted({b.symbol for b in bars})
    }
    atrs = {s: AtrSelector(wilder_atr(v)) for s, v in by_symbol.items()}
    selector = ContractSelector(by_symbol)

    events: list[dict] = []
    intervals: list[dict] = []
    profiles = 0

    for position, current in enumerate(dates):
        if position == 0:
            continue
        prior = dates[position - 1]
        for family in ProfileFamily:
            source_date = prior if family == ProfileFamily.PRIOR_RTH else current
            pwindow = profile_window(family, source_date)
            try:
                symbol = selector.choose(pwindow.source_start)
            except ValueError:
                continue
            source = sorted(
                [
                    b
                    for b in by_symbol[symbol]
                    if pwindow.source_start <= b.start_time < pwindow.source_end
                ],
                key=lambda b: b.close_time,
            )
            if not _consecutive(source, EXPECTED_SOURCE_MINUTES[family]):
                continue
            atr_point = atrs[symbol].before(pwindow.source_start)
            try:
                profile = construct_tick_profile(
                    source, (atr_point,), pwindow,
                    code_sha=code_sha, data_partition=f"development_{year}",
                )
            except ValueError:
                continue
            zones, activity = classify_zones(profile)
            if not activity.valid:
                continue
            profiles += 1
            accepted = [z for z in zones if z.accepted]
            if not accepted:
                continue

            # Controls are chosen once per frozen profile, from structural
            # information only, before any interaction window is opened.
            taken: set[int] = set()
            controls_by_zone: dict[str, list] = {}
            for zone in accepted:
                chosen = select_controls(
                    profile, activity, accepted, zone, taken=taken
                )
                for control in chosen:
                    taken.update(range(control.low_index, control.high_index + 1))
                controls_by_zone[zone.zone_id] = chosen

            for relationship in RELATIONSHIPS_BY_FAMILY[family]:
                try:
                    window_bars = interaction_bars(
                        by_symbol, symbol, relationship,
                        source_date=source_date, interaction_date=current,
                    )
                except (KeyError, ValueError):
                    continue
                if len(window_bars) < 2:
                    continue
                base = {
                    "year": year,
                    "profile_id": profile.profile_id,
                    "family": family.value,
                    "relationship_id": relationship.value,
                    "session_date": current.isoformat(),
                    "contract": symbol,
                    "atr_value": profile.atr_value,
                }
                for zone in accepted:
                    rows, summary = events_for_interval(
                        window_bars,
                        interval_id=f"{zone.zone_id}-{relationship.value}",
                        population=zone_population(zone.zone_class),
                        zone_class=zone.zone_class,
                        low=zone.zone_low,
                        high=zone.zone_high,
                        atr=profile.atr_value,
                        base=base | {"arm": "TREATED", "physical_zone_id": zone.physical_zone_id},
                    )
                    events.extend(rows)
                    intervals.append(summary)
                    for control in controls_by_zone.get(zone.zone_id, []):
                        crows, csummary = events_for_interval(
                            window_bars,
                            interval_id=f"{control.control_id}-{relationship.value}",
                            population=zone_population(zone.zone_class),
                            zone_class=zone.zone_class,
                            low=control.control_low,
                            high=control.control_high,
                            atr=profile.atr_value,
                            base=base
                            | {
                                "arm": control.control_family,
                                "physical_zone_id": zone.physical_zone_id,
                                "matched_zone_id": zone.zone_id,
                            },
                        )
                        events.extend(crows)
                        intervals.append(csummary)

    return {"events": events, "intervals": intervals, "profiles": profiles}


# ---------------------------------------------------------------------------
# Aggregation


def _pct(numerator: int, denominator: int) -> Decimal | None:
    if not denominator:
        return None
    return (Decimal(numerator) * Decimal(100) / Decimal(denominator)).quantize(
        Decimal("0.01")
    )


def _strata(row: dict) -> list[tuple[str, str]]:
    """Each row contributes to its session cell and to the combined cell."""
    return [
        (row["relationship_id"], row["interaction_session"]),
        (row["relationship_id"], "ALL_SESSIONS"),
        ("ALL_ANCHORS", row["interaction_session"]),
        ("ALL_ANCHORS", "ALL_SESSIONS"),
    ]


def touch_population(intervals: list[dict]) -> list[dict]:
    """Touch rates with their denominator: untouched intervals are reported."""
    buckets: dict[tuple, dict] = defaultdict(
        lambda: {"intervals": 0, "touched": 0, "touches": 0, "retouches": 0, "first_touch_minutes": []}
    )
    for row in intervals:
        for anchor in (row["relationship_id"], "ALL_ANCHORS"):
            key = (row["population"], row["arm"], anchor)
            cell = buckets[key]
            cell["intervals"] += 1
            cell["touched"] += 1 if row["touched"] else 0
            cell["touches"] += row["touch_count"]
            cell["retouches"] += row["retouch_count"]
            if row["minutes_to_first_touch"] is not None:
                cell["first_touch_minutes"].append(row["minutes_to_first_touch"])
    out = []
    for (population, arm, anchor), cell in sorted(buckets.items()):
        minutes = sorted(cell["first_touch_minutes"])
        out.append(
            {
                "population": population,
                "arm": arm,
                "anchor": anchor,
                "intervals": cell["intervals"],
                "untouched": cell["intervals"] - cell["touched"],
                "touched": cell["touched"],
                "touch_rate_pct": _pct(cell["touched"], cell["intervals"]),
                "total_touches": cell["touches"],
                "retouches": cell["retouches"],
                "touches_per_touched_interval": (
                    (Decimal(cell["touches"]) / Decimal(cell["touched"])).quantize(
                        Decimal("0.01")
                    )
                    if cell["touched"]
                    else None
                ),
                "median_minutes_to_first_touch": (
                    minutes[len(minutes) // 2] if minutes else None
                ),
                "underpowered": cell["touched"] < UNDERPOWERED_EPISODES,
            }
        )
    return out


def displacement_distribution(events: list[dict]) -> list[dict]:
    """Share of first touches reaching each threshold on bar 1, 2, 3, ..."""
    first = [e for e in events if e["is_first_touch"]]
    out = []
    for threshold in DISPLACEMENT_THRESHOLDS_ATR:
        key = f"{int(threshold)}atr"
        buckets: dict[tuple, list] = defaultdict(list)
        for row in first:
            for anchor, session in _strata(row):
                buckets[(row["population"], row["arm"], anchor, session)].append(row)
        for (population, arm, anchor, session), rows in sorted(buckets.items()):
            total = len(rows)
            counts = Counter()
            for row in rows:
                if row[f"censored_{key}"]:
                    counts["censored"] += 1
                elif not row[f"reached_{key}"]:
                    counts["never_reached"] += 1
                else:
                    bars = row[f"bars_to_{key}"]
                    for label, low, high in BAR_BUCKETS:
                        if low <= bars <= high:
                            counts[label] += 1
                            break
            reached = sorted(
                row[f"bars_to_{key}"] for row in rows if row[f"reached_{key}"]
            )
            record = {
                "threshold": key,
                "population": population,
                "arm": arm,
                "anchor": anchor,
                "session": session,
                "events": total,
                "reached": len(reached),
                "reached_pct": _pct(len(reached), total),
                "never_reached": counts["never_reached"],
                "never_reached_pct": _pct(counts["never_reached"], total),
                "censored": counts["censored"],
                "censored_pct": _pct(counts["censored"], total),
                "median_bars": reached[len(reached) // 2] if reached else None,
                "p90_bars": reached[int(0.9 * (len(reached) - 1))] if reached else None,
                "underpowered": total < UNDERPOWERED_EPISODES,
            }
            for label, _, _ in BAR_BUCKETS:
                record[f"bars_{label}_pct"] = _pct(counts[label], total)
            out.append(record)
    return out


def envelope_summary(events: list[dict]) -> list[dict]:
    first = [e for e in events if e["is_first_touch"] and e["envelope_eligible"]]
    buckets: dict[tuple, list] = defaultdict(list)
    for row in first:
        for anchor, session in _strata(row):
            buckets[(row["population"], row["arm"], anchor, session)].append(row)
    out = []
    for (population, arm, anchor, session), rows in sorted(buckets.items()):
        left = [r for r in rows if r["envelope_left"]]
        minutes = sorted(r["envelope_minutes_inside"] for r in left)
        censored = sum(1 for r in rows if r["envelope_censored"])
        out.append(
            {
                "population": population,
                "arm": arm,
                "anchor": anchor,
                "session": session,
                "eligible_events": len(rows),
                "left_envelope": len(left),
                "censored": censored,
                "censored_pct": _pct(censored, len(rows)),
                "mean_minutes_inside": (
                    (sum(minutes) / Decimal(len(minutes))).quantize(Decimal("0.1"))
                    if minutes
                    else None
                ),
                "median_minutes_inside": minutes[len(minutes) // 2] if minutes else None,
                "p25_minutes": minutes[int(0.25 * (len(minutes) - 1))] if minutes else None,
                "p75_minutes": minutes[int(0.75 * (len(minutes) - 1))] if minutes else None,
                "p90_minutes": minutes[int(0.90 * (len(minutes) - 1))] if minutes else None,
                "underpowered": len(rows) < UNDERPOWERED_EPISODES,
            }
        )
    return out


def continuation_summary(events: list[dict]) -> list[dict]:
    """Continuation shares, split by approach side as the amendment requires."""
    first = [
        e
        for e in events
        if e["is_first_touch"]
        and e["approach_side"] in ("APPROACH_FROM_BELOW", "APPROACH_FROM_ABOVE")
    ]
    out = []
    for threshold in DISPLACEMENT_THRESHOLDS_ATR:
        key = f"{int(threshold)}atr"
        for horizon in CONTINUATION_HORIZONS_MINUTES:
            buckets: dict[tuple, list] = defaultdict(list)
            for row in first:
                if not row[f"continuation_evaluated_{key}_{horizon}m"]:
                    continue
                for anchor, session in _strata(row):
                    buckets[
                        (
                            row["population"],
                            row["arm"],
                            row["approach_side"],
                            anchor,
                            session,
                        )
                    ].append(row)
            for (population, arm, side, anchor, session), rows in sorted(buckets.items()):
                continued = sum(1 for r in rows if r[f"continued_{key}_{horizon}m"])
                returned = sum(1 for r in rows if r[f"returned_inside_after_{key}"])
                out.append(
                    {
                        "threshold": key,
                        "horizon_minutes": horizon,
                        "population": population,
                        "arm": arm,
                        "approach_side": side,
                        "anchor": anchor,
                        "session": session,
                        "evaluated_events": len(rows),
                        "continued": continued,
                        "continued_pct": _pct(continued, len(rows)),
                        "returned_inside": returned,
                        "returned_inside_pct": _pct(returned, len(rows)),
                        "underpowered": len(rows) < UNDERPOWERED_EPISODES,
                    }
                )
    return out


def write_table(path: Path, rows: list[dict], sort_by: tuple[str, ...]) -> None:
    fields = tuple(sorted({k for r in rows for k in r})) if rows else ("record_id",)
    keys = tuple(f for f in sort_by if f in fields)
    path.write_bytes(deterministic_csv_bytes(rows, fields, sort_by=keys))


def main(argv=None) -> None:
    args = parse_args(argv)
    output = args.output_root / f"year_{args.year}"
    output.mkdir(parents=True, exist_ok=True)

    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    archive, member = SOURCES[args.year]
    source = (args.data_root / archive).resolve()
    dataset_hash = archive_sha256(source)
    bars, audit = databento_rows_with_audit(
        source, member, allowed_year=args.year, dataset_sha256=dataset_hash
    )
    for bar in bars:
        if bar.start_time.year in FORBIDDEN_YEARS or bar.close_time.year in FORBIDDEN_YEARS:
            raise AssertionError(f"forbidden partition row parsed: {bar.source_row_id}")

    built = build(bars, year=args.year, code_sha=code_sha)
    events, intervals = built["events"], built["intervals"]

    write_deterministic_gzip_csv(
        output / "event_ledger.csv.gz",
        events,
        tuple(sorted({k for e in events for k in e})) if events else ("record_id",),
        sort_by=("event_id",) if events else (),
    )
    write_deterministic_gzip_csv(
        output / "interval_ledger.csv.gz",
        intervals,
        tuple(sorted({k for e in intervals for k in e})) if intervals else ("record_id",),
        sort_by=("interval_id",) if intervals else (),
    )
    write_table(
        output / "touch_population.csv",
        touch_population(intervals),
        ("population", "arm", "anchor"),
    )
    write_table(
        output / "displacement_distribution.csv",
        displacement_distribution(events),
        ("threshold", "population", "arm", "anchor", "session"),
    )
    write_table(
        output / "envelope_summary.csv",
        envelope_summary(events),
        ("population", "arm", "anchor", "session"),
    )
    write_table(
        output / "continuation_summary.csv",
        continuation_summary(events),
        ("threshold", "horizon_minutes", "population", "arm", "approach_side", "anchor", "session"),
    )

    first = [e for e in events if e["is_first_touch"]]
    manifest = {
        "generation": "STAGE_02_GENERATION_4_HVN_ZONES",
        "amendments": ["AMENDMENT_01", "AMENDMENT_02"],
        "year": args.year,
        "archive": archive,
        "dataset_sha256": dataset_hash,
        "code_sha": code_sha,
        "bars": len(bars),
        "profiles": built["profiles"],
        "intervals": len(intervals),
        "events": len(events),
        "first_touches": len(first),
        "retouches": len(events) - len(first),
        "ingestion_audit": {
            "parsed_years": sorted(audit.parsed_years),
            "rows_admitted": audit.rows_admitted,
            "rows_excluded_earlier_year": audit.rows_excluded_earlier_year,
            "rows_excluded_later_year": audit.rows_excluded_later_year,
            "forbidden_year_rows_admitted": 0,
        },
        "artifacts": {
            str(p.relative_to(output)): {
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in sorted(output.rglob("*"))
            if p.is_file() and p.name != "manifest.json"
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n"
    )
    print(json.dumps({k: v for k, v in manifest.items() if k != "artifacts"}, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
