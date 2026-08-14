"""Two questions that were left open, settled with intervals.

  1  stacked against single    is the excursion asymmetry of stacked barriers
                               actually different from single-kind ones? The
                               per-group numbers hinted at it; the difference
                               itself was never tested.

  2  level against no level    the target/stop grid came out positive in every
                               cell. A barrier is a level *and* a place price
                               stalled, and the tap rule selects on the stall.
                               The control arm places the same band, same width,
                               same side, where no level is. If the tilt is the
                               same there, it belongs to the tap rule and not to
                               levels.

Both use a session-clustered bootstrap. Races inside one session share a regime
and are not independent draws; an event-level interval would be far too narrow.

The width confound is handled by reporting the stacked-single difference inside
width bands as well as pooled: stacked barriers are wider *and* occur in quieter
conditions -- their excursions are smaller on both sides -- so an unstratified
comparison is between different regimes rather than between different barriers.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

import numpy as np

from aggregate_stage07 import WIDTH_BINS, load

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TREATED = ROOT / "outputs" / "stage_07_races"
DEFAULT_CONTROL = ROOT / "outputs" / "stage_07_control"
RESAMPLES = 10000
SEED = 20260815
MIN_EVENTS = 200
DIAGONAL = ("1.0", "2.0", "3.0", "4.0", "5.0")


def paired_sessions(left, right, value):
    """Per-session sums and counts for two groups, on a common session index."""
    keys = sorted({e["session"] for e in left} | {e["session"] for e in right})
    index = {key: i for i, key in enumerate(keys)}
    sums = np.zeros((len(keys), 2))
    counts = np.zeros((len(keys), 2))
    for column, group in enumerate((left, right)):
        for event in group:
            result = value(event)
            if result is None:
                continue
            row = index[event["session"]]
            sums[row, column] += result
            counts[row, column] += 1
    return sums, counts


def difference(sums, counts):
    totals = counts.sum(0)
    if totals[0] == 0 or totals[1] == 0:
        return np.nan
    means = sums.sum(0) / totals
    return means[0] - means[1]


def interval(sums, counts, resamples, seed):
    rng = np.random.default_rng(seed)
    n = len(sums)
    if n == 0:
        return None
    observed = difference(sums, counts)
    draws = np.empty(resamples)
    for i in range(resamples):
        pick = rng.integers(0, n, n)
        draws[i] = difference(sums[pick], counts[pick])
    low, high = np.nanpercentile(draws, [2.5, 97.5])
    return {
        "observed": round(float(observed), 4),
        "ci_low": round(float(low), 4),
        "ci_high": round(float(high), 4),
        "excludes_zero": bool(low > 0 or high < 0),
        "n_left": int(counts[:, 0].sum()),
        "n_right": int(counts[:, 1].sum()),
        "sessions": n,
    }


def asymmetry(event):
    if "mfe_atr" not in event:
        return None
    return event["mfe_atr"] - event["mae_atr"]


def diagonal_tilt(event, distance):
    """+1 if favourable reached `distance` first, -1 if adverse, else None.

    On the diagonal the mirror is exactly the sign flip, so the mean of this is
    the mirrored edge with no separate control needed.
    """
    favourable = event.get("favourable_bar", {}).get(distance)
    adverse = event.get("adverse_bar", {}).get(distance)
    if favourable is None and adverse is None:
        return None
    if adverse is None:
        return 1.0
    if favourable is None:
        return -1.0
    if favourable < adverse:
        return 1.0
    if adverse < favourable:
        return -1.0
    return None


def report(label, result):
    if result is None:
        print(f"{label:<44} too few events")
        return
    flag = "   <- excludes zero" if result["excludes_zero"] else ""
    span = f"[{result['ci_low']:+.4f}, {result['ci_high']:+.4f}]"
    print(f"{label:<44} {result['observed']:>+9.4f} {span:>22} "
          f"{result['n_left']:>7} {result['n_right']:>7}{flag}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="settle_stage07.py")
    parser.add_argument("--treated", type=Path, default=DEFAULT_TREATED)
    parser.add_argument("--control", type=Path, default=DEFAULT_CONTROL)
    parser.add_argument("--resamples", type=int, default=RESAMPLES)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    treated = load(args.treated)
    report_out: dict = {}

    print("=" * 90)
    print("1  stacked minus single, difference in (MFE - MAE), in ATR")
    print("=" * 90)
    print(f"{'group':<44} {'diff':>9} {'95% interval':>22} "
          f"{'n stack':>7} {'n one':>7}")
    stacked = [e for e in treated if e["level_kinds"] >= 2]
    single = [e for e in treated if e["level_kinds"] == 1]
    pooled = interval(
        *paired_sessions(stacked, single, asymmetry), args.resamples, args.seed
    )
    report("pooled", pooled)
    report_out["stacked_minus_single"] = {"pooled": pooled, "by_width": {}}

    for low, high in WIDTH_BINS:
        band = f"{low}-{high}"
        left = [e for e in stacked if low <= Decimal(e["width_atr"]) < high]
        right = [e for e in single if low <= Decimal(e["width_atr"]) < high]
        if len(left) < MIN_EVENTS or len(right) < MIN_EVENTS:
            continue
        result = interval(
            *paired_sessions(left, right, asymmetry), args.resamples, args.seed
        )
        report(f"  width {band} ATR", result)
        report_out["stacked_minus_single"]["by_width"][band] = result

    print()
    print("=" * 90)
    print("2  level minus no-level: same band, same width, same side")
    print("=" * 90)
    if not args.control.exists() or not any(args.control.glob("*.json")):
        print(f"no control ledger at {args.control}")
        print("run:  PYTHONPATH=src:scripts python3 scripts/run_stage07.py --control")
        report_out["treated_minus_control"] = None
    else:
        control = load(args.control)
        print(f"{'quantity':<44} {'diff':>9} {'95% interval':>22} "
              f"{'n level':>7} {'n none':>7}")
        rows: dict = {}
        result = interval(
            *paired_sessions(treated, control, asymmetry),
            args.resamples, args.seed,
        )
        report("MFE - MAE", result)
        rows["asymmetry"] = result
        for distance in DIAGONAL:
            def tilt(event, _d=distance):
                return diagonal_tilt(event, _d)

            result = interval(
                *paired_sessions(treated, control, tilt), args.resamples, args.seed
            )
            report(f"reversal tilt at {distance} ATR", result)
            rows[f"tilt_{distance}"] = result

        # The tilt each arm shows on its own, so "the control has it too" is
        # visible rather than inferred from the difference alone.
        print()
        print(f"{'':<44} {'level':>12} {'no level':>12}")
        for distance in DIAGONAL:
            values = []
            for group in (treated, control):
                scores = [
                    diagonal_tilt(e, distance) for e in group
                ]
                scores = [s for s in scores if s is not None]
                values.append(100 * (np.mean(scores) + 1) / 2 if scores else float("nan"))
            print(f"favourable-first % at {distance} ATR{'':<18} "
                  f"{values[0]:>11.2f}% {values[1]:>11.2f}%")
            rows[f"share_{distance}"] = {
                "treated_pct": round(float(values[0]), 2),
                "control_pct": round(float(values[1]), 2),
            }
        report_out["treated_minus_control"] = rows

    output = args.treated / "aggregate"
    output.mkdir(parents=True, exist_ok=True)
    (output / "settle.json").write_text(json.dumps(report_out, indent=1) + "\n")
    print(f"\nwritten to {output / 'settle.json'}")


if __name__ == "__main__":
    main()
