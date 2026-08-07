"""Stage 4 aggregation: does agreement between sources change anything?

The claim under test is **monotonicity in confluence degree**, not the result of
any single cell. A confound would have to strengthen as more unrelated profile
constructions agree on a price, which is a hard thing for a confound to do — and
that is the only reason this design is worth running at all.

Three things are therefore reported together, always:

  counts       events per degree, per tolerance, per year, with the mean barrier
               width beside them. Width still creeps mildly with degree, and
               degree is the axis under test, so the width column is printed
               next to every result rather than buried.

  outcomes     excursion and rotation, treated against the distance-matched
               control, per degree.

  monotonic    whether the treated-minus-control difference rises with degree,
               stated as pass or fail before any individual cell is discussed.

Degree is compared only *within* a tolerance. A wider tolerance mechanically
raises degree, so a k=3 at 2.00 ATR is a different object from a k=3 at 0.25 ATR
and the tables never pool them.

The population is the first-touch reduction: one barrier per price region per
session, because a level re-detected at every hourly anchor is one level, not
six observations.
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
DEFAULT_STUDY = ROOT / "outputs" / "stage_04_confluence_study"
YEARS = (2019, 2021, 2023, 2025)
TREATED = "TREATED"
CONTROL = "CONTROL_DISTANCE_MATCHED"
DEGREES = (1, 2, 3, 4)  # 4 means "4 or more"
ROTATION_DEADLINES = (5, 20, 60)
MIN_EVENTS = 30


def is_true(value) -> bool:
    return str(value).lower() == "true"


def q3(value):
    return None if value is None else Decimal(value).quantize(Decimal("0.001"))


def mean(values):
    return sum(values) / Decimal(len(values)) if values else None


def degree_bucket(degree: int) -> int:
    return min(degree, 4)


def load_first_touch(study: Path) -> list[dict]:
    """Tapped rows reduced to one per price region per session per config.

    A barrier is re-detected at every hourly anchor. Keeping every detection
    would inflate the denominator and make correlated observations look like
    independent evidence, which is the mistake Stage 3 had to unwind.
    """
    kept: list[dict] = []
    for year in YEARS:
        path = study / f"year_{year}" / "confluence_ledger.csv.gz"
        if not path.exists():
            continue
        rows = []
        with gzip.open(path, "rt") as handle:
            for row in csv.DictReader(handle):
                if not is_true(row.get("tapped")):
                    continue
                row["year"] = year
                rows.append(row)
        rows.sort(key=lambda r: (r["anchor_time"], r["arm"], r["band_low"]))
        spent: dict[tuple, list[tuple[Decimal, Decimal]]] = defaultdict(list)
        for row in rows:
            key = (
                row["session"],
                row["contract"],
                row["arm"],
                row["atr_timeframe"],
                row["tolerance_atr"],
                row["direction"],
            )
            low, high = Decimal(row["band_low"]), Decimal(row["band_high"])
            if any(low < b and a < high for a, b in spent[key]):
                continue
            spent[key].append((low, high))
            kept.append(row)
    return kept


def _series(rows, field):
    return [
        Decimal(r[field]) for r in rows if r.get(field) not in ("", None)
    ]


def counts_table(events: list[dict]) -> list[dict]:
    out = []
    for timeframe in sorted({e["atr_timeframe"] for e in events}):
        for tolerance in sorted({e["tolerance_atr"] for e in events}, key=Decimal):
            for degree in DEGREES:
                rows = [
                    e
                    for e in events
                    if e["atr_timeframe"] == timeframe
                    and e["tolerance_atr"] == tolerance
                    and e["arm"] == TREATED
                    and degree_bucket(int(e["degree"])) == degree
                ]
                if not rows:
                    continue
                out.append(
                    {
                        "atr_timeframe": timeframe,
                        "tolerance_atr": tolerance,
                        "degree": "4+" if degree == 4 else degree,
                        "events": len(rows),
                        "mean_width_atr": q3(mean(_series(rows, "width_atr"))),
                        "mean_distance_atr": q3(mean(_series(rows, "distance_atr"))),
                        **{
                            f"n_{y}": sum(1 for r in rows if r["year"] == y)
                            for y in YEARS
                        },
                    }
                )
    return out


def _arm_stat(events, timeframe, tolerance, degree, arm, statistic):
    rows = [
        e
        for e in events
        if e["atr_timeframe"] == timeframe
        and e["tolerance_atr"] == tolerance
        and e["arm"] == arm
        and (arm == CONTROL or degree_bucket(int(e["degree"])) == degree)
    ]
    return rows, statistic(rows)


def outcome_table(events: list[dict], metric: str, statistic) -> list[dict]:
    """One metric, treated against control, per degree, with per-year signs."""
    out = []
    for timeframe in sorted({e["atr_timeframe"] for e in events}):
        for tolerance in sorted({e["tolerance_atr"] for e in events}, key=Decimal):
            for degree in DEGREES:
                treated_rows, treated = _arm_stat(
                    events, timeframe, tolerance, degree, TREATED, statistic
                )
                control_rows, control = _arm_stat(
                    events, timeframe, tolerance, degree, CONTROL, statistic
                )
                if treated is None or control is None or not treated_rows:
                    continue
                difference = treated - control
                agreeing = 0
                for year in YEARS:
                    t = statistic([r for r in treated_rows if r["year"] == year])
                    c = statistic([r for r in control_rows if r["year"] == year])
                    if t is None or c is None:
                        continue
                    if (t - c) * difference > 0:
                        agreeing += 1
                out.append(
                    {
                        "metric": metric,
                        "atr_timeframe": timeframe,
                        "tolerance_atr": tolerance,
                        "degree": "4+" if degree == 4 else degree,
                        "treated_events": len(treated_rows),
                        "control_events": len(control_rows),
                        "treated": q3(treated),
                        "control": q3(control),
                        "difference": q3(difference),
                        "years_agreeing": f"{agreeing}/4",
                        "supported": len(treated_rows) >= MIN_EVENTS
                        and len(control_rows) >= MIN_EVENTS,
                    }
                )
    return out


def monotonicity(rows: list[dict]) -> list[dict]:
    """Does the treated-minus-control difference rise with degree?

    Stated as pass or fail per configuration, before any cell is discussed. If
    the differences are flat across degree, confluence adds nothing regardless
    of how good any single cell looks.
    """
    out = []
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["metric"], row["atr_timeframe"], row["tolerance_atr"])].append(row)
    for (metric, timeframe, tolerance), cells in sorted(grouped.items()):
        ordered = [
            c
            for c in sorted(cells, key=lambda c: str(c["degree"]))
            if c["supported"] and c["difference"] is not None
        ]
        if len(ordered) < 3:
            out.append(
                {
                    "metric": metric,
                    "atr_timeframe": timeframe,
                    "tolerance_atr": tolerance,
                    "degrees_supported": len(ordered),
                    "verdict": "UNTESTABLE_TOO_FEW_DEGREES",
                }
            )
            continue
        values = [c["difference"] for c in ordered]
        rising = all(b >= a for a, b in zip(values, values[1:], strict=False))
        out.append(
            {
                "metric": metric,
                "atr_timeframe": timeframe,
                "tolerance_atr": tolerance,
                "degrees_supported": len(ordered),
                "first_degree_difference": values[0],
                "last_degree_difference": values[-1],
                "span": q3(values[-1] - values[0]),
                "verdict": "MONOTONIC_RISING" if rising else "NOT_MONOTONIC",
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
            writer.writerow(
                {k: ("" if row.get(k) is None else row.get(k)) for k in fields}
            )


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="aggregate_confluence_study.py")
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    args = parser.parse_args(argv)

    events = load_first_touch(args.study)
    output = args.study / "aggregate"
    output.mkdir(parents=True, exist_ok=True)

    def excursion(rows):
        return mean(_series(rows, "max_excursion_atr"))

    outcomes = outcome_table(events, "mean_excursion_atr", excursion)
    for deadline in ROTATION_DEADLINES:

        def rotated(rows, _d=deadline):
            usable = [r for r in rows if not is_true(r.get(f"censored_{_d}b"))]
            if not usable:
                return None
            hits = sum(1 for r in usable if is_true(r.get(f"rotated_{_d}b")))
            return Decimal(hits) * 100 / Decimal(len(usable))

        outcomes += outcome_table(events, f"rotated_{deadline}b_pct", rotated)

    verdicts = monotonicity(outcomes)
    write(output / "counts.csv", counts_table(events))
    write(output / "outcomes.csv", outcomes)
    write(output / "monotonicity.csv", verdicts)

    chance = sum(comb(4, k) for k in (3, 4)) / 16
    supported = [r for r in outcomes if r["supported"]]
    summary = {
        "first_touch_events": len(events),
        "years": [y for y in YEARS if any(e["year"] == y for e in events)],
        "cells_tested": len(outcomes),
        "cells_supported": len(supported),
        "cells_with_3of4_year_agreement": sum(
            1 for r in supported if r["years_agreeing"] in ("3/4", "4/4")
        ),
        "expected_agreeing_from_noise": round(len(supported) * chance, 1),
        "monotonic_rising": sum(1 for v in verdicts if v["verdict"] == "MONOTONIC_RISING"),
        "not_monotonic": sum(1 for v in verdicts if v["verdict"] == "NOT_MONOTONIC"),
        "untestable": sum(1 for v in verdicts if v["verdict"].startswith("UNTESTABLE")),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
