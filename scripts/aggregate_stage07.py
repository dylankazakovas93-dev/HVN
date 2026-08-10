"""Stage 7 aggregation: nine pre-declared numbers, then everything else.

The headline is fixed before the data is read: for each tier and each race
distance, the favourable-first share of stacked barriers (two or more level
kinds) minus that of single-kind barriers, pooled across width strata. Nine
numbers, three tiers by three distances. Everything below them in the output is
exploratory and labelled as such.

Stating the headline in advance is the whole point. Stage 6 produced 109 cells
and a sign test over 63 of them, which invited exactly the reading it got: hunt
for the positive ones. Nine numbers cannot be hunted through.

Three guards carry over unchanged, because each of them caught a real error:

  width strata   stacked barriers are wider, and width alone moves the outcome,
                 so stacking is compared only inside a width band and pooled
                 with the single-kind arm's weights
  first touch    one barrier per price region per session; a level re-detected
                 at every hourly anchor is one level, not six observations
  year agreement counted over years carrying data in BOTH arms; a missing year
                 never counts as a disagreement

Ambiguous races — one bar covering both brackets — are reported beside every
rate and excluded from it. OHLC does not say which bracket came first, and
guessing would bias the result in whichever direction the guess leans.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from hvn.race import ADVERSE, AMBIGUOUS, CENSORED, FAVOURABLE
from hvn.tiers import TIERS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "outputs" / "stage_07_races"
DISTANCES = ("1", "3", "5")
WIDTH_BINS = (
    (Decimal("0.0"), Decimal("0.7")),
    (Decimal("0.7"), Decimal("1.2")),
    (Decimal("1.2"), Decimal("2.0")),
    (Decimal("2.0"), Decimal("3.1")),
)
MIN_EVENTS = 50
MIN_YEAR_EVENTS = 20


def load(folder: Path) -> list[dict]:
    """Tapped rows, reduced to one barrier per price region per session per tier."""
    kept: list[dict] = []
    for path in sorted(folder.glob("*.json")):
        rows = [r for r in json.loads(path.read_text()) if r.get("tapped")]
        rows.sort(key=lambda r: (r["anchor_time"], r["tier"], r["band_low"]))
        spent: dict[tuple, list[tuple[Decimal, Decimal]]] = defaultdict(list)
        for row in rows:
            key = (row["tier"], row["direction"])
            low, high = Decimal(row["band_low"]), Decimal(row["band_high"])
            if any(low < b and a < high for a, b in spent[key]):
                continue
            spent[key].append((low, high))
            kept.append(row)
    return kept


def outcomes(rows, distance: str) -> dict[str, int]:
    counts = {FAVOURABLE: 0, ADVERSE: 0, AMBIGUOUS: 0, CENSORED: 0}
    for row in rows:
        outcome = row.get(f"race_{distance}")
        if outcome in counts:
            counts[outcome] += 1
    return counts


def favourable_share(rows, distance: str):
    """Favourable-first share among decided races, and how many decided."""
    counts = outcomes(rows, distance)
    decided = counts[FAVOURABLE] + counts[ADVERSE]
    if decided == 0:
        return None, 0, counts
    return Decimal(100 * counts[FAVOURABLE]) / Decimal(decided), decided, counts


def stratified(events, tier_name, distance):
    """Stacked-minus-single difference, pooled over width strata.

    Weights are the single-kind arm's decided counts, so the pooled number is
    "what would the difference be if stacked barriers had the width mix of
    single ones" rather than a mix dominated by whichever stratum happens to
    hold the most stacked events.
    """
    pool = [e for e in events if e["tier"] == tier_name]
    total_weight = Decimal(0)
    weighted = Decimal(0)
    strata = []
    for low, high in WIDTH_BINS:
        stratum = [e for e in pool if low <= Decimal(e["width_atr"]) < high]
        single = [e for e in stratum if e["level_kinds"] == 1]
        stacked = [e for e in stratum if e["level_kinds"] >= 2]
        base, base_n, base_counts = favourable_share(single, distance)
        rate, n, counts = favourable_share(stacked, distance)
        if base is None or rate is None or base_n < MIN_EVENTS or n < MIN_EVENTS:
            continue
        weight = Decimal(base_n)
        weighted += (rate - base) * weight
        total_weight += weight
        strata.append({
            "width_bin": f"{low}-{high}",
            "single_pct": round(float(base), 2),
            "stacked_pct": round(float(rate), 2),
            "difference_pp": round(float(rate - base), 2),
            "single_decided": base_n,
            "stacked_decided": n,
            "single_ambiguous": base_counts[AMBIGUOUS],
            "stacked_ambiguous": counts[AMBIGUOUS],
            "single_censored": base_counts[CENSORED],
            "stacked_censored": counts[CENSORED],
        })
    if total_weight == 0:
        return None, strata
    return weighted / total_weight, strata


def year_agreement(events, tier_name, distance, sign):
    agreeing = testable = 0
    for year in sorted({e["year"] for e in events}):
        pool = [e for e in events if e["tier"] == tier_name and e["year"] == year]
        single = [e for e in pool if e["level_kinds"] == 1]
        stacked = [e for e in pool if e["level_kinds"] >= 2]
        base, base_n, _ = favourable_share(single, distance)
        rate, n, _ = favourable_share(stacked, distance)
        if base is None or rate is None or base_n < MIN_YEAR_EVENTS or n < MIN_YEAR_EVENTS:
            continue
        testable += 1
        if (rate - base) * sign > 0:
            agreeing += 1
    return agreeing, testable


def by_stack_size(events, tier_name, distance):
    """Exploratory: the same rate broken out by how many kinds agreed."""
    pool = [e for e in events if e["tier"] == tier_name]
    out = []
    for count in (1, 2, 3, 4):
        rows = (
            [e for e in pool if e["level_kinds"] == count]
            if count < 4
            else [e for e in pool if e["level_kinds"] >= 4]
        )
        rate, n, counts = favourable_share(rows, distance)
        if rate is None or n < MIN_EVENTS:
            continue
        out.append({
            "level_kinds": "4+" if count == 4 else count,
            "favourable_pct": round(float(rate), 2),
            "decided": n,
            "ambiguous": counts[AMBIGUOUS],
            "censored": counts[CENSORED],
        })
    return out


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="aggregate_stage07.py")
    parser.add_argument("--dir", type=Path, default=DEFAULT_IN)
    args = parser.parse_args(argv)

    events = load(args.dir)
    headline = []
    exploratory = []
    for tier_name in TIERS:
        for distance in DISTANCES:
            difference, strata = stratified(events, tier_name, distance)
            if difference is None:
                headline.append({
                    "tier": tier_name,
                    "distance_atr": distance,
                    "verdict": "UNTESTABLE_NO_SUPPORTED_STRATUM",
                })
                continue
            sign = 1 if difference > 0 else -1
            agreeing, testable = year_agreement(events, tier_name, distance, sign)
            headline.append({
                "tier": tier_name,
                "distance_atr": distance,
                "stacked_minus_single_pp": round(float(difference), 2),
                "years_agreeing": f"{agreeing}/{testable}",
                "strata_supported": len(strata),
            })
            exploratory.append({
                "tier": tier_name,
                "distance_atr": distance,
                "strata": strata,
                "by_stack_size": by_stack_size(events, tier_name, distance),
            })

    output = args.dir / "aggregate"
    output.mkdir(parents=True, exist_ok=True)
    (output / "headline.json").write_text(json.dumps(headline, indent=1) + "\n")
    (output / "exploratory.json").write_text(json.dumps(exploratory, indent=1) + "\n")

    summary = {
        "first_touch_events": len(events),
        "years": sorted({e["year"] for e in events}),
        "sessions": len({e["session"] for e in events}),
        "by_tier": {
            name: sum(1 for e in events if e["tier"] == name) for name in TIERS
        },
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")

    print(json.dumps(summary, indent=1, sort_keys=True))
    print()
    print(f"{'tier':>8} {'dist':>5} {'stacked-single':>15} {'years':>7}")
    for row in headline:
        print(
            f"{row['tier']:>8} {row['distance_atr']:>5} "
            f"{row.get('stacked_minus_single_pp', row.get('verdict', '')):>15} "
            f"{row.get('years_agreeing', ''):>7}"
        )


if __name__ == "__main__":
    main()
