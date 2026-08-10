"""Stage 7: three level tiers, one-second inputs everywhere, measured as a race.

Three things change from Stage 6, and only these three:

  inputs     all nine sources read half-hour one-second buckets. Stage 6 read
             them for the composite alone and took the other eight from
             one-minute bars, which made "does the result survive accurate
             volume" unanswerable.

  tiers      loose, medium and strict level definitions, frozen on frequency
             before any outcome exists. One threshold is a guess; three ordered
             by selectivity is a test.

  outcome    a race to +/- 1, 3 and 5 ATR from the touch price, not a state at
             a fixed clock. "Did the level hold" and "where was price two hours
             later" are different questions and Stage 5-6 asked the second.

ATR is 5-minute Wilder throughout. The 1-minute/5-minute axis is gone, which
halves the cell count and with it the multiple-testing surface.

**Clustering tolerance is fixed at 1.00 ATR.** Earlier stages swept three, which
tripled the cells for an axis nobody was asking about; the middle value is kept
and stated rather than searched.

Work is written per session and skipped if present, so an interrupted run
resumes where it stopped.
"""

from __future__ import annotations

import argparse
import json
from bisect import bisect_right
from datetime import date
from decimal import Decimal
from pathlib import Path

from hvn.atr import wilder_atr
from hvn.bucket_histogram import BucketStore
from hvn.confluence import (
    ABOVE,
    MAX_CLUSTER_WIDTH_ATR,
    cluster_levels,
    nearest_barriers,
)
from hvn.profile_sources import resample
from hvn.race import DISTANCES_ATR, all_races
from hvn.range_reader import HTTPRangeReader
from hvn.rolling_profile import Node, find_tap, reanchor_times
from hvn.stage02_pipeline import AtrSelector
from hvn.stage7_levels import build_level_set
from hvn.tiers import TIERS, tier

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "outputs" / "stage_07_races"
BUCKETS = ROOT / "outputs" / "stage_07_buckets"
FILE_ID = "1aop7eaNO56pM9kZKyxelMcD6Uf8fG-Yf"
EPOCH = date(1970, 1, 1)

IS_YEARS = (2010, 2011, 2012, 2019, 2021, 2023, 2025)
ROLLING_SESSIONS = 20

# Frozen interaction parameters.
TOLERANCE_ATR = Decimal("1.00")
TAP_SEARCH_BARS = 60
TAP_BAND_ATR = Decimal("0.5")
TAP_MIN_BARS = 3
# Long enough that a 5 ATR race is usually decided rather than censored, and
# short enough that "after the tap" still means something.
FORWARD_BARS = 240
LIVE_BARS = TAP_SEARCH_BARS + TAP_MIN_BARS + FORWARD_BARS
ATR_MINUTES = 5
ATR_PERIOD = 14


def measure(forward, cluster, *, atr, direction, base) -> dict:
    """Tap the cluster, then race the brackets at each distance."""
    low, high = cluster.low, cluster.high
    node = Node(
        node_class="BARRIER", low_index=0, high_index=0,
        node_low=low, node_high=high, peak_index=0,
        peak_price=(low + high) / 2, smoothed_activity=Decimal(0),
        activity_percentile=Decimal(0), anchor_time=base["anchor_time_dt"],
    )
    tap = find_tap(
        forward[:TAP_SEARCH_BARS], node, atr=atr,
        max_distance_atr=TAP_BAND_ATR, min_bars_within=TAP_MIN_BARS,
    )
    row = {k: v for k, v in base.items() if k != "anchor_time_dt"}
    row |= {
        "direction": direction,
        "degree": cluster.degree,
        "level_kinds": len(set(cluster.kinds)),
        "kinds": "|".join(cluster.kinds),
        "sources": "|".join(cluster.sources),
        "band_low": str(low),
        "band_high": str(high),
        "width_atr": str((high - low) / atr),
        "tapped": tap.valid,
    }
    if not tap.valid or tap.first_index is None:
        return row

    # The tap completes on the last of `TAP_MIN_BARS` bars inside the band; its
    # close is where price actually was when the clock starts, and both brackets
    # are measured from there. Referencing the band instead — either edge or
    # midpoint — makes a wide barrier win for free, and width rises with the
    # number of stacked levels, which is the axis under test.
    start = tap.first_index + TAP_MIN_BARS
    reference = forward[start - 1].close
    window = forward[start : start + FORWARD_BARS]
    row["forward_bars"] = len(window)
    row["reference_price"] = str(reference)
    row["reference_offset_atr"] = str((reference - (low + high) / 2) / atr)
    results = all_races(
        window, reference=reference, direction=direction, atr=atr,
        distances=DISTANCES_ATR,
    )
    for distance, result in results.items():
        row[f"race_{distance}"] = result.outcome
        row[f"race_{distance}_bars"] = result.bars
    return row


