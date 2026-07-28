"""Re-test displacement with buckets cut from the observed distribution.

The frozen buckets put 97% of events in one cell, so displacement was never
actually tested. The raw value is already in the event ledgers, so this is a
re-cut rather than a re-run.

Quartile cuts are taken from the **control** arm's distribution. The control arm
carries no treatment, so a cut derived from it cannot be shaped by the treated
result. Cuts are computed and printed before any continuation rate is read.
"""

from __future__ import annotations

import csv
import gzip
import json
from collections import defaultdict
from decimal import Decimal
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "outputs" / "stage_02_generation_4_study"
FULL_YEARS = (2019, 2021, 2023, 2025)
TREATED = "TREATED"
PRIMARY_CONTROL = "C02_ACTIVITY_MATCHED"
HORIZONS = (15, 30, 60)
MIN_EVENTS = 30
QUARTILES = ("Q1_smallest", "Q2", "Q3", "Q4_largest")


def is_true(value) -> bool:
    return str(value).lower() == "true"


def pct(n, d):
    return (Decimal(n) * 100 / Decimal(d)).quantize(Decimal("0.01")) if d else None


def quantile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def load():
    events = []
    for year in FULL_YEARS:
        with gzip.open(STUDY / f"year_{year}" / "event_ledger.csv.gz", "rt") as handle:
            for row in csv.DictReader(handle):
                if not is_true(row.get("is_first_touch")):
                    continue
                if not is_true(row.get("departure_impulse_evaluated")):
                    continue
                raw = row.get("departure_displacement_atr")
                if raw in ("", None):
                    continue
                row["year"] = int(row["year"])
                row["_disp"] = Decimal(raw)
                events.append(row)
    return events


def main() -> None:
    events = load()
    out_rows = []
    cuts_report = {}

    for population in ("NONPOC", "POC"):
        pool = [e for e in events if e["population"] == population]
        control_values = [e["_disp"] for e in pool if e["arm"] == PRIMARY_CONTROL]
        cuts = [quantile(control_values, f) for f in (0.25, 0.50, 0.75)]
        cuts_report[population] = {
            "control_events": len(control_values),
            "cuts_atr": [str(c) for c in cuts],
            "control_min": str(min(control_values)) if control_values else None,
            "control_max": str(max(control_values)) if control_values else None,
        }

        def bucket(value):
            if value <= cuts[0]:
                return QUARTILES[0]
            if value <= cuts[1]:
                return QUARTILES[1]
            if value <= cuts[2]:
                return QUARTILES[2]
            return QUARTILES[3]

        for label in QUARTILES:
            for horizon in HORIZONS:
                arms = {}
                for arm in (TREATED, PRIMARY_CONTROL):
                    cell = [
                        e
                        for e in pool
                        if e["arm"] == arm
                        and bucket(e["_disp"]) == label
                        and is_true(e[f"impulse_outcome_evaluated_{horizon}b"])
                    ]
                    continued = sum(
                        1 for e in cell if is_true(e[f"impulse_continued_{horizon}b"])
                    )
                    arms[arm] = {
                        "n": len(cell),
                        "share": pct(continued, len(cell)),
                        "median_disp": quantile([e["_disp"] for e in cell], 0.5),
                        "per_year": {
                            y: pct(
                                sum(
                                    1
                                    for e in cell
                                    if e["year"] == y
                                    and is_true(e[f"impulse_continued_{horizon}b"])
                                ),
                                sum(1 for e in cell if e["year"] == y),
                            )
                            for y in FULL_YEARS
                        },
                    }
                t, c = arms[TREATED], arms[PRIMARY_CONTROL]
                if t["share"] is None or c["share"] is None:
                    continue
                difference = t["share"] - c["share"]
                agreeing = sum(
                    1
                    for y in FULL_YEARS
                    if t["per_year"][y] is not None
                    and c["per_year"][y] is not None
                    and (t["per_year"][y] - c["per_year"][y]) * difference > 0
                )
                out_rows.append(
                    {
                        "population": population,
                        "displacement_quartile": label,
                        "horizon_bars": horizon,
                        "treated_events": t["n"],
                        "control_events": c["n"],
                        "treated_median_displacement_atr": (
                            t["median_disp"].quantize(Decimal("0.01"))
                            if t["median_disp"] is not None
                            else None
                        ),
                        "treated_continued_pct": t["share"],
                        "control_continued_pct": c["share"],
                        "difference_pp": difference,
                        "full_years_agreeing": f"{agreeing}/4",
                        "consistent": agreeing >= 3
                        and t["n"] >= MIN_EVENTS
                        and c["n"] >= MIN_EVENTS,
                    }
                )

    output = STUDY / "impulse"
    fields = list(out_rows[0])
    with (output / "displacement_recut.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in out_rows:
            writer.writerow({k: ("" if row[k] is None else row[k]) for k in fields})

    tested = len(out_rows)
    passing = sum(1 for r in out_rows if r["consistent"])
    chance = sum(comb(4, k) for k in (3, 4)) / 16
    summary = {
        "quartile_cuts_from_control_arm": cuts_report,
        "cells_tested": tested,
        "cells_passing_consistency": passing,
        "expected_passing_from_noise": round(tested * chance, 1),
    }
    (output / "displacement_recut_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    print()
    for row in out_rows:
        if row["horizon_bars"] != 30:
            continue
        print(
            f"{row['population']:7s} {row['displacement_quartile']:12s} "
            f"medDisp={row['treated_median_displacement_atr']:>7} ATR  "
            f"nT={row['treated_events']:>5} T={row['treated_continued_pct']:>6}% "
            f"C={row['control_continued_pct']:>6}% diff={row['difference_pp']:>7} "
            f"yrs={row['full_years_agreeing']}"
        )


if __name__ == "__main__":
    main()
