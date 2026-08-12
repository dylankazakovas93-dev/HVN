"""The three questions, answered directly from the Stage 7 ledger.

    1  which kinds of level are worth pairing with which
    2  how often does a stacked level hold, in plain percent
    3  does stacking beat a single level, and by how much

Everything here reads `outputs/stage_07_races/*.json` and computes nothing new
about the market; it reorganises what the scan already recorded. The aggregator
answered a narrower question — one pooled difference per tier and distance —
and never broke the result out by *which* kinds agreed, which is the thing
actually being asked.

Two guards from the aggregator are kept, because dropping them would make the
answers wrong rather than merely coarse:

  first touch   one barrier per price region per session per tier, so a level
                re-detected at every hourly anchor counts once
  width strata  stacked barriers are wider, and width shifts the outcome on its
                own, so stacked and single are compared inside a width band and
                pooled with the single arm's weights

The interval is a **session-clustered bootstrap**. Races inside one session
share a regime and are not independent draws; treating them as independent
gives an interval far too narrow, which is how a coin flip starts looking like
a finding.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import numpy as np

from aggregate_stage07 import (
    DISTANCES,
    MIN_EVENTS,
    WIDTH_BINS,
    favourable_share,
    load,
)
from hvn.race import ADVERSE, AMBIGUOUS, CENSORED, FAVOURABLE
from hvn.tiers import TIERS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "outputs" / "stage_07_races"
RESAMPLES = 10000
SEED = 20260812
MIN_PAIR_EVENTS = 100

# Long constant names make the tables unreadable at this width.
SHORT = {
    "HIGH_NODE": "HVN",
    "LOW_NODE_INSIDE_VALUE": "LVN-in",
    "LOW_NODE_OUTSIDE_VALUE": "LVN-out",
    "VALUE_EDGE": "VA-edge",
    "SIGMA_EDGE": "sigma",
    "POC": "POC",
    "TPO_EXTREME": "time-gap",
    "VWAP_BAND": "VWAP",
}


def short(kind: str) -> str:
    return SHORT.get(kind, kind)


def decided(rows, distance):
    return [
        r for r in rows
        if r.get(f"race_{distance}") in (FAVOURABLE, ADVERSE)
    ]


# ---------------------------------------------------------------------------
# Question 3: stacked against single, with an honest interval


def session_matrix(events, tier_name, distance):
    """Per session: favourable and decided counts, single arm and stacked arm.

    Width-stratified: each event carries the weight its width band gives it, so
    the pooled difference is not dominated by whichever band happens to hold the
    most stacked events.
    """
    weights = {}
    for low, high in WIDTH_BINS:
        stratum = [
            e for e in events
            if e["tier"] == tier_name and low <= Decimal(e["width_atr"]) < high
        ]
        single = decided([e for e in stratum if e["level_kinds"] == 1], distance)
        stacked = decided([e for e in stratum if e["level_kinds"] >= 2], distance)
        if len(single) < MIN_EVENTS or len(stacked) < MIN_EVENTS:
            continue
        weights[(low, high)] = float(len(single))

    keyed: dict[str, np.ndarray] = {}
    for event in events:
        if event["tier"] != tier_name:
            continue
        outcome = event.get(f"race_{distance}")
        if outcome not in (FAVOURABLE, ADVERSE):
            continue
        width = Decimal(event["width_atr"])
        band = next(
            (b for b in weights if b[0] <= width < b[1]), None
        )
        if band is None:
            continue
        weight = weights[band] / sum(weights.values())
        row = keyed.setdefault(event["session"], np.zeros(4))
        arm = 0 if event["level_kinds"] == 1 else 2
        row[arm] += weight if outcome == FAVOURABLE else 0.0
        row[arm + 1] += weight
    if not keyed:
        return None
    return np.array([keyed[s] for s in sorted(keyed)])


def difference(matrix):
    totals = matrix.sum(0)
    if totals[1] <= 0 or totals[3] <= 0:
        return np.nan
    return 100 * (totals[2] / totals[3] - totals[0] / totals[1])


def bootstrap(matrix, resamples, seed):
    """Resample whole sessions, not events."""
    rng = np.random.default_rng(seed)
    n = len(matrix)
    draws = np.empty(resamples)
    for i in range(resamples):
        draws[i] = difference(matrix[rng.integers(0, n, n)])
    low, high = np.nanpercentile(draws, [2.5, 97.5])
    return float(low), float(high)


# ---------------------------------------------------------------------------
# Question 1: which kinds pair well


def pair_table(events, tier_name, distance):
    """Every kind-combination that appears often enough to read.

    Compared against the single-kind arm of the same tier, which is the only
    fair reference: a combination that beats other combinations but not a lone
    level has not shown that pairing helps.
    """
    pool = [e for e in events if e["tier"] == tier_name]
    base, base_n, _ = favourable_share(
        [e for e in pool if e["level_kinds"] == 1], distance
    )
    grouped: dict[tuple, list] = defaultdict(list)
    for event in pool:
        if event["level_kinds"] < 2:
            continue
        grouped[tuple(sorted(set(event["kinds"].split("|"))))].append(event)

    rows = []
    for kinds, members in grouped.items():
        rate, n, counts = favourable_share(members, distance)
        if rate is None or n < MIN_PAIR_EVENTS:
            continue
        rows.append({
            "kinds": " + ".join(short(k) for k in kinds),
            "n_kinds": len(kinds),
            "favourable_pct": round(float(rate), 2),
            "vs_single_pp": round(float(rate - base), 2) if base is not None else None,
            "decided": n,
            "censored": counts[CENSORED],
            "ambiguous": counts[AMBIGUOUS],
        })
    rows.sort(key=lambda r: -(r["vs_single_pp"] or 0))
    return base, base_n, rows


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="answer_stage07.py")
    parser.add_argument("--dir", type=Path, default=DEFAULT_IN)
    parser.add_argument("--resamples", type=int, default=RESAMPLES)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    events = load(args.dir)
    report = {"events": len(events), "sessions": len({e["session"] for e in events})}

    print("=" * 78)
    print("Q2 + Q3  how often levels hold, single against stacked")
    print("=" * 78)
    print(f"{'tier':>7} {'dist':>5} {'single':>8} {'stacked':>8} {'diff':>7} "
          f"{'95% interval':>18} {'n single':>9} {'n stacked':>10}")
    headline = []
    for tier_name in TIERS:
        for distance in DISTANCES:
            pool = [e for e in events if e["tier"] == tier_name]
            single_rate, single_n, _ = favourable_share(
                [e for e in pool if e["level_kinds"] == 1], distance
            )
            stacked_rate, stacked_n, _ = favourable_share(
                [e for e in pool if e["level_kinds"] >= 2], distance
            )
            matrix = session_matrix(events, tier_name, distance)
            if matrix is None or single_rate is None or stacked_rate is None:
                print(f"{tier_name:>7} {distance:>5}   too few events to read")
                continue
            observed = difference(matrix)
            low, high = bootstrap(matrix, args.resamples, args.seed)
            crosses = low <= 0 <= high
            print(
                f"{tier_name:>7} {distance:>5} {float(single_rate):>7.2f}% "
                f"{float(stacked_rate):>7.2f}% {observed:>+7.2f} "
                f"{f'[{low:+.2f}, {high:+.2f}]':>18} {single_n:>9} {stacked_n:>10}"
                f"{'' if crosses else '   <- excludes zero'}"
            )
            headline.append({
                "tier": tier_name,
                "distance_atr": distance,
                "single_pct": round(float(single_rate), 2),
                "stacked_pct": round(float(stacked_rate), 2),
                "difference_pp": round(observed, 2),
                "ci_low": round(low, 2),
                "ci_high": round(high, 2),
                "excludes_zero": not crosses,
                "sessions": len(matrix),
                "single_decided": single_n,
                "stacked_decided": stacked_n,
            })
    report["stacked_vs_single"] = headline

    print()
    print("=" * 78)
    print("Q1  which kinds are worth pairing")
    print("=" * 78)
    pairs = {}
    for tier_name in TIERS:
        for distance in DISTANCES:
            base, base_n, rows = pair_table(events, tier_name, distance)
            if not rows:
                print(f"\n{tier_name}, race to {distance} ATR: no combination "
                      f"reached {MIN_PAIR_EVENTS} decided races")
                continue
            pairs[f"{tier_name}_{distance}"] = rows
            print(f"\n{tier_name}, race to {distance} ATR "
                  f"(single-kind reference {float(base):.2f}%, n={base_n})")
            print(f"  {'combination':<44} {'holds':>7} {'vs 1':>7} {'n':>7}")
            for row in rows:
                print(f"  {row['kinds']:<44} {row['favourable_pct']:>6.2f}% "
                      f"{row['vs_single_pp']:>+7.2f} {row['decided']:>7}")
    report["pairs"] = pairs

    output = args.dir / "aggregate"
    output.mkdir(parents=True, exist_ok=True)
    (output / "answers.json").write_text(json.dumps(report, indent=1) + "\n")
    print(f"\nwritten to {output / 'answers.json'}")


if __name__ == "__main__":
    main()
