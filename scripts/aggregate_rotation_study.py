"""Pool the rotation partitions: does a node rotate differently from a control?

Reports the rotation grid — distance crossed with deadline, so each cell is a
speed — for high and low nodes against their width-matched controls, with the
per-year direction beside every pooled figure.

Every cell is written, winners and losers. A cell counts as consistent only when
the treated-minus-control sign holds in at least three of the four years and
both arms carry enough events. The chance rate for that filter is reported
beside the pass count, because with a grid this size a null produces passes.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import defaultdict
from decimal import Decimal
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STUDY = ROOT / "outputs" / "stage_03_rotation_study"
YEARS = (2019, 2021, 2023, 2025)
TREATED = "TREATED"
CONTROL = "CONTROL_WIDTH_MATCHED"
DISTANCES = ("0.5", "1", "2", "3")
DEADLINES = (3, 5, 10)
SUSTAINS = (5, 10, 20)
MIN_EVENTS = 30


def is_true(value) -> bool:
    return str(value).lower() == "true"


def pct(n, d):
    return (Decimal(n) * 100 / Decimal(d)).quantize(Decimal("0.01")) if d else None


def quantile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def load(study: Path) -> list[dict]:
    rows: list[dict] = []
    for year in YEARS:
        path = study / f"year_{year}" / "rotation_ledger.csv.gz"
        if not path.exists():
            continue
        with gzip.open(path, "rt") as handle:
            for row in csv.DictReader(handle):
                if not is_true(row.get("tapped")):
                    continue
                row["year"] = int(row["year"])
                rows.append(row)
    return rows


def _rate(rows, field):
    hits = sum(1 for r in rows if is_true(r.get(field)))
    return len(rows), hits, pct(hits, len(rows))


def tap_population(study: Path) -> list[dict]:
    """Tap rates with their denominator, from the untapped rows too."""
    out = []
    totals: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for year in YEARS:
        path = study / f"year_{year}" / "rotation_ledger.csv.gz"
        if not path.exists():
            continue
        with gzip.open(path, "rt") as handle:
            for row in csv.DictReader(handle):
                key = (row["arm"], row["node_class"])
                totals[key][0] += 1
                if is_true(row.get("tapped")):
                    totals[key][1] += 1
    for (arm, node_class), (nodes, tapped) in sorted(totals.items()):
        out.append(
            {
                "arm": arm,
                "node_class": node_class,
                "nodes": nodes,
                "tapped": tapped,
                "tap_rate_pct": pct(tapped, nodes),
            }
        )
    return out


def rotation_grid(events: list[dict]) -> list[dict]:
    """Rotation rate per distance-by-deadline cell, treated against control."""
    out = []
    for node_class in ("HIGH_VOLUME_NODE", "LOW_VOLUME_NODE"):
        pool = [e for e in events if e["node_class"] == node_class]
        for distance in DISTANCES:
            for deadline in DEADLINES:
                field = f"rotated_{distance}atr_{deadline}b"
                if not pool or field not in pool[0]:
                    continue
                arms = {}
                for arm in (TREATED, CONTROL):
                    rows = [
                        e
                        for e in pool
                        if e["arm"] == arm
                        and not is_true(e.get(f"censored_{distance}atr_{deadline}b"))
                    ]
                    total, hits, share = _rate(rows, field)
                    arms[arm] = {
                        "n": total,
                        "share": share,
                        "per_year": {
                            y: _rate([r for r in rows if r["year"] == y], field)[2]
                            for y in YEARS
                        },
                    }
                t, c = arms[TREATED], arms[CONTROL]
                if t["share"] is None or c["share"] is None:
                    continue
                difference = t["share"] - c["share"]
                agreeing = sum(
                    1
                    for y in YEARS
                    if t["per_year"][y] is not None
                    and c["per_year"][y] is not None
                    and (t["per_year"][y] - c["per_year"][y]) * difference > 0
                )
                out.append(
                    {
                        "node_class": node_class,
                        "distance_atr": distance,
                        "deadline_bars": deadline,
                        "treated_events": t["n"],
                        "control_events": c["n"],
                        "treated_rotated_pct": t["share"],
                        "control_rotated_pct": c["share"],
                        "difference_pp": difference,
                        "full_years_agreeing": f"{agreeing}/4",
                        "consistent": agreeing >= 3
                        and t["n"] >= MIN_EVENTS
                        and c["n"] >= MIN_EVENTS,
                    }
                )
    return out


def sustain_table(events: list[dict]) -> list[dict]:
    """Of the rotations that happened, how many held?"""
    out = []
    for node_class in ("HIGH_VOLUME_NODE", "LOW_VOLUME_NODE"):
        pool = [e for e in events if e["node_class"] == node_class]
        for distance in DISTANCES:
            for deadline in DEADLINES:
                key = f"{distance}atr_{deadline}b"
                for horizon in SUSTAINS:
                    field = f"sustained_{key}_{horizon}b"
                    guard = f"sustain_evaluated_{key}_{horizon}b"
                    if not pool or field not in pool[0]:
                        continue
                    arms = {}
                    for arm in (TREATED, CONTROL):
                        rows = [
                            e
                            for e in pool
                            if e["arm"] == arm and is_true(e.get(guard))
                        ]
                        total, hits, share = _rate(rows, field)
                        arms[arm] = {
                            "n": total,
                            "share": share,
                            "per_year": {
                                y: _rate([r for r in rows if r["year"] == y], field)[2]
                                for y in YEARS
                            },
                        }
                    t, c = arms[TREATED], arms[CONTROL]
                    if t["share"] is None or c["share"] is None:
                        continue
                    difference = t["share"] - c["share"]
                    agreeing = sum(
                        1
                        for y in YEARS
                        if t["per_year"][y] is not None
                        and c["per_year"][y] is not None
                        and (t["per_year"][y] - c["per_year"][y]) * difference > 0
                    )
                    out.append(
                        {
                            "node_class": node_class,
                            "distance_atr": distance,
                            "deadline_bars": deadline,
                            "sustain_bars": horizon,
                            "treated_rotations": t["n"],
                            "control_rotations": c["n"],
                            "treated_sustained_pct": t["share"],
                            "control_sustained_pct": c["share"],
                            "difference_pp": difference,
                            "full_years_agreeing": f"{agreeing}/4",
                            "consistent": agreeing >= 3
                            and t["n"] >= MIN_EVENTS
                            and c["n"] >= MIN_EVENTS,
                        }
                    )
    return out


def excursion_table(events: list[dict]) -> list[dict]:
    """The continuous view: how far and how fast, without any threshold."""
    out = []
    for node_class in ("HIGH_VOLUME_NODE", "LOW_VOLUME_NODE"):
        arms = {}
        for arm in (TREATED, CONTROL):
            rows = [
                e
                for e in events
                if e["node_class"] == node_class
                and e["arm"] == arm
                and e.get("max_excursion_atr") not in ("", None)
            ]
            distances = [Decimal(e["max_excursion_atr"]) for e in rows]
            rates = [
                Decimal(e["max_excursion_rate"])
                for e in rows
                if e.get("max_excursion_rate") not in ("", None)
            ]
            arms[arm] = {
                "n": len(rows),
                "median": quantile(distances, 0.5),
                "p90": quantile(distances, 0.9),
                "median_rate": quantile(rates, 0.5),
                "per_year": {
                    y: quantile(
                        [
                            Decimal(e["max_excursion_atr"])
                            for e in rows
                            if e["year"] == y
                        ],
                        0.5,
                    )
                    for y in YEARS
                },
            }
        t, c = arms[TREATED], arms[CONTROL]
        if t["median"] is None or c["median"] is None:
            continue
        difference = t["median"] - c["median"]
        agreeing = sum(
            1
            for y in YEARS
            if t["per_year"][y] is not None
            and c["per_year"][y] is not None
            and (t["per_year"][y] - c["per_year"][y]) * difference > 0
        )
        out.append(
            {
                "node_class": node_class,
                "treated_events": t["n"],
                "control_events": c["n"],
                "treated_median_excursion_atr": t["median"].quantize(Decimal("0.001")),
                "control_median_excursion_atr": c["median"].quantize(Decimal("0.001")),
                "treated_p90_atr": t["p90"].quantize(Decimal("0.001")),
                "control_p90_atr": c["p90"].quantize(Decimal("0.001")),
                "treated_median_rate": (
                    t["median_rate"].quantize(Decimal("0.001"))
                    if t["median_rate"] is not None
                    else None
                ),
                "control_median_rate": (
                    c["median_rate"].quantize(Decimal("0.001"))
                    if c["median_rate"] is not None
                    else None
                ),
                "full_years_agreeing": f"{agreeing}/4",
            }
        )
    return out


def q(value):
    return None if value is None else value.quantize(Decimal("0.001"))


def mean(values):
    if not values:
        return None
    return sum(values) / Decimal(len(values))


def quality_table(events: list[dict]) -> list[dict]:
    """Conditional on a rotation happening, how long did it hold and how far?

    "A high node rotates less often" is the theory restating itself. This table
    conditions on the rotation and asks whether the ones that do happen last
    longer or travel further than a control's — the question that is not
    circular. The denominator is rotations, not taps, so every cell here is a
    strictly smaller sample than the corresponding rotation-grid cell.
    """
    out = []
    for node_class in ("HIGH_VOLUME_NODE", "LOW_VOLUME_NODE"):
        pool = [e for e in events if e["node_class"] == node_class]
        for distance in DISTANCES:
            for deadline in DEADLINES:
                key = f"{distance}atr_{deadline}b"
                guard = f"quality_evaluated_{key}"
                if not pool or guard not in pool[0]:
                    continue
                arms = {}
                for arm in (TREATED, CONTROL):
                    rows = [
                        e for e in pool if e["arm"] == arm and is_true(e.get(guard))
                    ]

                    def series(subset, field):
                        return [
                            Decimal(r[field])
                            for r in subset
                            if r.get(field) not in ("", None)
                        ]

                    arms[arm] = {
                        "n": len(rows),
                        "held": mean(series(rows, f"bars_held_{key}")),
                        "extension": mean(series(rows, f"further_extension_{key}")),
                        "held_per_year": {
                            y: mean(
                                series(
                                    [r for r in rows if r["year"] == y],
                                    f"bars_held_{key}",
                                )
                            )
                            for y in YEARS
                        },
                        "extension_per_year": {
                            y: mean(
                                series(
                                    [r for r in rows if r["year"] == y],
                                    f"further_extension_{key}",
                                )
                            )
                            for y in YEARS
                        },
                    }
                t, c = arms[TREATED], arms[CONTROL]
                if t["held"] is None or c["held"] is None:
                    continue

                def agree(field):
                    diff = t[field] - c[field]
                    per = f"{field}_per_year"
                    return diff, sum(
                        1
                        for y in YEARS
                        if t[per][y] is not None
                        and c[per][y] is not None
                        and (t[per][y] - c[per][y]) * diff > 0
                    )

                held_diff, held_agreeing = agree("held")
                if t["extension"] is None or c["extension"] is None:
                    ext_diff, ext_agreeing = None, 0
                else:
                    ext_diff, ext_agreeing = agree("extension")
                out.append(
                    {
                        "node_class": node_class,
                        "distance_atr": distance,
                        "deadline_bars": deadline,
                        "treated_rotations": t["n"],
                        "control_rotations": c["n"],
                        "treated_mean_bars_held": q(t["held"]),
                        "control_mean_bars_held": q(c["held"]),
                        "bars_held_difference": q(held_diff),
                        "bars_held_years_agreeing": f"{held_agreeing}/4",
                        "treated_mean_further_extension_atr": q(t["extension"]),
                        "control_mean_further_extension_atr": q(c["extension"]),
                        "further_extension_difference_atr": q(ext_diff),
                        "further_extension_years_agreeing": f"{ext_agreeing}/4",
                        "consistent": held_agreeing >= 3
                        and t["n"] >= MIN_EVENTS
                        and c["n"] >= MIN_EVENTS,
                    }
                )
    return out


def write(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="aggregate_rotation_study.py")
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    args = parser.parse_args(argv)

    events = load(args.study)
    output = args.study / "aggregate"
    output.mkdir(parents=True, exist_ok=True)

    grid = rotation_grid(events)
    sustain = sustain_table(events)
    write(output / "tap_population.csv", tap_population(args.study))
    write(output / "rotation_grid.csv", grid)
    write(output / "sustain.csv", sustain)
    write(output / "max_excursion.csv", excursion_table(events))
    quality = quality_table(events)
    write(output / "rotation_quality.csv", quality)

    chance = sum(comb(4, k) for k in (3, 4)) / 16
    cells = len(grid) + len(sustain)
    passing = sum(1 for r in grid + sustain if r["consistent"])
    summary = {
        "tapped_events": len(events),
        "years": list(YEARS),
        "cells_tested": cells,
        "cells_passing_consistency": passing,
        "expected_passing_from_noise": round(cells * chance, 1),
        "quality_cells_tested": len(quality),
        "quality_cells_passing": sum(1 for r in quality if r["consistent"]),
        "quality_expected_from_noise": round(len(quality) * chance, 1),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
