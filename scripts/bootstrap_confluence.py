"""Interval and null test for the confluence result, clustered by session.

Same procedure as `bootstrap_lvn_excursion.py`, applied to the Stage 4
population: resample whole sessions with replacement for the interval, and swap
whole sessions' arm labels for the null. Observations inside a session share a
regime and are not independent draws, so anything that treats them as such gives
an interval far too narrow.

What is bootstrapped here is deliberately narrow. The Stage 4 claim is
*monotonicity in confluence degree*, so the quantity of interest is not any one
cell but the **span** — the treated-minus-control difference at the highest
supported degree minus the difference at the lowest. If that span's interval
covers zero, agreement between sources buys nothing, whatever individual cells
happen to look like.

Both the per-degree differences and the span are reported, so a reader can see
the cells the span was computed from rather than taking it on trust.
"""

from __future__ import annotations

import argparse
import csv
import json
from decimal import Decimal
from pathlib import Path

import numpy as np

from aggregate_confluence_study import (
    CONTROL,
    DEGREES,
    TREATED,
    degree_bucket,
    is_true,
    load_first_touch,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STUDY = ROOT / "outputs" / "stage_04_confluence_study"
RESAMPLES = 10000
SEED = 20260807
ALPHA = 5
MIN_EVENTS = 30


def session_matrices(events, timeframe, tolerance, metric):
    """Per-session sums and counts, per arm and degree bucket.

    Columns are [control, degree 1, degree 2, degree 3, degree 4+] so a resample
    is a matrix sum and ten thousand of them stay cheap.
    """
    keyed: dict[tuple, list[list[float]]] = {}
    for row in events:
        if row["atr_timeframe"] != timeframe or row["tolerance_atr"] != tolerance:
            continue
        value = metric(row)
        if value is None:
            continue
        key = (row["year"], row["session"])
        slot = keyed.setdefault(key, [[] for _ in range(1 + len(DEGREES))])
        if row["arm"] == CONTROL:
            slot[0].append(value)
        elif row["arm"] == TREATED:
            slot[degree_bucket(int(row["degree"]))].append(value)

    sessions = sorted(keyed)
    width = 1 + len(DEGREES)
    counts = np.zeros((len(sessions), width))
    sums = np.zeros((len(sessions), width))
    for index, key in enumerate(sessions):
        for column, values in enumerate(keyed[key]):
            counts[index, column] = len(values)
            sums[index, column] = float(sum(values))
    return sessions, counts, sums


def differences(counts, sums):
    """Treated-minus-control mean per degree bucket."""
    totals = counts.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = np.where(totals > 0, sums.sum(0) / totals, np.nan)
    return means[1:] - means[0]


def run(events, timeframe, tolerance, metric_name, metric, resamples, seed):
    sessions, counts, sums = session_matrices(events, timeframe, tolerance, metric)
    if not sessions:
        return None
    n = len(sessions)
    observed = differences(counts, sums)
    supported = [
        i
        for i in range(len(DEGREES))
        if counts[:, i + 1].sum() >= MIN_EVENTS and counts[:, 0].sum() >= MIN_EVENTS
    ]
    if len(supported) < 2:
        return {
            "atr_timeframe": timeframe,
            "tolerance_atr": tolerance,
            "metric": metric_name,
            "verdict": "UNTESTABLE_TOO_FEW_DEGREES",
        }
    low_degree, high_degree = supported[0], supported[-1]
    observed_span = observed[high_degree] - observed[low_degree]

    rng = np.random.default_rng(seed)
    boot = np.empty((resamples, len(DEGREES)))
    boot_span = np.empty(resamples)
    null_span = np.empty(resamples)
    for i in range(resamples):
        draw = rng.integers(0, n, n)
        values = differences(counts[draw], sums[draw])
        boot[i] = values
        boot_span[i] = values[high_degree] - values[low_degree]
        # Null: the arm label of a whole session carries no information, so the
        # treated columns and the control column are exchangeable within it.
        flip = rng.random(n) < 0.5
        swapped_counts = counts[draw].copy()
        swapped_sums = sums[draw].copy()
        rows = np.where(flip)[0]
        for column in (low_degree + 1, high_degree + 1):
            swapped_counts[rows, 0], swapped_counts[rows, column] = (
                counts[draw][rows, column],
                counts[draw][rows, 0],
            )
            swapped_sums[rows, 0], swapped_sums[rows, column] = (
                sums[draw][rows, column],
                sums[draw][rows, 0],
            )
        nulls = differences(swapped_counts, swapped_sums)
        null_span[i] = nulls[high_degree] - nulls[low_degree]

    def interval(samples, point):
        lo, hi = np.nanpercentile(samples, [ALPHA / 2, 100 - ALPHA / 2])
        return {
            "observed": round(float(point), 4),
            "ci_low": round(float(lo), 4),
            "ci_high": round(float(hi), 4),
            "excludes_zero": bool(lo > 0 or hi < 0),
        }

    centred = null_span - np.nanmean(null_span)
    return {
        "atr_timeframe": timeframe,
        "tolerance_atr": tolerance,
        "metric": metric_name,
        "sessions": n,
        "low_degree": DEGREES[low_degree],
        "high_degree": DEGREES[high_degree],
        "per_degree": {
            str(DEGREES[i]): interval(boot[:, i], observed[i])
            for i in supported
        },
        "span": interval(boot_span, observed_span)
        | {"permutation_p": round(float((np.abs(centred) >= abs(observed_span)).mean()), 4)},
        "verdict": (
            "SPAN_EXCLUDES_ZERO"
            if interval(boot_span, observed_span)["excludes_zero"]
            else "SPAN_COVERS_ZERO"
        ),
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="bootstrap_confluence.py")
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    parser.add_argument("--resamples", type=int, default=RESAMPLES)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    events = load_first_touch(args.study)
    output = args.study / "aggregate"
    output.mkdir(parents=True, exist_ok=True)

    def excursion(row):
        value = row.get("max_excursion_atr")
        return None if value in ("", None) else float(value)

    def rotated_20(row):
        if is_true(row.get("censored_20b")):
            return None
        return 100.0 if is_true(row.get("rotated_20b")) else 0.0

    metrics = [("mean_excursion_atr", excursion), ("rotated_20b_pct", rotated_20)]
    results = []
    for timeframe in sorted({e["atr_timeframe"] for e in events}):
        for tolerance in sorted({e["tolerance_atr"] for e in events}, key=Decimal):
            for name, metric in metrics:
                result = run(
                    events, timeframe, tolerance, name, metric,
                    args.resamples, args.seed,
                )
                if result:
                    results.append(result)

    (output / "bootstrap.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n"
    )
    fields = [
        "metric", "atr_timeframe", "tolerance_atr", "sessions",
        "low_degree", "high_degree", "span_observed", "span_ci_low",
        "span_ci_high", "span_excludes_zero", "permutation_p", "verdict",
    ]
    with (output / "bootstrap.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            span = result.get("span", {})
            writer.writerow(
                {
                    "metric": result["metric"],
                    "atr_timeframe": result["atr_timeframe"],
                    "tolerance_atr": result["tolerance_atr"],
                    "sessions": result.get("sessions", ""),
                    "low_degree": result.get("low_degree", ""),
                    "high_degree": result.get("high_degree", ""),
                    "span_observed": span.get("observed", ""),
                    "span_ci_low": span.get("ci_low", ""),
                    "span_ci_high": span.get("ci_high", ""),
                    "span_excludes_zero": span.get("excludes_zero", ""),
                    "permutation_p": span.get("permutation_p", ""),
                    "verdict": result["verdict"],
                }
            )
    for result in results:
        print(result["metric"], result["atr_timeframe"], result["tolerance_atr"],
              result["verdict"], result.get("span", {}))


if __name__ == "__main__":
    main()
