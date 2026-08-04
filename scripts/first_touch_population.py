"""First-touch population: one shelf, one session, one observation.

A node is re-detected at every hourly re-anchor, so a shelf that persists
through a day enters the ledger many times and is tapped many times. Those rows
are not independent draws — they are one shelf being revisited — and pooling
them inflates every denominator in the study.

This script keeps the first tap of a shelf in a session and deactivates that
price region for the remainder of that session. The next session starts clean:
if the shelf is still there and still valid the following day, it is counted
again, because a day later it is a genuinely new interaction.

Two shelves are treated as the same shelf when their price intervals overlap
within the same session, contract, arm and node class. Overlap can chain across
a trending session (A overlaps B, B overlaps C, A and C do not), which merges
slightly more aggressively than a strict identity rule would. That direction is
deliberate: it under-counts rather than over-counts independent events.

No threshold in the underlying study is changed. This re-cuts which rows are
pooled, and every table is recomputed on the reduced population.
"""

from __future__ import annotations

import argparse
import csv
import gzip
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from hvn.rolling_profile import session_date

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STUDY = ROOT / "outputs" / "stage_03_rotation_study"
YEARS = (2019, 2021, 2023, 2025)
TREATED = "TREATED"
CONTROL = "CONTROL_WIDTH_MATCHED"
CLASSES = ("HIGH_VOLUME_NODE", "LOW_VOLUME_NODE")
CELLS = (("0.5", 3), ("1", 5), ("2", 3), ("2", 5), ("3", 3), ("3", 10))
LADDER = [Decimal(n) / 4 for n in range(4, 45, 2)]  # 1.00 .. 11.00 ATR


def is_true(value) -> bool:
    return str(value).lower() == "true"


def q3(value):
    return None if value is None else value.quantize(Decimal("0.001"))


def mean(values):
    return sum(values) / Decimal(len(values)) if values else None


def first_touch(study: Path) -> tuple[list[dict], dict]:
    """Tapped rows reduced to one per shelf per session, plus the audit counts."""
    kept: list[dict] = []
    audit = {"tapped_rows": 0, "kept": 0, "suppressed": 0}
    for year in YEARS:
        path = study / f"year_{year}" / "rotation_ledger.csv.gz"
        if not path.exists():
            continue
        rows = []
        with gzip.open(path, "rt") as handle:
            for row in csv.DictReader(handle):
                if not is_true(row.get("tapped")):
                    continue
                row["year"] = year
                anchor = datetime.fromisoformat(row["anchor_time"])
                row["session"] = session_date(anchor)
                row["_anchor"] = anchor
                rows.append(row)
        audit["tapped_rows"] += len(rows)
        rows.sort(key=lambda r: (r["_anchor"], r["node_id"]))
        # Price regions already spent, per session and arm and class.
        spent: dict[tuple, list[tuple[Decimal, Decimal]]] = defaultdict(list)
        for row in rows:
            key = (row["session"], row["contract"], row["arm"], row["node_class"])
            low, high = Decimal(row["node_low"]), Decimal(row["node_high"])
            if any(low < b and a < high for a, b in spent[key]):
                audit["suppressed"] += 1
                continue
            spent[key].append((low, high))
            kept.append(row)
            audit["kept"] += 1
    return kept, audit


def per_year_counts(events: list[dict]) -> list[dict]:
    counts: dict[tuple, set] = defaultdict(set)
    totals: dict[tuple, int] = defaultdict(int)
    for row in events:
        totals[(row["year"], row["node_class"], row["arm"])] += 1
        counts[row["year"]].add(row["session"])
    out = []
    for year in YEARS:
        sessions = len(counts[year])
        for node_class in CLASSES:
            for arm in (TREATED, CONTROL):
                n = totals[(year, node_class, arm)]
                out.append(
                    {
                        "year": year,
                        "sessions": sessions,
                        "node_class": node_class,
                        "arm": arm,
                        "first_touch_events": n,
                        "per_session": (
                            q3(Decimal(n) / Decimal(sessions)) if sessions else None
                        ),
                    }
                )
    return out


def _agreement(events, node_class, statistic, difference) -> str:
    if difference is None:
        return "0/4"
    agreeing = 0
    for year in YEARS:
        parts = []
        for arm in (TREATED, CONTROL):
            parts.append(
                statistic(
                    [
                        r
                        for r in events
                        if r["year"] == year
                        and r["arm"] == arm
                        and r["node_class"] == node_class
                    ]
                )
            )
        if parts[0] is None or parts[1] is None:
            continue
        if (parts[0] - parts[1]) * difference > 0:
            agreeing += 1
    return f"{agreeing}/4"


def _excursions(rows) -> list[Decimal]:
    return [
        Decimal(r["max_excursion_atr"])
        for r in rows
        if r.get("max_excursion_atr") not in ("", None)
    ]


