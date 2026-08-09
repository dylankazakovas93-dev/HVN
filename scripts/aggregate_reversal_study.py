"""Reversal or break-through by stack size, at 10, 30 and 120 minutes.

The question: price engages a level; does it turn back the way it came, or carry
through? And does stacking several kinds of level at the same price change the
answer?

Three guards, because each one killed an earlier version of this result:

  width strata   a wider band is mechanically easier to "revert" off when
                 distances are measured from its edges. Excursion here is
                 measured from the midpoint, which removes most of that, but
                 stacks are still wider on average, so degree is only ever
                 compared within a width band.

  year agreement counted over years that carry data in BOTH arms. Treating an
                 empty cell as a disagreement is what once made a two-year
                 result read as "2 of 4" and got a real effect dismissed.

  first touch    one barrier per price region per session. A level re-detected
                 at every anchor is one level, not several observations.
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
DEFAULT_STUDY = ROOT / "outputs" / "stage_05_reversal_study"
YEARS = (2019, 2021, 2023, 2025)
HORIZONS = (10, 30, 120)
WIDTH_BINS = (
    (Decimal("0.0"), Decimal("0.7")),
    (Decimal("0.7"), Decimal("1.2")),
    (Decimal("1.2"), Decimal("2.0")),
    (Decimal("2.0"), Decimal("3.1")),
)
MIN_EVENTS = 50
REVERSED = "REVERSED"
BROKE_THROUGH = "BROKE_THROUGH"


def is_true(value) -> bool:
    return str(value).lower() == "true"


def q(value, places="0.01"):
    return None if value is None else Decimal(value).quantize(Decimal(places))


def load(study: Path) -> list[dict]:
    """Tapped rows, reduced to one barrier per price region per session."""
    kept: list[dict] = []
    for year in YEARS:
        folder = study / f"year_{year}"
        if not folder.exists():
            continue
        rows = []
        for path in sorted(folder.glob("reversal_ledger*.csv.gz")):
            with gzip.open(path, "rt") as handle:
                for row in csv.DictReader(handle):
                    if not is_true(row.get("tapped")):
                        continue
                    row["year"] = year
                    rows.append(row)
        rows.sort(key=lambda r: (r["anchor_time"], r["band_low"]))
        spent: dict[tuple, list[tuple[Decimal, Decimal]]] = defaultdict(list)
        for row in rows:
            key = (
                row["session"], row["contract"], row["atr_timeframe"],
                row["tolerance_atr"], row["direction"],
            )
            low, high = Decimal(row["band_low"]), Decimal(row["band_high"])
            if any(low < b and a < high for a, b in spent[key]):
                continue
            spent[key].append((low, high))
            kept.append(row)
    return kept


def kinds(row) -> int:
    return int(row["level_kinds"])


def resolved_rate(rows, horizon: int):
    """Share of resolved outcomes that were reversals.

    Events still inside the band at the horizon are excluded rather than counted
    as either outcome: they have not resolved, and folding them into the
    denominator would let a slow, directionless drift dilute both arms unequally.
    """
    resolved = [
        r
        for r in rows
        if is_true(r.get(f"evaluated_{horizon}m"))
        and r.get(f"state_{horizon}m") in (REVERSED, BROKE_THROUGH)
    ]
    if not resolved:
        return None, 0
    hits = sum(1 for r in resolved if r[f"state_{horizon}m"] == REVERSED)
    return Decimal(100 * hits) / Decimal(len(resolved)), len(resolved)


def build(events: list[dict]) -> list[dict]:
    out = []
    for timeframe in sorted({e["atr_timeframe"] for e in events}):
        for tolerance in sorted({e["tolerance_atr"] for e in events}, key=Decimal):
            pool = [
                e
                for e in events
                if e["atr_timeframe"] == timeframe and e["tolerance_atr"] == tolerance
            ]
            for low, high in WIDTH_BINS:
                stratum = [
                    e for e in pool if low <= Decimal(e["width_atr"]) < high
                ]
                reference = [e for e in stratum if kinds(e) == 1]
                for horizon in HORIZONS:
                    base, base_n = resolved_rate(reference, horizon)
                    if base is None or base_n < MIN_EVENTS:
                        continue
                    for count in (1, 2, 3, 4):
                        rows = (
                            [e for e in stratum if kinds(e) == count]
                            if count < 4
                            else [e for e in stratum if kinds(e) >= 4]
                        )
                        rate, n = resolved_rate(rows, horizon)
                        if rate is None or n < MIN_EVENTS:
                            continue
                        difference = rate - base
                        agreeing = testable = 0
                        for year in YEARS:
                            a, an = resolved_rate(
                                [r for r in rows if r["year"] == year], horizon
                            )
                            b, bn = resolved_rate(
                                [r for r in reference if r["year"] == year], horizon
                            )
                            if a is None or b is None or an < 20 or bn < 20:
                                continue
                            testable += 1
                            if (a - b) * difference > 0:
                                agreeing += 1
                        favourable = [
                            Decimal(r[f"favourable_{horizon}m"])
                            for r in rows
                            if r.get(f"favourable_{horizon}m") not in ("", None)
                        ]
                        adverse = [
                            Decimal(r[f"adverse_{horizon}m"])
                            for r in rows
                            if r.get(f"adverse_{horizon}m") not in ("", None)
                        ]
                        out.append(
                            {
                                "atr_timeframe": timeframe,
                                "tolerance_atr": tolerance,
                                "width_bin": f"{low}-{high}",
                                "level_kinds": "4+" if count == 4 else count,
                                "horizon_min": horizon,
                                "resolved": n,
                                "reversal_pct": q(rate),
                                "vs_single_kind_pp": q(difference),
                                "mean_favourable_atr": q(
                                    sum(favourable) / len(favourable), "0.001"
                                )
                                if favourable
                                else None,
                                "mean_adverse_atr": q(
                                    sum(adverse) / len(adverse), "0.001"
                                )
                                if adverse
                                else None,
                                "years_agreeing": f"{agreeing}/{testable}",
                                "years_testable": testable,
                            }
                        )
    return out


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="aggregate_reversal_study.py")
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    args = parser.parse_args(argv)

    events = load(args.study)
    rows = build(events)
    output = args.study / "aggregate"
    output.mkdir(parents=True, exist_ok=True)
    if rows:
        with (output / "reversal_by_stack.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    stacked = [r for r in rows if r["level_kinds"] != 1 and r["years_testable"] >= 3]
    positive = [r for r in stacked if r["vs_single_kind_pp"] > 0]
    consistent = [
        r
        for r in stacked
        if int(r["years_agreeing"].split("/")[0]) >= r["years_testable"] - 1
    ]
    summary = {
        "first_touch_events": len(events),
        "cells": len(rows),
        "stacked_cells_testable": len(stacked),
        "stacked_cells_positive": len(positive),
        "stacked_cells_mostly_agreeing": len(consistent),
        "expected_agreeing_from_noise": round(len(stacked) * 5 / 16, 1),
        "sign_test_p": (
            round(
                sum(comb(len(stacked), i) for i in range(len(positive), len(stacked) + 1))
                / 2 ** len(stacked),
                6,
            )
            if stacked
            else None
        ),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
