"""The >55% bundle, per year, beside the control that says what it's worth.

Three things, in this order, because the order is the argument:

  1  bundle        every combination that scored above 55% in sample, pooled,
                   broken out by year at each race distance
  2  shuffle       the identical selection rule applied to outcomes permuted
                   within session, repeated many times. This is what a bundle
                   picked this way scores when there is provably nothing there.
  3  width         favourable-first rate against barrier width, in fine bins,
                   single and stacked separately

**Read 1 and 2 together or not at all.** Selecting combinations for scoring
above 55% on this data and then reporting their score on the same data is
circular: they were chosen for being high here, so they are high here. That is
arithmetic, not evidence. The shuffle quantifies exactly how much of the
bundle's apparent performance the selection rule manufactures on its own — the
outcomes are destroyed, the selection is not, and whatever survives is pure
selection bias.

The permutation is **within session**, so each session keeps its own mix of
favourable and adverse and only the pairing of outcome to barrier is broken.
Shuffling globally would also destroy the between-session variation, which is
real, and would understate the noise.

Width (3) is the one question here that selection cannot contaminate: width is
a property of the level fixed before any outcome exists, and every barrier is
in the table regardless of how it scored. It has only ever been used as a
control in this project, never looked at directly.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import numpy as np

from aggregate_stage07 import DISTANCES, load
from answer_stage07 import MIN_PAIR_EVENTS, short
from hvn.race import ADVERSE, FAVOURABLE
from hvn.tiers import TIERS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "outputs" / "stage_07_races"
THRESHOLD = 55.0
SHUFFLES = 200
SEED = 20260813
WIDTH_EDGES = [Decimal(str(x)) for x in
               ("0.0", "0.4", "0.7", "1.0", "1.3", "1.6", "2.0", "2.5", "3.1")]
MIN_BIN = 150


def combo_key(event) -> tuple:
    return tuple(sorted(set(event["kinds"].split("|"))))


def rate(rows, distance):
    """Favourable-first share among decided races, and the count."""
    decided = [
        r for r in rows if r.get(f"race_{distance}") in (FAVOURABLE, ADVERSE)
    ]
    if not decided:
        return None, 0
    hits = sum(1 for r in decided if r[f"race_{distance}"] == FAVOURABLE)
    return 100.0 * hits / len(decided), len(decided)


def select(events, distance):
    """Combinations scoring above the threshold, by tier. The selection rule.

    Applied identically to real and shuffled outcomes; that is the only way the
    control measures the rule rather than the data.
    """
    chosen = set()
    grouped: dict[tuple, list] = defaultdict(list)
    for event in events:
        if event["level_kinds"] < 2:
            continue
        grouped[(event["tier"], combo_key(event))].append(event)
    for key, members in grouped.items():
        value, n = rate(members, distance)
        if value is not None and n >= MIN_PAIR_EVENTS and value > THRESHOLD:
            chosen.add(key)
    return chosen


def bundle_by_year(events, chosen, distance):
    members = [
        e for e in events if (e["tier"], combo_key(e)) in chosen
    ]
    overall, total = rate(members, distance)
    years = {}
    for year in sorted({e["year"] for e in events}):
        value, n = rate([e for e in members if e["year"] == year], distance)
        years[year] = {"pct": None if value is None else round(value, 2), "n": n}
    return overall, total, years


def shuffled(events, rng):
    """Permute race outcomes within session, keeping each session's own mix."""
    by_session: dict[str, list] = defaultdict(list)
    for event in events:
        by_session[event["session"]].append(event)
    out = []
    for members in by_session.values():
        pools = {
            d: [m.get(f"race_{d}") for m in members] for d in DISTANCES
        }
        for pool in pools.values():
            rng.shuffle(pool)
        for index, event in enumerate(members):
            copy = dict(event)
            for d in DISTANCES:
                copy[f"race_{d}"] = pools[d][index]
            out.append(copy)
    return out