def excursion_tables(events: list[dict]) -> tuple[list[dict], list[dict]]:
    moments, exceedance = [], []
    for node_class in CLASSES:
        arms = {
            arm: [
                r for r in events if r["node_class"] == node_class and r["arm"] == arm
            ]
            for arm in (TREATED, CONTROL)
        }

        def stat_mean(rows):
            return mean(_excursions(rows))

        t, c = stat_mean(arms[TREATED]), stat_mean(arms[CONTROL])
        if t is not None and c is not None:
            moments.append(
                {
                    "node_class": node_class,
                    "treated_n": len(arms[TREATED]),
                    "control_n": len(arms[CONTROL]),
                    "treated_mean_atr": q3(t),
                    "control_mean_atr": q3(c),
                    "difference_atr": q3(t - c),
                    "years_agreeing": _agreement(events, node_class, stat_mean, t - c),
                }
            )
        for level in LADDER:

            def share(rows, _l=level):
                values = _excursions(rows)
                if not values:
                    return None
                hits = sum(1 for v in values if v >= _l)
                return Decimal(hits) * 100 / Decimal(len(values))

            ts, cs = share(arms[TREATED]), share(arms[CONTROL])
            if ts is None or cs is None:
                continue
            exceedance.append(
                {
                    "node_class": node_class,
                    "excursion_atr": level,
                    "treated_n": len(arms[TREATED]),
                    "control_n": len(arms[CONTROL]),
                    "treated_reaching_pct": q3(ts),
                    "control_reaching_pct": q3(cs),
                    "difference_pp": q3(ts - cs),
                    "years_agreeing": _agreement(events, node_class, share, ts - cs),
                }
            )
    return moments, exceedance


def quality_tables(events: list[dict]) -> tuple[list[dict], list[dict]]:
    rotations, held = [], []
    for node_class in CLASSES:
        for distance, deadline in CELLS:
            key = f"{distance}atr_{deadline}b"
            arms = {}
            for arm in (TREATED, CONTROL):
                pool = [
                    r
                    for r in events
                    if r["node_class"] == node_class
                    and r["arm"] == arm
                    and not is_true(r.get(f"censored_{key}"))
                ]
                hits = [r for r in pool if is_true(r.get(f"rotated_{key}"))]
                arms[arm] = {"pool": pool, "hits": hits}

            def rate(rows, _k=key):
                rows = [r for r in rows if not is_true(r.get(f"censored_{_k}"))]
                if not rows:
                    return None
                n = sum(1 for r in rows if is_true(r.get(f"rotated_{_k}")))
                return Decimal(n) * 100 / Decimal(len(rows))

            t, c = rate(arms[TREATED]["pool"]), rate(arms[CONTROL]["pool"])
            if t is not None and c is not None:
                rotations.append(
                    {
                        "node_class": node_class,
                        "distance_atr": distance,
                        "deadline_bars": deadline,
                        "treated_events": len(arms[TREATED]["pool"]),
                        "control_events": len(arms[CONTROL]["pool"]),
                        "treated_rotations_per_year": round(
                            len(arms[TREATED]["hits"]) / len(YEARS)
                        ),
                        "treated_rotated_pct": q3(t),
                        "control_rotated_pct": q3(c),
                        "difference_pp": q3(t - c),
                        "years_agreeing": _agreement(events, node_class, rate, t - c),
                    }
                )

            def held_mean(rows, _k=key):
                values = [
                    Decimal(r[f"bars_held_{_k}"])
                    for r in rows
                    if is_true(r.get(f"quality_evaluated_{_k}"))
                    and r.get(f"bars_held_{_k}") not in ("", None)
                ]
                return mean(values)

            th, ch = held_mean(arms[TREATED]["pool"]), held_mean(arms[CONTROL]["pool"])
            if th is None or ch is None:
                continue
            held.append(
                {
                    "node_class": node_class,
                    "distance_atr": distance,
                    "deadline_bars": deadline,
                    "treated_rotations": len(arms[TREATED]["hits"]),
                    "control_rotations": len(arms[CONTROL]["hits"]),
                    "treated_mean_bars_held": q3(th),
                    "control_mean_bars_held": q3(ch),
                    "difference": q3(th - ch),
                    "years_agreeing": _agreement(events, node_class, held_mean, th - ch),
                }
            )
    return rotations, held


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
    parser = argparse.ArgumentParser(prog="first_touch_population.py")
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    args = parser.parse_args(argv)

    events, audit = first_touch(args.study)
    output = args.study / "aggregate" / "first_touch"
    output.mkdir(parents=True, exist_ok=True)

    counts = per_year_counts(events)
    moments, exceedance = excursion_tables(events)
    rotations, held = quality_tables(events)
    write(output / "counts_per_year.csv", counts)
    write(output / "excursion_moments.csv", moments)
    write(output / "excursion_exceedance.csv", exceedance)
    write(output / "rotation_rates.csv", rotations)
    write(output / "bars_held.csv", held)
    print(audit)
    for row in moments:
        print(row)


if __name__ == "__main__":
    main()
