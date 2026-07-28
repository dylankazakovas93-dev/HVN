"""Does an abnormal directional impulse away from an HVN zone continue or revert?

Reads the per-year event ledgers and reports continuation against reversion in
the frozen impulse buckets, treated beside both control arms, with the per-year
direction on every pooled figure.

Every cell is written, winners and losers alike. A cell is only called
consistent when the treated-minus-control sign holds in at least three of the
four full development years.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STUDY = ROOT / "outputs" / "stage_02_generation_4_study"
FULL_YEARS = (2019, 2021, 2023, 2025)
TREATED = "TREATED"
CONTROLS = ("C01_NEUTRAL", "C02_ACTIVITY_MATCHED")
PRIMARY_CONTROL = "C02_ACTIVITY_MATCHED"
HORIZONS = (15, 30, 60)
MIN_EVENTS = 30

VOLUME_ORDER = ("below_normal", "normal", "elevated", "extreme")
DISPLACEMENT_ORDER = ("lt_0.5", "0.5_1.0", "1.0_1.5", "gt_1.5")
EFFICIENCY_ORDER = ("low", "medium", "high")
DWELL_ORDER = ("0-2", "3-6", "7-12", "13+")


def read_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt") as handle:
        return list(csv.DictReader(handle))


def is_true(value) -> bool:
    return str(value).lower() == "true"


def pct(numerator: int, denominator: int) -> Decimal | None:
    if not denominator:
        return None
    return (Decimal(numerator) * Decimal(100) / Decimal(denominator)).quantize(
        Decimal("0.01")
    )


def load(study: Path) -> list[dict]:
    events: list[dict] = []
    for year in FULL_YEARS:
        for row in read_gz(study / f"year_{year}" / "event_ledger.csv.gz"):
            row["year"] = int(row["year"])
            if not is_true(row.get("is_first_touch")):
                continue
            if not is_true(row.get("departure_impulse_evaluated")):
                continue
            events.append(row)
    return events


def _continuation(rows: list[dict], horizon: int) -> tuple[int, int, Decimal | None]:
    evaluated = [r for r in rows if is_true(r[f"impulse_outcome_evaluated_{horizon}b"])]
    continued = sum(1 for r in evaluated if is_true(r[f"impulse_continued_{horizon}b"]))
    return len(evaluated), continued, pct(continued, len(evaluated))


def _cell_rows(events, key_fields, order_maps):
    """Group events by the given bucket fields, in the frozen bucket order."""
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in events:
        key = tuple(row.get(field, "undefined") for field in key_fields)
        grouped[key].append(row)

    def sort_key(key):
        out = []
        for value, order in zip(key, order_maps):
            out.append(order.index(value) if value in order else len(order))
        return tuple(out) + key
    return [(key, grouped[key]) for key in sorted(grouped, key=sort_key)]


def bucket_table(events: list[dict], key_fields, order_maps, labels) -> list[dict]:
    """Continuation by bucket, treated against each control, with year signs."""
    out = []
    for population in ("NONPOC", "POC"):
        population_rows = [e for e in events if e["population"] == population]
        by_arm = {
            arm: [e for e in population_rows if e["arm"] == arm]
            for arm in (TREATED, *CONTROLS)
        }
        keys = {k for k, _ in _cell_rows(population_rows, key_fields, order_maps)}
        for key, _ in _cell_rows(population_rows, key_fields, order_maps):
            if key not in keys:
                continue
            keys.discard(key)
            for horizon in HORIZONS:
                arms = {}
                for arm, rows in by_arm.items():
                    cell = [
                        r
                        for r in rows
                        if tuple(r.get(f, "undefined") for f in key_fields) == key
                    ]
                    evaluated, continued, share = _continuation(cell, horizon)
                    arms[arm] = {
                        "events": evaluated,
                        "continued": continued,
                        "share": share,
                        "per_year": {
                            year: _continuation(
                                [r for r in cell if r["year"] == year], horizon
                            )[2]
                            for year in FULL_YEARS
                        },
                    }
                treated = arms[TREATED]
                for arm in CONTROLS:
                    control = arms[arm]
                    if treated["share"] is None or control["share"] is None:
                        continue
                    difference = treated["share"] - control["share"]
                    agreeing = sum(
                        1
                        for year in FULL_YEARS
                        if treated["per_year"][year] is not None
                        and control["per_year"][year] is not None
                        and (treated["per_year"][year] - control["per_year"][year])
                        * difference
                        > 0
                    )
                    row = {
                        "population": population,
                        **dict(zip(labels, key)),
                        "horizon_bars": horizon,
                        "control_arm": arm,
                        "treated_events": treated["events"],
                        "control_events": control["events"],
                        "treated_continued_pct": treated["share"],
                        "control_continued_pct": control["share"],
                        "difference_pp": difference,
                        "full_years_agreeing": f"{agreeing}/4",
                        "consistent": agreeing >= 3
                        and treated["events"] >= MIN_EVENTS
                        and control["events"] >= MIN_EVENTS,
                        "underpowered": treated["events"] < MIN_EVENTS
                        or control["events"] < MIN_EVENTS,
                    }
                    for year in FULL_YEARS:
                        row[f"treated_{year}"] = treated["per_year"][year]
                    out.append(row)
    return out


def baseline_table(events: list[dict]) -> list[dict]:
    """Continuation with no conditioning, so every cell has something to beat."""
    out = []
    for population in ("NONPOC", "POC"):
        for arm in (TREATED, *CONTROLS):
            rows = [
                e
                for e in events
                if e["population"] == population and e["arm"] == arm
            ]
            for horizon in HORIZONS:
                evaluated, continued, share = _continuation(rows, horizon)
                out.append(
                    {
                        "population": population,
                        "arm": arm,
                        "horizon_bars": horizon,
                        "events": evaluated,
                        "continued": continued,
                        "continued_pct": share,
                    }
                )
    return out


def coverage_table(events: list[dict]) -> list[dict]:
    """How many events actually carry a seasonal volume baseline."""
    out = []
    for population in ("NONPOC", "POC"):
        for arm in (TREATED, *CONTROLS):
            rows = [
                e for e in events if e["population"] == population and e["arm"] == arm
            ]
            with_baseline = sum(
                1 for r in rows if is_true(r.get("departure_seasonal_baseline"))
            )
            defined = sum(
                1 for r in rows if r.get("departure_volume_bucket") not in ("undefined", "", None)
            )
            out.append(
                {
                    "population": population,
                    "arm": arm,
                    "events": len(rows),
                    "with_seasonal_baseline": with_baseline,
                    "baseline_coverage_pct": pct(with_baseline, len(rows)),
                    "volume_bucket_defined": defined,
                    "bucket_coverage_pct": pct(defined, len(rows)),
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
    parser = argparse.ArgumentParser(prog="aggregate_gen5_impulse.py")
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    args = parser.parse_args(argv)

    events = load(args.study)
    output = args.study / "impulse"
    output.mkdir(parents=True, exist_ok=True)

    write(output / "baseline_continuation.csv", baseline_table(events))
    write(output / "seasonal_coverage.csv", coverage_table(events))
    write(
        output / "by_volume.csv",
        bucket_table(events, ("departure_volume_bucket",), (VOLUME_ORDER,), ("volume",)),
    )
    write(
        output / "by_displacement.csv",
        bucket_table(
            events, ("departure_displacement_bucket",), (DISPLACEMENT_ORDER,), ("displacement",)
        ),
    )
    write(
        output / "by_efficiency.csv",
        bucket_table(
            events, ("departure_efficiency_bucket",), (EFFICIENCY_ORDER,), ("efficiency",)
        ),
    )
    write(
        output / "by_dwell.csv",
        bucket_table(events, ("dwell_bucket",), (DWELL_ORDER,), ("dwell",)),
    )
    write(
        output / "by_volume_and_displacement.csv",
        bucket_table(
            events,
            ("departure_volume_bucket", "departure_displacement_bucket"),
            (VOLUME_ORDER, DISPLACEMENT_ORDER),
            ("volume", "displacement"),
        ),
    )
    write(
        output / "by_volume_displacement_efficiency.csv",
        bucket_table(
            events,
            (
                "departure_volume_bucket",
                "departure_displacement_bucket",
                "departure_efficiency_bucket",
            ),
            (VOLUME_ORDER, DISPLACEMENT_ORDER, EFFICIENCY_ORDER),
            ("volume", "displacement", "efficiency"),
        ),
    )
    write(
        output / "by_anchor_and_volume.csv",
        bucket_table(
            events,
            ("relationship_id", "departure_volume_bucket"),
            ((), VOLUME_ORDER),
            ("anchor", "volume"),
        ),
    )

    summary = {
        "first_touch_events_with_impulse": len(events),
        "full_years": list(FULL_YEARS),
        "primary_control": PRIMARY_CONTROL,
        "horizons_bars": list(HORIZONS),
        "minimum_events_per_cell": MIN_EVENTS,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
