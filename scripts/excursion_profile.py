"""The excursion distribution at fine granularity, node class against control.

`max_excursion_atr` was recorded continuously and without reference to any
threshold, precisely so the grid could be re-cut afterwards without touching
source bars. This script cuts it three ways:

  quantiles   the shape of the distribution, every 5th percentile
  exceedance  P(max excursion >= d) on a 0.25 ATR ladder
  moments     mean and count, with the per-year sign of the difference

Re-cutting a recorded distribution is description, not a threshold search. No
cell here is selected for reporting on the strength of its result — the whole
ladder is written, and the per-year agreement column is what separates a shape
that holds from one that does not.
"""

from __future__ import annotations

import argparse
import csv
import gzip
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STUDY = ROOT / "outputs" / "stage_03_rotation_study"
YEARS = (2019, 2021, 2023, 2025)
TREATED = "TREATED"
CONTROL = "CONTROL_WIDTH_MATCHED"
CLASSES = ("LOW_VOLUME_NODE", "HIGH_VOLUME_NODE")
PERCENTILES = tuple(range(5, 100, 5))
LADDER = [Decimal(n) / 4 for n in range(1, 41)]  # 0.25 .. 10.00 ATR


def load(study: Path) -> dict[tuple[str, str], list[tuple[int, Decimal]]]:
    """(node_class, arm) -> [(year, max excursion in ATR)] over tapped events."""
    out: dict[tuple[str, str], list[tuple[int, Decimal]]] = {}
    for year in YEARS:
        path = study / f"year_{year}" / "rotation_ledger.csv.gz"
        if not path.exists():
            continue
        with gzip.open(path, "rt") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("tapped")).lower() != "true":
                    continue
                value = row.get("max_excursion_atr")
                if value in ("", None):
                    continue
                out.setdefault((row["node_class"], row["arm"]), []).append(
                    (year, Decimal(value))
                )
    return out


def quantile(values: list[Decimal], percentile: int) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, percentile * len(ordered) // 100)
    return ordered[index]


def mean(values: list[Decimal]) -> Decimal | None:
    return sum(values) / Decimal(len(values)) if values else None


def q3(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(Decimal("0.001"))


def _agreement(data, node_class, statistic, difference) -> str:
    """How many years reproduce the pooled sign of `difference`."""
    if difference is None:
        return "0/4"
    agreeing = 0
    for year in YEARS:
        parts = []
        for arm in (TREATED, CONTROL):
            values = [v for y, v in data.get((node_class, arm), []) if y == year]
            parts.append(statistic(values))
        if parts[0] is None or parts[1] is None:
            continue
        if (parts[0] - parts[1]) * difference > 0:
            agreeing += 1
    return f"{agreeing}/4"


def quantile_table(data) -> list[dict]:
    rows = []
    for node_class in CLASSES:
        treated = [v for _, v in data.get((node_class, TREATED), [])]
        control = [v for _, v in data.get((node_class, CONTROL), [])]
        for percentile in PERCENTILES:
            t, c = quantile(treated, percentile), quantile(control, percentile)
            if t is None or c is None:
                continue
            difference = t - c

            def statistic(values, _p=percentile):
                return quantile(values, _p)

            rows.append(
                {
                    "node_class": node_class,
                    "percentile": percentile,
                    "treated_n": len(treated),
                    "control_n": len(control),
                    "treated_excursion_atr": q3(t),
                    "control_excursion_atr": q3(c),
                    "difference_atr": q3(difference),
                    "years_agreeing": _agreement(
                        data, node_class, statistic, difference
                    ),
                }
            )
    return rows


def exceedance_table(data) -> list[dict]:
    rows = []
    for node_class in CLASSES:
        treated = [v for _, v in data.get((node_class, TREATED), [])]
        control = [v for _, v in data.get((node_class, CONTROL), [])]
        if not treated or not control:
            continue
        for level in LADDER:

            def share(values, _l=level):
                if not values:
                    return None
                hits = sum(1 for v in values if v >= _l)
                return Decimal(hits) * 100 / Decimal(len(values))

            t, c = share(treated), share(control)
            difference = t - c
            rows.append(
                {
                    "node_class": node_class,
                    "excursion_atr": level,
                    "treated_n": len(treated),
                    "control_n": len(control),
                    "treated_reaching_pct": q3(t),
                    "control_reaching_pct": q3(c),
                    "difference_pp": q3(difference),
                    "years_agreeing": _agreement(data, node_class, share, difference),
                }
            )
    return rows


def moment_table(data) -> list[dict]:
    rows = []
    for node_class in CLASSES:
        treated = [v for _, v in data.get((node_class, TREATED), [])]
        control = [v for _, v in data.get((node_class, CONTROL), [])]
        t, c = mean(treated), mean(control)
        if t is None or c is None:
            continue
        rows.append(
            {
                "node_class": node_class,
                "treated_n": len(treated),
                "control_n": len(control),
                "treated_mean_atr": q3(t),
                "control_mean_atr": q3(c),
                "difference_atr": q3(t - c),
                "years_agreeing": _agreement(data, node_class, mean, t - c),
            }
        )
    return rows


def write(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    fields = list(rows[0])
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {k: ("" if row.get(k) is None else row.get(k)) for k in fields}
            )


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="excursion_profile.py")
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    args = parser.parse_args(argv)

    data = load(args.study)
    output = args.study / "aggregate"
    output.mkdir(parents=True, exist_ok=True)
    write(output / "excursion_quantiles.csv", quantile_table(data))
    write(output / "excursion_exceedance.csv", exceedance_table(data))
    write(output / "excursion_moments.csv", moment_table(data))
    for row in moment_table(data):
        print(row)


if __name__ == "__main__":
    main()