def width_table(events, distance):
    rows = []
    for tier_name in TIERS:
        for low, high in zip(WIDTH_EDGES, WIDTH_EDGES[1:], strict=False):
            stratum = [
                e for e in events
                if e["tier"] == tier_name and low <= Decimal(e["width_atr"]) < high
            ]
            single, single_n = rate(
                [e for e in stratum if e["level_kinds"] == 1], distance
            )
            stacked, stacked_n = rate(
                [e for e in stratum if e["level_kinds"] >= 2], distance
            )
            if single_n < MIN_BIN and stacked_n < MIN_BIN:
                continue
            rows.append({
                "tier": tier_name,
                "width_atr": f"{low}-{high}",
                "single_pct": None if single_n < MIN_BIN else round(single, 2),
                "single_n": single_n,
                "stacked_pct": None if stacked_n < MIN_BIN else round(stacked, 2),
                "stacked_n": stacked_n,
            })
    return rows


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="bundle_stage07.py")
    parser.add_argument("--dir", type=Path, default=DEFAULT_IN)
    parser.add_argument("--shuffles", type=int, default=SHUFFLES)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    events = load(args.dir)
    years = sorted({e["year"] for e in events})
    report = {"events": len(events), "years": years, "threshold_pct": THRESHOLD}
    rng = random.Random(args.seed)

    print("=" * 78)
    print(f"1+2  the >{THRESHOLD:.0f}% bundle, per year, against its shuffle control")
    print("=" * 78)

    per_distance = {}
    for distance in DISTANCES:
        chosen = select(events, distance)
        overall, total, by_year = bundle_by_year(events, chosen, distance)
        if overall is None:
            print(f"\nrace to {distance} ATR: nothing selected")
            continue

        # The control: same rule, outcomes destroyed.
        null_overall = []
        null_years = defaultdict(list)
        for _ in range(args.shuffles):
            fake = shuffled(events, rng)
            fake_chosen = select(fake, distance)
            value, _n, fake_years = bundle_by_year(fake, fake_chosen, distance)
            if value is None:
                continue
            null_overall.append(value)
            for year, cell in fake_years.items():
                if cell["pct"] is not None:
                    null_years[year].append(cell["pct"])

        centre = float(np.mean(null_overall)) if null_overall else float("nan")
        high = float(np.percentile(null_overall, 95)) if null_overall else float("nan")
        print(f"\nrace to {distance} ATR — {len(chosen)} combinations selected, "
              f"{total} decided races")
        print(f"  bundle overall          {overall:6.2f}%")
        print(f"  shuffle control mean    {centre:6.2f}%   "
              f"95th percentile {high:6.2f}%")
        print(f"  {'':>6}{'year':>6} {'bundle':>8} {'n':>7} {'shuffle mean':>14}")
        for year in years:
            cell = by_year[year]
            null = null_years.get(year, [])
            null_mean = f"{np.mean(null):.2f}%" if null else "-"
            shown = "-" if cell["pct"] is None else f"{cell['pct']:.2f}%"
            print(f"  {'':>6}{year:>6} {shown:>8} {cell['n']:>7} {null_mean:>14}")
        per_distance[distance] = {
            "combinations": [
                {"tier": t, "kinds": " + ".join(short(k) for k in c)}
                for t, c in sorted(chosen)
            ],
            "bundle_pct": round(overall, 2),
            "decided": total,
            "by_year": by_year,
            "shuffle_mean_pct": round(centre, 2),
            "shuffle_p95_pct": round(high, 2),
            "beats_shuffle_p95": overall > high,
        }
    report["bundle"] = per_distance

    print()
    print("=" * 78)
    print("3  favourable-first rate against barrier width")
    print("=" * 78)
    widths = {}
    for distance in DISTANCES:
        rows = width_table(events, distance)
        widths[distance] = rows
        print(f"\nrace to {distance} ATR")
        print(f"  {'tier':>7} {'width (ATR)':>12} {'single':>8} {'n':>7} "
              f"{'stacked':>8} {'n':>7}")
        for row in rows:
            single = "-" if row["single_pct"] is None else f"{row['single_pct']:.2f}%"
            stacked = "-" if row["stacked_pct"] is None else f"{row['stacked_pct']:.2f}%"
            print(f"  {row['tier']:>7} {row['width_atr']:>12} {single:>8} "
                  f"{row['single_n']:>7} {stacked:>8} {row['stacked_n']:>7}")
    report["width"] = widths

    output = args.dir / "aggregate"
    output.mkdir(parents=True, exist_ok=True)
    (output / "bundle.json").write_text(json.dumps(report, indent=1, default=str) + "\n")
    print(f"\nwritten to {output / 'bundle.json'}")


if __name__ == "__main__":
    main()
