"""Interval and null test for the low-node excursion band, clustered by session.

The four-year sign agreement tells us the direction is stable. It does not tell
us the magnitude is distinguishable from zero, because the observations are not
independent: taps within a session share the same regime, the same volatility,
and often the same order flow. Treating them as independent draws would make any
interval far too narrow.

Both procedures here resample **whole sessions**, which is what keeps the
within-session correlation intact:

  bootstrap   draw sessions with replacement, recompute the treated-minus-control
              difference each time, and read the 2.5th and 97.5th percentiles of
              the resulting distribution. This is the confidence interval.

  permutation swap the treated and control labels of an entire session at random,
              recompute, and repeat. This builds the distribution the difference
              would have under the null that the labels carry no information, and
              the p-value is the share of that distribution at least as extreme
              as what was observed.

Treated and control are resampled together from the same drawn sessions, so a
session that happens to be volatile inflates both arms and cancels in the
difference, exactly as it does in the observed data.

The population is the first-touch reduction: one shelf, one session. The ladder
and the statistics were fixed before running; nothing here is selected on its
result.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from first_touch_population import LADDER, first_touch

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STUDY = ROOT / "outputs" / "stage_03_rotation_study"
TREATED = "TREATED"
CONTROL = "CONTROL_WIDTH_MATCHED"
RESAMPLES = 10000
SEED = 20260804
ALPHA = 5  # percent, two-sided


def session_matrices(events, node_class):
    """Per-session counts, exceedance counts per ladder level, and sums.

    Reducing each session to fixed-width vectors up front turns a resample into
    a matrix sum, which is what makes ten thousand of them cheap.
    """
    levels = np.array([float(level) for level in LADDER])
    keyed: dict[tuple, dict[str, list[float]]] = {}
    for row in events:
        if row["node_class"] != node_class:
            continue
        value = row.get("max_excursion_atr")
        if value in ("", None):
            continue
        key = (row["year"], row["session"])
        keyed.setdefault(key, {TREATED: [], CONTROL: []})[row["arm"]].append(
            float(value)
        )

    sessions = sorted(keyed)
    counts = np.zeros((len(sessions), 2))
    sums = np.zeros((len(sessions), 2))
    above = np.zeros((len(sessions), 2, len(levels)))
    for index, key in enumerate(sessions):
        for arm_index, arm in enumerate((TREATED, CONTROL)):
            values = np.array(keyed[key][arm])
            counts[index, arm_index] = values.size
            if values.size:
                sums[index, arm_index] = values.sum()
                above[index, arm_index] = (values[:, None] >= levels[None, :]).sum(0)
    return sessions, counts, sums, above


def statistics(counts, sums, above):
    """Treated-minus-control: mean excursion, then exceedance at each level."""
    totals = counts.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = np.where(totals > 0, sums.sum(0) / totals, np.nan)
        shares = np.where(
            totals[:, None] > 0, above.sum(0) * 100 / totals[:, None], np.nan
        )
    return means[0] - means[1], shares[0] - shares[1]


def run(events, node_class, resamples, seed):
    sessions, counts, sums, above = session_matrices(events, node_class)
    n = len(sessions)
    observed_mean, observed_shares = statistics(counts, sums, above)

    rng = np.random.default_rng(seed)
    boot_mean = np.empty(resamples)
    boot_shares = np.empty((resamples, len(LADDER)))
    null_mean = np.empty(resamples)
    null_shares = np.empty((resamples, len(LADDER)))

    for i in range(resamples):
        draw = rng.integers(0, n, n)
        boot_mean[i], boot_shares[i] = statistics(
            counts[draw], sums[draw], above[draw]
        )
        # Null: the arm label of a whole session is exchangeable.
        flip = rng.random(n) < 0.5
        order = np.where(flip[:, None], [1, 0], [0, 1])
        rows = np.arange(n)[:, None]
        null_mean[i], null_shares[i] = statistics(
            counts[rows, order], sums[rows, order], above[rows, order, :]
        )

    def summarise(observed, boot, null):
        low, high = np.nanpercentile(boot, [ALPHA / 2, 100 - ALPHA / 2])
        centred = null - np.nanmean(null)
        p = float((np.abs(centred) >= abs(observed)).mean())
        return {
            "observed": round(float(observed), 4),
            "ci_low": round(float(low), 4),
            "ci_high": round(float(high), 4),
            "excludes_zero": bool(low > 0 or high < 0),
            "permutation_p": round(p, 4),
        }

    out = {
        "node_class": node_class,
        "sessions": n,
        "treated_events": int(counts[:, 0].sum()),
        "control_events": int(counts[:, 1].sum()),
        "resamples": resamples,
        "seed": seed,
        "mean_excursion_atr": summarise(observed_mean, boot_mean, null_mean),
        "exceedance": [],
    }
    for index, level in enumerate(LADDER):
        row = summarise(
            observed_shares[index], boot_shares[:, index], null_shares[:, index]
        )
        row["excursion_atr"] = str(level)
        out["exceedance"].append(row)
    return out


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="bootstrap_lvn_excursion.py")
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    parser.add_argument("--resamples", type=int, default=RESAMPLES)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    events, _ = first_touch(args.study)
    output = args.study / "aggregate" / "first_touch"
    output.mkdir(parents=True, exist_ok=True)

    results = [
        run(events, node_class, args.resamples, args.seed)
        for node_class in ("LOW_VOLUME_NODE", "HIGH_VOLUME_NODE")
    ]
    (output / "bootstrap.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n"
    )

    fields = [
        "node_class",
        "metric",
        "observed",
        "ci_low",
        "ci_high",
        "excludes_zero",
        "permutation_p",
    ]
    with (output / "bootstrap.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            for metric, row in [("mean_excursion_atr", result["mean_excursion_atr"])] + [
                (f"reaching_{r['excursion_atr']}atr_pp", r) for r in result["exceedance"]
            ]:
                writer.writerow(
                    {"node_class": result["node_class"], "metric": metric}
                    | {k: row[k] for k in fields[2:]}
                )
    for result in results:
        print(result["node_class"], result["sessions"], "sessions",
              result["mean_excursion_atr"])


if __name__ == "__main__":
    main()
