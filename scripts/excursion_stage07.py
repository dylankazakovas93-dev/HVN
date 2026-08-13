"""Magnitude, not direction: how far price travels each way after a touch.

The race said direction is a coin flip. That leaves one way these levels could
still carry information — **asymmetry in size**. Price might turn and run four
ATR half the time and break and drift one and a half the other half, and a
binary race is blind to it by construction.

Three things:

  1  excursion    MFE and MAE distributions, as quartiles rather than means. A
                  mean hides exactly the skew being looked for, and a single
                  violent session moves it.
  2  asymmetry    MFE minus MAE per event, with a session-clustered bootstrap.
                  This is the whole question stated as one number.
  3  brackets     every target/stop pair on the recorded grid: how often the
                  target is reached first, and the expectancy in ATR.

**The bracket grid is read, never re-simulated.** The scan recorded the bar at
which each distance was first reached in each direction, so a 3 ATR target
against a 1 ATR stop is a comparison of two integers. Nothing here re-walks a
price series, which is why any pair can be asked about without another scan.

Censoring is reported beside every bracket cell and never folded into it. An
event where neither side was reached inside the window did not "lose"; it did
not resolve, and averaging it in as a zero would flatter every wide target.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from aggregate_stage07 import load
from hvn.race import BRACKET_GRID
from hvn.tiers import TIERS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "outputs" / "stage_07_races"
RESAMPLES = 10000
SEED = 20260814
MIN_EVENTS = 200
GRID = [str(d) for d in BRACKET_GRID]

# A cell where most events never resolved is not a result, it is an artifact.
# On synthetic data with no signal at all, the highest-expectancy cell was a
# 3 ATR target against a 5 ATR stop: +2.10 ATR, 88.7% target-first, and 80.8%
# censored. A stop that wide is rarely reached inside the window, so the target
# wins by default among whatever remainder resolved. Every naive target/stop
# grid points at its widest stop for this reason, and it means nothing.
MAX_CENSORED_PCT = 33.0


def has_excursions(events) -> bool:
    return any("mfe_atr" in e for e in events)


def quartiles(values):
    if not values:
        return None
    array = np.array(values, dtype=float)
    return {
        "p25": round(float(np.percentile(array, 25)), 3),
        "median": round(float(np.percentile(array, 50)), 3),
        "p75": round(float(np.percentile(array, 75)), 3),
        "p90": round(float(np.percentile(array, 90)), 3),
        "mean": round(float(array.mean()), 3),
        "n": len(array),
    }


def session_means(events, value):
    """Per-session mean of `value`, so the bootstrap can resample whole days."""
    grouped = defaultdict(list)
    for event in events:
        result = value(event)
        if result is not None:
            grouped[event["session"]].append(result)
    keys = sorted(grouped)
    sums = np.array([sum(grouped[k]) for k in keys], dtype=float)
    counts = np.array([len(grouped[k]) for k in keys], dtype=float)
    return sums, counts


def bootstrap_mean(sums, counts, resamples, seed):
    rng = np.random.default_rng(seed)
    n = len(sums)
    if n == 0:
        return None
    observed = sums.sum() / counts.sum()
    draws = np.empty(resamples)
    for i in range(resamples):
        pick = rng.integers(0, n, n)
        draws[i] = sums[pick].sum() / counts[pick].sum()
    low, high = np.percentile(draws, [2.5, 97.5])
    return {
        "observed": round(float(observed), 4),
        "ci_low": round(float(low), 4),
        "ci_high": round(float(high), 4),
        "excludes_zero": bool(low > 0 or high < 0),
    }


def _race_counts(events, target: str, stop: str, first: str, second: str):
    """How often `first` reaches `target` before `second` reaches `stop`."""
    target_first = stop_first = ambiguous = censored = 0
    for event in events:
        near = event.get(first, {}).get(target)
        far = event.get(second, {}).get(stop)
        if near is None and far is None:
            censored += 1
        elif far is None:
            target_first += 1
        elif near is None:
            stop_first += 1
        elif near < far:
            target_first += 1
        elif far < near:
            stop_first += 1
        else:
            # Both on the same bar. OHLC does not order them, so neither wins.
            ambiguous += 1
    return target_first, stop_first, ambiguous, censored


def bracket_cell(events, target: str, stop: str):
    """Target/stop outcome, and the same thing mirrored, which is the control.

    Dropping unresolved events biases every cell toward the near side: a wide
    stop is rarely reached inside the window, so the target wins by default
    among whatever remains. On synthetic data with no signal at all this
    produced +0.66 ATR and 93% target-first at a 1 ATR target against a 4 ATR
    stop. No censoring threshold fixes that — it only relocates it.

    The mirror does fix it. Swapping which side is the target and which is the
    stop leaves the censoring identical, so under the null that direction
    carries no information the two must agree. **`edge_pp` is the number to
    read**; the raw expectancy beside it is what the same cell would show if
    price moved at random, and the two are usually indistinguishable.
    """
    target_first, stop_first, ambiguous, censored = _race_counts(
        events, target, stop, "favourable_bar", "adverse_bar"
    )
    mirror_first, mirror_stop, _, _ = _race_counts(
        events, target, stop, "adverse_bar", "favourable_bar"
    )
    resolved = target_first + stop_first
    mirror_resolved = mirror_first + mirror_stop
    if resolved < MIN_EVENTS or mirror_resolved < MIN_EVENTS:
        return None
    share = target_first / resolved
    mirror_share = mirror_first / mirror_resolved
    expectancy = share * float(target) - (1 - share) * float(stop)
    mirror_expectancy = mirror_share * float(target) - (1 - mirror_share) * float(stop)
    return {
        "target_atr": float(target),
        "stop_atr": float(stop),
        "target_first_pct": round(100 * share, 2),
        "mirror_first_pct": round(100 * mirror_share, 2),
        "edge_pp": round(100 * (share - mirror_share), 2),
        "expectancy_atr": round(expectancy, 4),
        "mirror_expectancy_atr": round(mirror_expectancy, 4),
        "expectancy_edge_atr": round(expectancy - mirror_expectancy, 4),
        "resolved": resolved,
        "censored": censored,
        "ambiguous": ambiguous,
        "censored_pct": round(100 * censored / max(1, len(events)), 1),
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="excursion_stage07.py")
    parser.add_argument("--dir", type=Path, default=DEFAULT_IN)
    parser.add_argument("--resamples", type=int, default=RESAMPLES)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    events = load(args.dir)
    if not has_excursions(events):
        raise SystemExit(
            "this ledger has no excursion fields; re-run the scan with the "
            "current runner (rm -rf outputs/stage_07_races && ./scripts/stage07.sh)"
        )
    report = {"events": len(events), "sessions": len({e["session"] for e in events})}

    print("=" * 78)
    print("1  how far price travels, in ATR, after the touch")
    print("=" * 78)
    print(f"{'group':>22} {'':>8} {'p25':>7} {'median':>7} {'p75':>7} {'p90':>7} {'n':>7}")
    distributions = {}
    groups = [("ALL", events)]
    groups += [(t, [e for e in events if e["tier"] == t]) for t in TIERS]
    groups += [
        ("single kind", [e for e in events if e["level_kinds"] == 1]),
        ("stacked 2+", [e for e in events if e["level_kinds"] >= 2]),
    ]
    for name, rows in groups:
        for label, field in (("favourable", "mfe_atr"), ("adverse", "mae_atr")):
            stats = quartiles([e[field] for e in rows if field in e])
            if stats is None:
                continue
            distributions[f"{name}|{label}"] = stats
            print(f"{name:>22} {label:>10} {stats['p25']:>7.2f} "
                  f"{stats['median']:>7.2f} {stats['p75']:>7.2f} "
                  f"{stats['p90']:>7.2f} {stats['n']:>7}")
    report["excursion"] = distributions

    print()
    print("=" * 78)
    print("2  is the favourable side bigger than the adverse side?")
    print("=" * 78)
    print(f"{'group':>22} {'MFE-MAE':>9} {'95% interval':>20}")
    asymmetry = {}
    for name, rows in groups:
        sums, counts = session_means(
            rows, lambda e: e["mfe_atr"] - e["mae_atr"] if "mfe_atr" in e else None
        )
        result = bootstrap_mean(sums, counts, args.resamples, args.seed)
        if result is None:
            continue
        asymmetry[name] = result
        flag = "" if not result["excludes_zero"] else "   <- excludes zero"
        interval = f"[{result['ci_low']:+.4f}, {result['ci_high']:+.4f}]"
        print(f"{name:>22} {result['observed']:>+9.4f} {interval:>20}{flag}")
    report["asymmetry"] = asymmetry

    print()
    print("=" * 78)
    print("3  target / stop grid — expectancy ABOVE ITS MIRROR, in ATR")
    print("=" * 78)
    grid_out = {}
    for name, rows in (("ALL", events), ("stacked 2+", [e for e in events
                                                        if e["level_kinds"] >= 2])):
        print(f"\n{name}")
        header = "  " + "target\\stop".ljust(12) + "".join(f"{s:>9}" for s in GRID)
        print(header)
        cells = []
        for target in GRID:
            line = "  " + target.ljust(12)
            for stop in GRID:
                cell = bracket_cell(rows, target, stop)
                if cell is None:
                    line += f"{'-':>9}"
                    continue
                cells.append(cell)
                mark = "*" if cell["censored_pct"] > MAX_CENSORED_PCT else " "
                line += f"{cell['expectancy_edge_atr']:>+8.3f}{mark}"
            print(line)
        grid_out[name] = cells
        readable = [c for c in cells if c["censored_pct"] <= MAX_CENSORED_PCT]
        print(f"  * more than {MAX_CENSORED_PCT:.0f}% of events never resolved; "
              f"those cells are artifacts of the window, not results")
        best = max(readable, key=lambda c: c["expectancy_edge_atr"], default=None)
        if best is None:
            print("  no cell resolved often enough to read")
            continue
        print(f"  best readable cell: target {best['target_atr']} / stop "
              f"{best['stop_atr']} -> edge {best['expectancy_edge_atr']:+.3f} ATR "
              f"(raw {best['expectancy_atr']:+.3f}, mirror "
              f"{best['mirror_expectancy_atr']:+.3f})")
        print(f"    target first {best['target_first_pct']}% against mirror "
              f"{best['mirror_first_pct']}%, edge {best['edge_pp']:+.2f}pp, "
              f"n={best['resolved']}, censored {best['censored_pct']}%")
    report["brackets"] = grid_out

    output = args.dir / "aggregate"
    output.mkdir(parents=True, exist_ok=True)
    (output / "excursion.json").write_text(json.dumps(report, indent=1) + "\n")
    print(f"\nwritten to {output / 'excursion.json'}")


if __name__ == "__main__":
    main()
