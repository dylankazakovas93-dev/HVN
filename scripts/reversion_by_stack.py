"""Do stacked levels reverse price more often than singular ones?

The Stage 4 tables measured travel *away* from a level. This measures the
opposite and simpler thing: price approaches a barrier, and either turns back
the way it came (reversion) or carries through it (continuation). A barrier
sitting above price was approached from below, so a subsequent move down is a
reversion and a move up is a continuation.

Stacking is counted as **distinct level kinds** in the cluster, not sources: an
LVN plus a TPO extreme plus a sigma edge is three kinds, whatever profiles they
came from.

Width is stratified, not pooled, because it is a mechanical confound that tracks
the test axis. Excursion is measured from the band edge, so a wider band needs
more travel to be broken through and will look more "reversion-prone" for
reasons that have nothing to do with confluence. Comparing within a width
stratum removes that.

This comparison is entirely within the treated arm, so it does not depend on the
Stage 4 control, which is distance-mismatched and unusable for absolute claims.
"""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal
from pathlib import Path

from aggregate_confluence_study import TREATED, load_first_touch

YEARS = (2019, 2021, 2023, 2025)
WIDTH_BINS = (
    (Decimal("0.4"), Decimal("0.7")),
    (Decimal("0.7"), Decimal("1.0")),
    (Decimal("1.0"), Decimal("1.5")),
    (Decimal("1.5"), Decimal("2.0")),
)
MIN_EVENTS = 50


def reverted(event) -> bool:
    return (
        event["direction"] == "ABOVE" and event["max_excursion_direction"] == "DOWN"
    ) or (event["direction"] == "BELOW" and event["max_excursion_direction"] == "UP")


def rate(rows):
    if not rows:
        return None
    return Decimal(100 * sum(1 for r in rows if reverted(r))) / Decimal(len(rows))


def kind_count(event) -> int:
    return len(set(event["kinds"].split("|")))


def build(events) -> list[dict]:
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
                reference = [e for e in stratum if kind_count(e) == 1]
                if len(reference) < MIN_EVENTS:
                    continue
                base = rate(reference)
                for kinds in (1, 2, 3, 4):
                    rows = (
                        [e for e in stratum if kind_count(e) == kinds]
                        if kinds < 4
                        else [e for e in stratum if kind_count(e) >= 4]
                    )
                    if len(rows) < MIN_EVENTS:
                        continue
                    value = rate(rows)
                    difference = value - base
                    # Count only years carrying data in BOTH arms. A year with
                    # an empty cell did not disagree, and conflating the two
                    # understates a real effect — the mistake that made a
                    # two-year result read as "2 of 4".
                    agreeing = 0
                    testable = 0
                    for year in YEARS:
                        a = rate([r for r in rows if r["year"] == year])
                        b = rate([r for r in reference if r["year"] == year])
                        if a is None or b is None:
                            continue
                        testable += 1
                        if (a - b) * difference > 0:
                            agreeing += 1
                    out.append(
                        {
                            "atr_timeframe": timeframe,
                            "tolerance_atr": tolerance,
                            "width_bin": f"{low}-{high}",
                            "level_kinds": "4+" if kinds == 4 else kinds,
                            "events": len(rows),
                            "reversion_pct": value.quantize(Decimal("0.01")),
                            "vs_single_kind_pp": difference.quantize(Decimal("0.01")),
                            "years_agreeing": f"{agreeing}/{testable}",
                            "years_testable": testable,
                        }
                    )
    return out


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="reversion_by_stack.py")
    parser.add_argument(
        "--study",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "outputs"
        / "stage_04_confluence_study",
    )
    args = parser.parse_args(argv)

    events = [
        e
        for e in load_first_touch(args.study)
        if e["arm"] == TREATED and e.get("max_excursion_direction") in ("UP", "DOWN")
    ]
    rows = build(events)
    output = args.study / "aggregate"
    output.mkdir(parents=True, exist_ok=True)
    with (output / "reversion_by_stack.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    stacked = [r for r in rows if r["level_kinds"] != 1]
    full = [r for r in stacked if r["years_testable"] >= 2]
    unanimous = [
        r for r in full
        if r["years_agreeing"].split("/")[0] == str(r["years_testable"])
    ]
    print(f"cells: {len(stacked)}  testable in 2+ years: {len(full)}")
    print(f"cells where every testable year agrees: {len(unanimous)}")
    for row in sorted(full, key=lambda r: -float(r["vs_single_kind_pp"]))[:14]:
        print(
            f"  tf{row['atr_timeframe']} tol{row['tolerance_atr']} "
            f"w{row['width_bin']} kinds={row['level_kinds']} n={row['events']} "
            f"rev={row['reversion_pct']}% vs1={row['vs_single_kind_pp']}pp "
            f"years={row['years_agreeing']}"
        )


if __name__ == "__main__":
    main()