def run_session(
    session: str, store: BucketStore, parquet, instrument_by_day
) -> list[dict] | None:
    """Every anchor in one session, at every tier, against causal levels."""
    from run_stage06_reversal import minute_bars

    # None, not an empty list: a session without 20 sessions of history behind
    # it is *not yet* answerable, and writing an empty result would mark it done
    # forever. Once earlier buckets are built it becomes answerable, and a
    # resumed run must pick it up rather than skip it.
    window = store.trailing(session, ROLLING_SESSIONS + 1)
    if len(window) < ROLLING_SESSIONS + 1:
        return None

    day = (date.fromisoformat(session) - EPOCH).days
    bars = minute_bars(parquet, {day - 1, day}, instrument_by_day)
    if len(bars) < 400:
        return []
    # ATR is 5-minute Wilder. Resampling buckets on bar start, never close: a
    # bar closing at 10:05 belongs to the 10:00-10:05 bucket, and bucketing it
    # on its close put it in the next one for every earlier generation.
    five = tuple(resample(bars, ATR_MINUTES))
    if len(five) < ATR_PERIOD + 2:
        return []
    atrs = AtrSelector(wilder_atr(five, period=ATR_PERIOD))
    times = [b.close_time for b in bars]

    rows: list[dict] = []
    for anchor in reanchor_times(bars, minutes=60):
        try:
            atr = atrs.before(anchor).value
        except (ValueError, IndexError):
            continue
        if atr <= 0:
            continue
        index = bisect_right(times, anchor)
        forward = bars[index : index + LIVE_BARS]
        if len(forward) < LIVE_BARS:
            continue
        price = bars[index - 1].close

        for name in TIERS:
            spec = tier(name)
            level_set = build_level_set(store, session, anchor, atr=atr, spec=spec)
            # Nine sources is nine chances to leak the future, and a leak would
            # not crash — it would produce an excellent result.
            level_set.assert_causal()
            if not level_set.levels:
                continue
            clusters = cluster_levels(
                level_set.levels,
                tolerance=TOLERANCE_ATR * atr,
                max_width=MAX_CLUSTER_WIDTH_ATR * atr,
            )
            for direction, cluster in nearest_barriers(clusters, price).items():
                if cluster is None:
                    continue
                rows.append(
                    measure(
                        forward, cluster, atr=atr, direction=direction,
                        base={
                            "session": session,
                            "year": int(session[:4]),
                            "anchor_time": anchor.isoformat(),
                            "anchor_time_dt": anchor,
                            "tier": name,
                            "levels_available": len(level_set.levels),
                            "atr": str(atr),
                            "tolerance_atr": str(TOLERANCE_ATR),
                            "distance_atr": str(
                                (cluster.low - price) / atr
                                if direction == ABOVE
                                else (price - cluster.high) / atr
                            ),
                        },
                    )
                )
    return rows


def open_source():
    import pyarrow.parquet as pq

    from build_histograms import front_month_by_day, front_month_by_session
    from scan_contracts import resolved_url

    parquet = pq.ParquetFile(HTTPRangeReader(resolved_url(FILE_ID)))
    return parquet, front_month_by_session(front_month_by_day())


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="run_stage07.py")
    parser.add_argument("--limit", type=int, default=0, help="sessions this run")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--buckets", type=Path, default=BUCKETS)
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    store = BucketStore(args.buckets)
    parquet, instrument_by_day = open_source()

    def pending():
        return [
            s for s in store.sessions
            if int(s[:4]) in IS_YEARS and not (args.out / f"{s}.json").exists()
        ]

    todo = pending()
    if args.limit:
        todo = todo[: args.limit]

    done = 0
    for session in todo:
        rows = run_session(session, store, parquet, instrument_by_day)
        if rows is None:
            print(f"{session}: skipped, needs {ROLLING_SESSIONS} sessions of history",
                  flush=True)
            continue
        (args.out / f"{session}.json").write_text(json.dumps(rows, separators=(",", ":")))
        done += 1
        tapped = sum(1 for r in rows if r.get("tapped"))
        print(f"{session}: {len(rows)} barriers, {tapped} tapped", flush=True)

    print(json.dumps({"sessions_written": done, "remaining": len(pending())}))


if __name__ == "__main__":
    main()
