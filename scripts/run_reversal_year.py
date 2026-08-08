"""Reversal or break-through, at fixed clock horizons, with excursion both ways.

The question this answers: price engages a level; ten, thirty and a hundred and
twenty minutes later, has it turned back the way it came or carried through?

For a barrier sitting **above** price, price arrived from below. So:

    reversal      the favourable direction is DOWN, back the way it came
    break-through the adverse direction is UP, onward through the level

and the mirror for a barrier below price.

Two measurements per horizon, because they answer different things:

    state       where the close sits at exactly that horizon — reversed,
                broken through, or still inside the band
    excursion   the furthest the move got in each direction at any point up to
                that horizon, favourable and adverse recorded separately

**Reference point.** Distances are measured from the band **midpoint**, not its
edges. Measuring from edges makes a wide band look reversal-prone for a purely
geometric reason: arriving from below, price sits near the low edge, so leaving
downward is a short trip while breaking upward must cross the whole band. The
midpoint is symmetric and does not reward width. The edge-based state is
recorded alongside so both readings are available.

The forward window is long enough that the 120-minute horizon is real data
rather than a truncated one: the tap must begin inside the first hour, and a
full 120 bars must remain after it ends.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from bisect import bisect_right
from decimal import Decimal
from pathlib import Path

from hvn.atr import wilder_atr
from hvn.confluence import (
    ABOVE,
    BELOW,
    MAX_CLUSTER_WIDTH_ATR,
    TOLERANCES_ATR,
    cluster_levels,
    nearest_barriers,
)
from hvn.io import databento_rows_with_audit
from hvn.profile_sources import resample
from hvn.rolling_profile import Node, build_rolling_profile, find_tap, reanchor_times, session_date
from hvn.stage02_ledger import write_deterministic_gzip_csv
from hvn.stage02_pipeline import AtrSelector
from hvn.stage4_levels import build_level_set

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "stage_05_reversal_study"
SOURCES = {
    2019: ("nq2018.zip", "glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst"),
    2021: ("nq2021.zip", "glbx-mdp3-20210101-20221230.ohlcv-1m.csv.zst"),
    2023: ("nq2023.zip", "glbx-mdp3-20230101-20241230.ohlcv-1m.csv.zst"),
    2025: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
}
FORBIDDEN_YEARS = (2018, 2020, 2022, 2024)

HORIZONS_MINUTES = (10, 30, 120)
TAP_SEARCH_BARS = 60
TAP_BAND_ATR = Decimal("0.5")
TAP_MIN_BARS = 3
# Enough bars that the longest horizon is measured, never truncated.
LIVE_BARS = TAP_SEARCH_BARS + TAP_MIN_BARS + max(HORIZONS_MINUTES)

REVERSED = "REVERSED"
BROKE_THROUGH = "BROKE_THROUGH"
INSIDE = "INSIDE"

TREATED = "TREATED"


def archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="run_reversal_year.py")
    parser.add_argument("--year", type=int, choices=sorted(SOURCES), required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-anchors", type=int, default=0)
    # Chunking. The environment kills long-running jobs, so a year is run as a
    # sequence of anchor slices that are merged afterwards. Slices are disjoint
    # and deterministic, so the union is identical to an uninterrupted run.
    parser.add_argument("--anchor-offset", type=int, default=0)
    parser.add_argument("--anchor-limit", type=int, default=0)
    parser.add_argument("--part", type=str, default="")
    return parser.parse_args(argv)


def measure(forward, cluster, *, atr, direction, base):
    """Tap the cluster, then favourable and adverse excursion at each horizon."""
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
        "band_low": low,
        "band_high": high,
        "width_atr": (high - low) / atr,
        "tapped": tap.valid,
    }
    if not tap.valid or tap.first_index is None:
        return row

    after = forward[tap.first_index + TAP_MIN_BARS :]
    midpoint = (low + high) / 2
    # Favourable is the way price came from; adverse is onward through.
    sign = Decimal(-1) if direction == ABOVE else Decimal(1)
    row["tap_index"] = tap.first_index

    for horizon in HORIZONS_MINUTES:
        window = after[:horizon]
        if len(window) < horizon:
            row[f"evaluated_{horizon}m"] = False
            continue
        row[f"evaluated_{horizon}m"] = True
        favourable = max(
            (sign * (bar.low if sign < 0 else bar.high) - sign * midpoint) / atr
            for bar in window
        )
        adverse = max(
            (sign * midpoint - sign * (bar.high if sign < 0 else bar.low)) / atr
            for bar in window
        )
        close = window[-1].close
        if (direction == ABOVE and close < low) or (direction == BELOW and close > high):
            state = REVERSED
        elif (direction == ABOVE and close >= high) or (
            direction == BELOW and close <= low
        ):
            state = BROKE_THROUGH
        else:
            state = INSIDE
        row[f"favourable_{horizon}m"] = favourable
        row[f"adverse_{horizon}m"] = adverse
        row[f"state_{horizon}m"] = state
    return row


def build(bars, *, year, code_sha, max_anchors=0, offset=0, limit=0):
    by_symbol: dict[str, list] = {}
    for bar in bars:
        by_symbol.setdefault(bar.symbol, []).append(bar)
    for symbol in by_symbol:
        by_symbol[symbol].sort(key=lambda b: b.close_time)

    rows: list[dict] = []
    anchors_used = 0
    seen = 0
    checks = 0
    for symbol, series in sorted(by_symbol.items()):
        if len(series) < 500:
            continue
        atrs = {
            minutes: AtrSelector(wilder_atr(tuple(resample(series, minutes))))
            for minutes in (1, 5)
        }
        times = [b.close_time for b in series]
        for anchor in reanchor_times(series):
            if max_anchors and anchors_used >= max_anchors:
                break
            if limit and anchors_used >= limit:
                break
            seen += 1
            if seen <= offset:
                continue
            try:
                atr_one = atrs[1].before(anchor).value
            except (ValueError, IndexError):
                continue
            if atr_one <= 0:
                continue
            profile = build_rolling_profile(series, anchor, atr=atr_one)
            if profile is None or profile.bars_used < 500:
                continue
            level_set = build_level_set(
                series, anchor, atr=atr_one, rolling_profile=profile
            )
            level_set.assert_causal()
            checks += 1
            if not level_set.levels:
                continue
            start = bisect_right(times, anchor)
            forward = series[start : start + LIVE_BARS]
            if len(forward) < LIVE_BARS:
                continue
            price = series[start - 1].close
            anchors_used += 1

            for minutes in (1, 5):
                try:
                    atr = atrs[minutes].before(anchor).value
                except (ValueError, IndexError):
                    continue
                if atr <= 0:
                    continue
                for tolerance in TOLERANCES_ATR:
                    clusters = cluster_levels(
                        level_set.levels,
                        tolerance=tolerance * atr,
                        max_width=MAX_CLUSTER_WIDTH_ATR * atr,
                    )
                    for direction, cluster in nearest_barriers(clusters, price).items():
                        if cluster is None:
                            continue
                        rows.append(
                            measure(
                                forward, cluster, atr=atr, direction=direction,
                                base={
                                    "year": year,
                                    "contract": symbol,
                                    "anchor_time": anchor.isoformat(),
                                    "anchor_time_dt": anchor,
                                    "session": session_date(anchor),
                                    "atr_timeframe": minutes,
                                    "atr": atr,
                                    "tolerance_atr": tolerance,
                                    "arm": TREATED,
                                    "distance_atr": (
                                        (cluster.low - price) / atr
                                        if direction == ABOVE
                                        else (price - cluster.high) / atr
                                    ),
                                    "code_sha": code_sha,
                                },
                            )
                        )
    return rows, anchors_used, checks


def main(argv=None) -> None:
    args = parse_args(argv)
    if args.year in FORBIDDEN_YEARS:
        raise SystemExit(f"year {args.year} is out of scope")
    output = args.output_root.resolve() / f"year_{args.year}"
    output.mkdir(parents=True, exist_ok=True)

    container, member = SOURCES[args.year]
    archive = (args.data_root / container).resolve()
    dataset_hash = archive_sha256(archive)
    bars, audit = databento_rows_with_audit(
        archive, member, allowed_year=args.year, dataset_sha256=dataset_hash
    )
    for bar in bars:
        if bar.start_time.year in FORBIDDEN_YEARS or bar.close_time.year in FORBIDDEN_YEARS:
            raise AssertionError(f"forbidden partition row parsed: {bar.source_row_id}")
    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

    rows, anchors, checks = build(
        bars, year=args.year, code_sha=code_sha, max_anchors=args.max_anchors,
        offset=args.anchor_offset, limit=args.anchor_limit,
    )
    suffix = f"_{args.part}" if args.part else ""
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    write_deterministic_gzip_csv(
        output / f"reversal_ledger{suffix}.csv.gz", rows, fields
    )
    summary = {
        "year": args.year,
        "archive_sha256": dataset_hash,
        "anchors": anchors,
        "causality_assertions_passed": checks,
        "rows": len(rows),
        "tapped": sum(1 for r in rows if r.get("tapped")),
        "evaluated_120m": sum(1 for r in rows if r.get("evaluated_120m")),
        "code_sha": code_sha,
        "audit": audit if isinstance(audit, dict) else str(audit),
    }
    summary["anchor_offset"] = args.anchor_offset
    summary["anchor_limit"] = args.anchor_limit
    (output / f"summary{suffix}.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "audit"},
                     indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
