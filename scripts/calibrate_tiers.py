"""How many levels does each tier emit? Frequency only — no outcomes here.

This is the script that sets the tier constants, and it is deliberately unable
to see whether a level reverses price. It counts levels, clusters and distinct
kinds per anchor, and nothing else. The tiers are adjusted until the counts sit
where they should, the constants are frozen, and only then does anything
outcome-shaped get run.

Keeping the calibration in a separate script from the aggregation is not
ceremony. It is the only structural reason to believe the thresholds were not
nudged after somebody saw a result they liked.
"""

from __future__ import annotations

import argparse
import json
import statistics
from bisect import bisect_right
from datetime import date
from decimal import Decimal
from pathlib import Path

from hvn.atr import wilder_atr
from hvn.bucket_histogram import BucketStore
from hvn.confluence import MAX_CLUSTER_WIDTH_ATR, cluster_levels
from hvn.profile_sources import resample
from hvn.rolling_profile import reanchor_times
from hvn.stage02_pipeline import AtrSelector
from hvn.stage7_levels import build_level_set
from hvn.tiers import TIERS, tier

ROOT = Path(__file__).resolve().parents[1]
BUCKETS = ROOT / "outputs" / "stage_07_buckets"
DEFAULT_OUT = ROOT / "outputs" / "stage_07_calibration"
EPOCH = date(1970, 1, 1)
ROLLING_SESSIONS = 20
ATR_MINUTES = 5
ATR_PERIOD = 14
TOLERANCE_ATR = Decimal("1.00")
# A level further than this from price is not something a reader would call a
# level "near price"; counted separately so the strict tier's rarity is visible.
NEAR_ATR = Decimal("2.0")


def describe(values):
    if not values:
        return {"anchors": 0}
    return {
        "anchors": len(values),
        "mean": round(statistics.fmean(values), 2),
        "median": statistics.median(values),
        "p90": sorted(values)[int(len(values) * 0.9)],
        "max": max(values),
        "zero_share_pct": round(100 * sum(1 for v in values if v == 0) / len(values), 1),
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="calibrate_tiers.py")
    parser.add_argument("--sessions", type=int, default=20)
    parser.add_argument("--buckets", type=Path, default=BUCKETS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    from run_stage06_reversal import minute_bars
    from run_stage07 import open_source

    store = BucketStore(args.buckets)
    parquet, instrument_by_day = open_source()
    eligible = [
        s for s in store.sessions
        if len(store.trailing(s, ROLLING_SESSIONS + 1)) == ROLLING_SESSIONS + 1
    ]
    chosen = eligible[-args.sessions:] if args.sessions else eligible

    levels = {name: [] for name in TIERS}
    clusters = {name: [] for name in TIERS}
    near = {name: [] for name in TIERS}
    kinds = {name: [] for name in TIERS}

    for session in chosen:
        day = (date.fromisoformat(session) - EPOCH).days
        bars = minute_bars(parquet, {day - 1, day}, instrument_by_day)
        if len(bars) < 400:
            continue
        five = tuple(resample(bars, ATR_MINUTES))
        if len(five) < ATR_PERIOD + 2:
            continue
        atrs = AtrSelector(wilder_atr(five, period=ATR_PERIOD))
        times = [b.close_time for b in bars]
        for anchor in reanchor_times(bars, minutes=60):
            try:
                atr = atrs.before(anchor).value
            except (ValueError, IndexError):
                continue
            if atr <= 0:
                continue
            index = bisect_right(times, anchor)
            if index == 0:
                continue
            price = bars[index - 1].close
            for name in TIERS:
                level_set = build_level_set(
                    store, session, anchor, atr=atr, spec=tier(name)
                )
                level_set.assert_causal()
                grouped = cluster_levels(
                    level_set.levels,
                    tolerance=TOLERANCE_ATR * atr,
                    max_width=MAX_CLUSTER_WIDTH_ATR * atr,
                )
                levels[name].append(len(level_set.levels))
                clusters[name].append(len(grouped))
                near[name].append(
                    sum(
                        1 for c in grouped
                        if min(abs(c.low - price), abs(c.high - price)) <= NEAR_ATR * atr
                    )
                )
                kinds[name].append(len({le.kind for le in level_set.levels}))
        print(f"{session}: done", flush=True)

    report = {
        name: {
            "levels_per_anchor": describe(levels[name]),
            "clusters_per_anchor": describe(clusters[name]),
            "clusters_within_2atr": describe(near[name]),
            "distinct_kinds_per_anchor": describe(kinds[name]),
        }
        for name in TIERS
    }
    report["sessions"] = chosen
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "frequency.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "sessions"}, indent=1))


if __name__ == "__main__":
    main()
