"""Stage 4 scan: nine sources, three tolerances, two ATR timeframes, one year.

```text
every hourly close  ->  build levels from all nine sources
                    ->  assert nothing later than the anchor contributed
per tolerance       ->  cluster levels into confluence degrees
per ATR timeframe   ->  nearest barrier above and below the prevailing price
                    ->  a distance-matched control barrier nobody drew
                    ->  tap, rotation at 5/20/60 minutes, continuous excursion
```

The control isolates "is this level special" from "is this distance special": it
is the same width at the same distance on the same side, moved outward only as
far as needed to sit clear of every level any source drew.
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
from hvn.confluence import ABOVE, BELOW, TOLERANCES_ATR, cluster_levels, nearest_barriers
from hvn.gen4_outcomes import interaction_session
from hvn.io import databento_rows_with_audit
from hvn.profile_sources import resample
from hvn.rolling_profile import build_rolling_profile, reanchor_times, session_date
from hvn.rotation import find_rotation, max_excursion
from hvn.stage02_ledger import write_deterministic_gzip_csv
from hvn.stage02_pipeline import AtrSelector
from hvn.stage4_levels import build_level_set

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "stage_04_confluence_study"
SOURCES = {
    2019: ("nq2018.zip", "glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst"),
    2021: ("nq2021.zip", "glbx-mdp3-20210101-20221230.ohlcv-1m.csv.zst"),
    2023: ("nq2023.zip", "glbx-mdp3-20230101-20241230.ohlcv-1m.csv.zst"),
    2025: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
}
FORBIDDEN_YEARS = (2018, 2020, 2022, 2024)

# Frozen interaction parameters, carried from Stage 3 unchanged.
LIVE_BARS = 120
TAP_SEARCH_BARS = 60
TAP_BAND_ATR = Decimal("0.5")
TAP_MIN_BARS = 3
MAX_EXCURSION_WINDOW = 60

# Rotation at the three horizons named in the spec, in 1-minute bars.
ROTATION_DISTANCE_ATR = Decimal("3")
ROTATION_DEADLINES = (5, 20, 60)

ATR_TIMEFRAMES = (1, 5)
CONTROL_SEARCH_TICKS = 400
TICK = Decimal("0.25")

TREATED = "TREATED"
CONTROL = "CONTROL_DISTANCE_MATCHED"


def archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="run_confluence_year.py")
    parser.add_argument("--year", type=int, choices=sorted(SOURCES), required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-anchors", type=int, default=0, help="0 means all")
    return parser.parse_args(argv)


def control_band(levels, price, low, high, direction):
    """Same width, same side, same distance — at a price no source marked.

    Stepping outward is deterministic and stops at the first clear placement, so
    the control is as close to the treated barrier's distance as a level-free
    location allows. The realised distance is recorded rather than assumed.
    """
    width = high - low
    occupied = [(level.low, level.high) for level in levels]

    def clear(candidate_low, candidate_high):
        return not any(
            candidate_low < b and a < candidate_high for a, b in occupied
        )

    for step in range(CONTROL_SEARCH_TICKS):
        offset = TICK * step
        if direction == ABOVE:
            candidate_low = low + offset
        else:
            candidate_low = low - offset
        candidate_high = candidate_low + width
        if direction == ABOVE and candidate_low <= price:
            continue
        if direction == BELOW and candidate_high > price:
            continue
        if clear(candidate_low, candidate_high):
            return candidate_low, candidate_high
    return None


def measure(forward, low, high, *, atr, base):
    """Tap the band, then rotation and excursion away from it."""
    from hvn.rolling_profile import Node

    node = Node(
        node_class="BARRIER", low_index=0, high_index=0,
        node_low=low, node_high=high, peak_index=0,
        peak_price=(low + high) / 2, smoothed_activity=Decimal(0),
        activity_percentile=Decimal(0), anchor_time=base["anchor_time_dt"],
    )
    from hvn.rolling_profile import find_tap

    tap = find_tap(
        forward[:TAP_SEARCH_BARS], node, atr=atr,
        max_distance_atr=TAP_BAND_ATR, min_bars_within=TAP_MIN_BARS,
    )
    row = {k: v for k, v in base.items() if k != "anchor_time_dt"}
    row |= {
        "band_low": low,
        "band_high": high,
        "width_atr": (high - low) / atr,
        "tapped": tap.valid,
        "closest_approach_atr": tap.closest_distance_atr,
    }
    if not tap.valid or tap.first_index is None:
        return row

    after = forward[tap.first_index + TAP_MIN_BARS :]
    row["interaction_session"] = interaction_session(
        forward[tap.first_index].close_time
    )
    excursion = max_excursion(
        after, node_low=low, node_high=high, atr=atr,
        window_bars=MAX_EXCURSION_WINDOW,
    )
    row["max_excursion_atr"] = excursion.max_distance_atr
    row["bars_to_max_excursion"] = excursion.bars_to_max
    row["max_excursion_direction"] = excursion.direction

    for deadline in ROTATION_DEADLINES:
        rotation = find_rotation(
            after, node_low=low, node_high=high, atr=atr,
            distance_atr=ROTATION_DISTANCE_ATR, deadline_bars=deadline,
        )
        row[f"rotated_{deadline}b"] = rotation.rotated
        row[f"censored_{deadline}b"] = rotation.censored
        row[f"bars_{deadline}b"] = rotation.bars_taken
        row[f"direction_{deadline}b"] = rotation.direction
    return row


def build(bars, *, year, code_sha, max_anchors=0):
    by_symbol: dict[str, list] = {}
    for bar in bars:
        by_symbol.setdefault(bar.symbol, []).append(bar)
    for symbol in by_symbol:
        by_symbol[symbol].sort(key=lambda b: b.close_time)

    rows: list[dict] = []
    anchors_used = 0
    causality_checks = 0

    for symbol, series in sorted(by_symbol.items()):
        if len(series) < 500:
            continue
        atr_by_timeframe = {
            minutes: AtrSelector(wilder_atr(tuple(resample(series, minutes))))
            for minutes in ATR_TIMEFRAMES
        }
        times = [b.close_time for b in series]
        anchors = reanchor_times(series)
        for anchor in anchors:
            if max_anchors and anchors_used >= max_anchors:
                break
            try:
                atr_one = atr_by_timeframe[1].before(anchor).value
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
            # Checked at every anchor, not once at startup. A leak does not
            # crash; it produces an excellent result.
            level_set.assert_causal()
            causality_checks += 1
            if not level_set.levels:
                continue

            start = bisect_right(times, anchor)
            forward = series[start : start + LIVE_BARS]
            if len(forward) < LIVE_BARS:
                continue
            price = series[start - 1].close
            anchors_used += 1

            for minutes in ATR_TIMEFRAMES:
                try:
                    atr = atr_by_timeframe[minutes].before(anchor).value
                except (ValueError, IndexError):
                    continue
                if atr <= 0:
                    continue
                for tolerance in TOLERANCES_ATR:
                    clusters = cluster_levels(
                        level_set.levels, tolerance=tolerance * atr
                    )
                    barriers = nearest_barriers(clusters, price)
                    for direction, cluster in barriers.items():
                        if cluster is None:
                            continue
                        base = {
                            "year": year,
                            "contract": symbol,
                            "anchor_time": anchor.isoformat(),
                            "anchor_time_dt": anchor,
                            "session": session_date(anchor),
                            "atr_timeframe": minutes,
                            "atr": atr,
                            "tolerance_atr": tolerance,
                            "direction": direction,
                            "degree": cluster.degree,
                            "sources": "|".join(cluster.sources),
                            "kinds": "|".join(cluster.kinds),
                            "distance_atr": (
                                (cluster.low - price) / atr
                                if direction == ABOVE
                                else (price - cluster.high) / atr
                            ),
                            "code_sha": code_sha,
                        }
                        treated = measure(
                            forward, cluster.low, cluster.high,
                            atr=atr, base=base | {"arm": TREATED},
                        )
                        rows.append(treated)

                        placement = control_band(
                            level_set.levels, price, cluster.low, cluster.high,
                            direction,
                        )
                        if placement is None:
                            continue
                        rows.append(
                            measure(
                                forward, placement[0], placement[1], atr=atr,
                                base=base
                                | {
                                    "arm": CONTROL,
                                    "degree": 0,
                                    "sources": "",
                                    "kinds": "",
                                    "distance_atr": (
                                        (placement[0] - price) / atr
                                        if direction == ABOVE
                                        else (price - placement[1]) / atr
                                    ),
                                },
                            )
                        )
    return rows, anchors_used, causality_checks


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
    # The partition is defined by parsed timestamps, never by a filename.
    for bar in bars:
        if bar.start_time.year in FORBIDDEN_YEARS or bar.close_time.year in FORBIDDEN_YEARS:
            raise AssertionError(f"forbidden partition row parsed: {bar.source_row_id}")
    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

    rows, anchors, checks = build(
        bars, year=args.year, code_sha=code_sha, max_anchors=args.max_anchors
    )
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    write_deterministic_gzip_csv(output / "confluence_ledger.csv.gz", rows, fields)

    summary = {
        "year": args.year,
        "archive_sha256": dataset_hash,
        "bars": len(bars),
        "anchors": anchors,
        "causality_assertions_passed": checks,
        "rows": len(rows),
        "tapped": sum(1 for r in rows if r.get("tapped")),
        "code_sha": code_sha,
        "audit": audit if isinstance(audit, dict) else str(audit),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "audit"}, indent=2,
                     sort_keys=True, default=str))


if __name__ == "__main__":
    main()
