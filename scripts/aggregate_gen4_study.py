"""Pool the Generation 4 partitions and test year consistency.

Reads the per-year event and interval ledgers, pools the four full development
years, and reports treated against each control arm with the per-year direction
beside every pooled figure. Partial 2026 is carried as supporting evidence and
never counts toward a year-consistency figure.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STUDY = ROOT / "outputs" / "stage_02_generation_4_study"
FULL_YEARS = (2019, 2021, 2023, 2025)
SUPPORTING_YEARS = (2026,)
TREATED = "TREATED"
CONTROLS = ("C01_NEUTRAL", "C02_ACTIVITY_MATCHED")
PRIMARY_CONTROL = "C02_ACTIVITY_MATCHED"
UNDERPOWERED = 30


def read_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt") as handle:
        return list(csv.DictReader(handle))


def pct(numerator: int, denominator: int) -> Decimal | None:
    if not denominator:
        return None
    return (Decimal(numerator) * Decimal(100) / Decimal(denominator)).quantize(
        Decimal("0.01")
    )


def ratio(treated: Decimal | None, control: Decimal | None) -> Decimal | None:
    if treated is None or control is None or control == 0:
        return None
    return (treated / control).quantize(Decimal("0.001"))


def median(values: list) -> object:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def load(study: Path, years) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    intervals: list[dict] = []
    for year in years:
        folder = study / f"year_{year}"
        for row in read_gz(folder / "event_ledger.csv.gz"):
            row["year"] = int(row["year"])
            events.append(row)
        for row in read_gz(folder / "interval_ledger.csv.gz"):
            row["year"] = int(row["year"])
            intervals.append(row)
    return events, intervals


def is_true(value) -> bool:
    return str(value).lower() == "true"


# ---------------------------------------------------------------------------


def touch_rate_table(intervals: list[dict]) -> list[dict]:
    """Touch rate per population and arm, pooled, with each year beside it."""
    out = []
    for population in ("NONPOC", "POC"):
        by_arm: dict[str, dict] = {}
        for arm in (TREATED, *CONTROLS):
            rows = [
                r
                for r in intervals
                if r["population"] == population
                and r["arm"] == arm
                and r["year"] in FULL_YEARS
            ]
            touched = sum(1 for r in rows if is_true(r["touched"]))
            by_arm[arm] = {
                "intervals": len(rows),
                "touched": touched,
                "rate": pct(touched, len(rows)),
                "per_year": {},
            }
            for year in FULL_YEARS:
                year_rows = [r for r in rows if r["year"] == year]
                by_arm[arm]["per_year"][year] = pct(
                    sum(1 for r in year_rows if is_true(r["touched"])), len(year_rows)
                )
        treated = by_arm[TREATED]
        for arm in CONTROLS:
            control = by_arm[arm]
            years_favouring = sum(
                1
                for year in FULL_YEARS
                if treated["per_year"][year] is not None
                and control["per_year"][year] is not None
                and treated["per_year"][year] > control["per_year"][year]
            )
            out.append(
                {
                    "population": population,
                    "control_arm": arm,
                    "treated_intervals": treated["intervals"],
                    "control_intervals": control["intervals"],
                    "treated_touch_rate_pct": treated["rate"],
                    "control_touch_rate_pct": control["rate"],
                    "difference_pp": (
                        treated["rate"] - control["rate"]
                        if treated["rate"] is not None and control["rate"] is not None
                        else None
                    ),
                    "ratio": ratio(treated["rate"], control["rate"]),
                    "full_years_treated_higher": f"{years_favouring}/4",
                    **{
                        f"treated_{year}": treated["per_year"][year] for year in FULL_YEARS
                    },
                    **{
                        f"control_{year}": control["per_year"][year] for year in FULL_YEARS
                    },
                }
            )
    return out


def displacement_table(events: list[dict]) -> list[dict]:
    """Median bars to each threshold, and the share reaching it at all."""
    first = [e for e in events if is_true(e["is_first_touch"]) and e["year"] in FULL_YEARS]
    out = []
    for threshold in ("3atr", "5atr"):
        for population in ("NONPOC", "POC"):
            arms: dict[str, dict] = {}
            for arm in (TREATED, *CONTROLS):
                rows = [
                    e
                    for e in first
                    if e["population"] == population and e["arm"] == arm
                ]
                reached = sorted(
                    int(e[f"bars_to_{threshold}"])
                    for e in rows
                    if is_true(e[f"reached_{threshold}"])
                )
                arms[arm] = {
                    "events": len(rows),
                    "reached": len(reached),
                    "reached_pct": pct(len(reached), len(rows)),
                    "censored_pct": pct(
                        sum(1 for e in rows if is_true(e[f"censored_{threshold}"])),
                        len(rows),
                    ),
                    "median": median(reached),
                    "per_year": {
                        year: median(
                            [
                                int(e[f"bars_to_{threshold}"])
                                for e in rows
                                if e["year"] == year and is_true(e[f"reached_{threshold}"])
                            ]
                        )
                        for year in FULL_YEARS
                    },
                }
            treated = arms[TREATED]
            for arm in CONTROLS:
                control = arms[arm]
                faster = sum(
                    1
                    for year in FULL_YEARS
                    if treated["per_year"][year] is not None
                    and control["per_year"][year] is not None
                    and treated["per_year"][year] < control["per_year"][year]
                )
                out.append(
                    {
                        "threshold": threshold,
                        "population": population,
                        "control_arm": arm,
                        "treated_events": treated["events"],
                        "control_events": control["events"],
                        "treated_reached_pct": treated["reached_pct"],
                        "control_reached_pct": control["reached_pct"],
                        "treated_censored_pct": treated["censored_pct"],
                        "treated_median_bars": treated["median"],
                        "control_median_bars": control["median"],
                        "full_years_treated_faster": f"{faster}/4",
                        "underpowered": treated["events"] < UNDERPOWERED,
                    }
                )
    return out


def envelope_table(events: list[dict]) -> list[dict]:
    first = [
        e
        for e in events
        if is_true(e["is_first_touch"])
        and is_true(e["envelope_eligible"])
        and e["year"] in FULL_YEARS
    ]
    out = []
    for population in ("NONPOC", "POC"):
        arms: dict[str, dict] = {}
        for arm in (TREATED, *CONTROLS):
            rows = [e for e in first if e["population"] == population and e["arm"] == arm]
            minutes = [
                int(e["envelope_minutes_inside"])
                for e in rows
                if is_true(e["envelope_left"]) and e["envelope_minutes_inside"] not in ("", None)
            ]
            arms[arm] = {
                "events": len(rows),
                "median": median(minutes),
                "mean": (
                    (sum(minutes) / Decimal(len(minutes))).quantize(Decimal("0.1"))
                    if minutes
                    else None
                ),
                "per_year": {
                    year: median(
                        [
                            int(e["envelope_minutes_inside"])
                            for e in rows
                            if e["year"] == year
                            and is_true(e["envelope_left"])
                            and e["envelope_minutes_inside"] not in ("", None)
                        ]
                    )
                    for year in FULL_YEARS
                },
            }
        treated = arms[TREATED]
        for arm in CONTROLS:
            control = arms[arm]
            longer = sum(
                1
                for year in FULL_YEARS
                if treated["per_year"][year] is not None
                and control["per_year"][year] is not None
                and treated["per_year"][year] > control["per_year"][year]
            )
            out.append(
                {
                    "population": population,
                    "control_arm": arm,
                    "treated_events": treated["events"],
                    "control_events": control["events"],
                    "treated_median_minutes": treated["median"],
                    "control_median_minutes": control["median"],
                    "treated_mean_minutes": treated["mean"],
                    "control_mean_minutes": control["mean"],
                    "ratio_mean": ratio(treated["mean"], control["mean"]),
                    "full_years_treated_longer": f"{longer}/4",
                    "underpowered": treated["events"] < UNDERPOWERED,
                }
            )
    return out


def continuation_table(events: list[dict]) -> list[dict]:
    first = [
        e
        for e in events
        if is_true(e["is_first_touch"])
        and e["approach_side"] in ("APPROACH_FROM_BELOW", "APPROACH_FROM_ABOVE")
        and e["year"] in FULL_YEARS
    ]
    out = []
    for threshold in ("3atr", "5atr"):
        for horizon in (15, 30, 60):
            for population in ("NONPOC", "POC"):
                for side in ("APPROACH_FROM_BELOW", "APPROACH_FROM_ABOVE"):
                    arms: dict[str, dict] = {}
                    for arm in (TREATED, *CONTROLS):
                        rows = [
                            e
                            for e in first
                            if e["population"] == population
                            and e["arm"] == arm
                            and e["approach_side"] == side
                            and is_true(
                                e[f"continuation_evaluated_{threshold}_{horizon}m"]
                            )
                        ]
                        continued = sum(
                            1 for e in rows if is_true(e[f"continued_{threshold}_{horizon}m"])
                        )
                        returned = sum(
                            1 for e in rows if is_true(e[f"returned_inside_after_{threshold}"])
                        )
                        arms[arm] = {
                            "events": len(rows),
                            "continued_pct": pct(continued, len(rows)),
                            "returned_pct": pct(returned, len(rows)),
                        }
                    treated = arms[TREATED]
                    for arm in CONTROLS:
                        control = arms[arm]
                        out.append(
                            {
                                "threshold": threshold,
                                "horizon_minutes": horizon,
                                "population": population,
                                "approach_side": side,
                                "control_arm": arm,
                                "treated_events": treated["events"],
                                "control_events": control["events"],
                                "treated_continued_pct": treated["continued_pct"],
                                "control_continued_pct": control["continued_pct"],
                                "difference_pp": (
                                    treated["continued_pct"] - control["continued_pct"]
                                    if treated["continued_pct"] is not None
                                    and control["continued_pct"] is not None
                                    else None
                                ),
                                "treated_returned_inside_pct": treated["returned_pct"],
                                "control_returned_inside_pct": control["returned_pct"],
                                "underpowered": treated["events"] < UNDERPOWERED,
                            }
                        )
    return out


def session_table(events: list[dict]) -> list[dict]:
    """Every anchor split by interaction session, and combined."""
    first = [e for e in events if is_true(e["is_first_touch"]) and e["year"] in FULL_YEARS]
    buckets: dict[tuple, list] = defaultdict(list)
    for row in first:
        for anchor in (row["relationship_id"], "ALL_ANCHORS"):
            for session in (row["interaction_session"], "ALL_SESSIONS"):
                buckets[(row["population"], anchor, session, row["arm"])].append(row)
    out = []
    seen = sorted({(p, a, s) for (p, a, s, _) in buckets})
    for population, anchor, session in seen:
        treated_rows = buckets.get((population, anchor, session, TREATED), [])
        if not treated_rows:
            continue
        record = {
            "population": population,
            "anchor": anchor,
            "session": session,
            "treated_events": len(treated_rows),
            "underpowered": len(treated_rows) < UNDERPOWERED,
        }
        for label, rows in (
            ("treated", treated_rows),
            *[(arm.lower(), buckets.get((population, anchor, session, arm), [])) for arm in CONTROLS],
        ):
            reached = sorted(
                int(e["bars_to_3atr"]) for e in rows if is_true(e["reached_3atr"])
            )
            record[f"{label}_events"] = len(rows)
            record[f"{label}_median_bars_3atr"] = median(reached)
            record[f"{label}_returned_inside_3atr_pct"] = pct(
                sum(1 for e in rows if is_true(e["returned_inside_after_3atr"])), len(rows)
            )
        out.append(record)
    return out


def write(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    fields = list(rows[0])
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
    parser = argparse.ArgumentParser(prog="aggregate_gen4_study.py")
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    args = parser.parse_args(argv)

    years = FULL_YEARS + SUPPORTING_YEARS
    events, intervals = load(args.study, years)
    output = args.study / "aggregate"
    output.mkdir(parents=True, exist_ok=True)

    write(output / "touch_rates.csv", touch_rate_table(intervals))
    write(output / "displacement.csv", displacement_table(events))
    write(output / "envelope.csv", envelope_table(events))
    write(output / "continuation.csv", continuation_table(events))
    write(output / "by_anchor_and_session.csv", session_table(events))

    summary = {
        "full_years": list(FULL_YEARS),
        "supporting_years": list(SUPPORTING_YEARS),
        "primary_control": PRIMARY_CONTROL,
        "intervals": len(intervals),
        "events": len(events),
        "first_touches": sum(1 for e in events if is_true(e["is_first_touch"])),
        "first_touches_full_years": sum(
            1 for e in events if is_true(e["is_first_touch"]) and e["year"] in FULL_YEARS
        ),
        "unique_physical_zones": len(
            {i["physical_zone_id"] for i in intervals if i["arm"] == TREATED}
        ),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
