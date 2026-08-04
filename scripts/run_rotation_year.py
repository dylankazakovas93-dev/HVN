"""Rotation study: rolling hourly profiles, HVN and LVN taps, rotation, sustain.

One development year end to end.

```text
every hourly close   ->  profile the trailing 20 sessions
                     ->  detect high and low nodes
                     ->  pick a width-matched control per node
node live window     ->  the next LIVE_BARS completed bars
tap                  ->  TAP_MIN_BARS consecutive bars within TAP_BAND_ATR
rotation(D, B)       ->  reached D ATR from the edge within B bars of the tap
sustain(N)           ->  still that far, same side, N bars after the rotation bar
```

Causal throughout: a profile contains only bars closed at or before its anchor,
and the tap search starts strictly after it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from bisect import bisect_right
from collections import Counter
from decimal import Decimal
from pathlib import Path

from hvn.atr import wilder_atr
from hvn.gen4_outcomes import interaction_session
from hvn.io import databento_rows_with_audit
from hvn.rolling_profile import (
    HIGH_NODE,
    LOW_NODE,
    Node,
    build_rolling_profile,
    detect_nodes,
    find_tap,
    reanchor_times,
    rolling_activity,
)
from hvn.rotation import (
    ROTATION_DEADLINES_BARS,
    ROTATION_DISTANCES_ATR,
    SUSTAIN_HORIZONS_BARS,
    check_sustain,
    find_rotation,
    max_excursion,
    rotation_quality,
)
from hvn.stage02_ledger import deterministic_csv_bytes, write_deterministic_gzip_csv
from hvn.stage02_pipeline import AtrSelector

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "stage_03_rotation_study"
SOURCES = {
    2019: ("nq2018.zip", "glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst"),
    2021: ("nq2021.zip", "glbx-mdp3-20210101-20221230.ohlcv-1m.csv.zst"),
    2023: ("nq2023.zip", "glbx-mdp3-20230101-20241230.ohlcv-1m.csv.zst"),
    2025: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
    2026: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
}
FORBIDDEN_YEARS = (2018, 2020, 2022, 2024)

# Frozen interaction parameters.
LIVE_BARS = 120          # a node is interactable for two hours after its anchor
TAP_SEARCH_BARS = 60     # the tap itself must begin within the first hour
TAP_BAND_ATR = Decimal("0.5")
TAP_MIN_BARS = 3
MAX_EXCURSION_WINDOW = 60

TREATED = "TREATED"
CONTROL = "CONTROL_WIDTH_MATCHED"


def archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="run_rotation_year.py")
    parser.add_argument("--year", type=int, choices=sorted(SOURCES), required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-anchors", type=int, default=0, help="0 means all")
    return parser.parse_args(argv)


def pick_control(profile, activity, nodes, node) -> Node | None:
    """A same-width window in the same profile that is not any node.

    Nearest eligible window to the treated node, lower index breaking a tie, so
    selection is deterministic and the control sits in comparable price
    territory without ever consulting what happens next.
    """
    width = node.width_ticks
    blocked: set[int] = set()
    for other in nodes:
        blocked.update(range(other.low_index, other.high_index + 1))
    active = set(activity.active)
    centre = node.low_index + node.high_index

    best = None
    for low in range(profile.low_index, profile.high_index - width + 2):
        high = low + width - 1
        window = range(low, high + 1)
        if any(i in blocked for i in window):
            continue
        if not all(i in active for i in window):
            continue
        distance = abs(low + high - centre)
        if best is None or (distance, low) < (best[0], best[1]):
            best = (distance, low, high)
    if best is None:
        return None
    _, low, high = best
    return Node(
        node_class=node.node_class,
        low_index=low,
        high_index=high,
        node_low=profile.tick_low(low),
        node_high=profile.tick_high(high),
        peak_index=(low + high) // 2,
        peak_price=profile.tick_low((low + high) // 2),
        smoothed_activity=activity.smoothed_activity.get((low + high) // 2, Decimal(0)),
        activity_percentile=activity.percentile.get((low + high) // 2, Decimal(0)),
        anchor_time=node.anchor_time,
    )


def measure(forward, node, *, atr, base) -> dict | None:
    """Tap, rotation grid, sustain and the continuous excursion for one node."""
    tap = find_tap(
        forward[:TAP_SEARCH_BARS],
        node,
        atr=atr,
        max_distance_atr=TAP_BAND_ATR,
        min_bars_within=TAP_MIN_BARS,
    )
    row = base | {
        "node_class": node.node_class,
        "node_low": node.node_low,
        "node_high": node.node_high,
        "width_ticks": node.width_ticks,
        "width_atr": node.width_points / atr,
        "smoothed_activity": node.smoothed_activity,
        "activity_percentile": node.activity_percentile,
        "tapped": tap.valid,
        "tap_index": tap.first_index,
        "closest_approach_atr": tap.closest_distance_atr,
    }
    if not tap.valid or tap.first_index is None:
        return row

    after = forward[tap.first_index + TAP_MIN_BARS :]
    row["interaction_session"] = interaction_session(
        forward[tap.first_index].close_time
    )
    excursion = max_excursion(
        after,
        node_low=node.node_low,
        node_high=node.node_high,
        atr=atr,
        window_bars=MAX_EXCURSION_WINDOW,
    )
    row["max_excursion_atr"] = excursion.max_distance_atr
    row["bars_to_max_excursion"] = excursion.bars_to_max
    row["max_excursion_rate"] = excursion.rate_atr_per_bar
    row["max_excursion_direction"] = excursion.direction

    for distance in ROTATION_DISTANCES_ATR:
        for deadline in ROTATION_DEADLINES_BARS:
            key = f"{distance.normalize()}atr_{deadline}b"
            rotation = find_rotation(
                after,
                node_low=node.node_low,
                node_high=node.node_high,
                atr=atr,
                distance_atr=distance,
                deadline_bars=deadline,
            )
            row[f"rotated_{key}"] = rotation.rotated
            row[f"censored_{key}"] = rotation.censored
            row[f"bars_{key}"] = rotation.bars_taken
            row[f"rate_{key}"] = rotation.rate_atr_per_bar
            row[f"direction_{key}"] = rotation.direction
            for horizon in SUSTAIN_HORIZONS_BARS:
                sustain = check_sustain(
                    after,
                    rotation,
                    node_low=node.node_low,
                    node_high=node.node_high,
                    atr=atr,
                    horizon_bars=horizon,
                )
                row[f"sustain_evaluated_{key}_{horizon}b"] = sustain.evaluated
                row[f"sustained_{key}_{horizon}b"] = sustain.sustained
            # Conditional on the rotation happening: how long did it hold and
            # how much further did it go? "A high node rotates less often" is
            # the theory restating itself; this is the question that is not.
            quality = rotation_quality(
                after,
                rotation,
                node_low=node.node_low,
                node_high=node.node_high,
                atr=atr,
                window_bars=MAX_EXCURSION_WINDOW,
            )
            row[f"quality_evaluated_{key}"] = quality.evaluated
            row[f"bars_held_{key}"] = quality.bars_held
            row[f"further_extension_{key}"] = quality.further_extension_atr
            row[f"gave_back_{key}"] = quality.gave_back
    return row


def build(bars, *, year, code_sha, max_anchors=0):
    by_symbol: dict[str, list] = {}
    for bar in bars:
        by_symbol.setdefault(bar.symbol, []).append(bar)
    for symbol in by_symbol:
        by_symbol[symbol].sort(key=lambda b: b.close_time)

    rows: list[dict] = []
    anchors_used = 0
    profiles_built = 0

    for symbol, series in sorted(by_symbol.items()):
        if len(series) < 500:
            continue
        atrs = AtrSelector(wilder_atr(tuple(series)))
        times = [b.close_time for b in series]
        anchors = reanchor_times(series)
        for anchor in anchors:
            if max_anchors and anchors_used >= max_anchors:
                break
            try:
                atr = atrs.before(anchor).value
            except (ValueError, IndexError):
                continue
            if atr <= 0:
                continue
            profile = build_rolling_profile(series, anchor, atr=atr)
            if profile is None or profile.bars_used < 500:
                continue
            activity = rolling_activity(profile)
            if not activity.valid:
                continue
            nodes = detect_nodes(profile, activity)
            if not nodes:
                continue
            profiles_built += 1
            anchors_used += 1

            start = bisect_right(times, anchor)
            forward = series[start : start + LIVE_BARS]
            if len(forward) < LIVE_BARS:
                continue

            base = {
                "year": year,
                "contract": symbol,
                "anchor_time": anchor.isoformat(),
                "atr": atr,
                "sessions_in_profile": len(profile.sessions),
                "bars_in_profile": profile.bars_used,
                "code_sha": code_sha,
            }
            for index, node in enumerate(nodes):
                treated = measure(
                    forward,
                    node,
                    atr=atr,
                    base=base | {"arm": TREATED, "node_id": f"{anchor.isoformat()}-{index}"},
                )
                if treated:
                    rows.append(treated)
                control = pick_control(profile, activity, nodes, node)
                if control is None:
                    continue
                measured = measure(
                    forward,
                    control,
                    atr=atr,
                    base=base
                    | {"arm": CONTROL, "node_id": f"{anchor.isoformat()}-{index}-C"},
                )
                if measured:
                    rows.append(measured)
    return rows, profiles_built


def main(argv=None) -> None:
    args = parse_args(argv)
    output = args.output_root.resolve() / f"year_{args.year}"
    output.mkdir(parents=True, exist_ok=True)

    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    archive, member = SOURCES[args.year]
    source = (args.data_root / archive).resolve()
    dataset_hash = archive_sha256(source)
    bars, audit = databento_rows_with_audit(
        source, member, allowed_year=args.year, dataset_sha256=dataset_hash
    )
    for bar in bars:
        if bar.start_time.year in FORBIDDEN_YEARS or bar.close_time.year in FORBIDDEN_YEARS:
            raise AssertionError(f"forbidden partition row parsed: {bar.source_row_id}")

    rows, profiles = build(
        bars, year=args.year, code_sha=code_sha, max_anchors=args.max_anchors
    )
    fields = tuple(sorted({k for r in rows for k in r})) if rows else ("record_id",)
    write_deterministic_gzip_csv(
        output / "rotation_ledger.csv.gz", rows, fields,
        sort_by=("node_id",) if rows and "node_id" in fields else (),
    )

    tapped = [r for r in rows if str(r.get("tapped")).lower() == "true"]
    counts = Counter((r["arm"], r["node_class"]) for r in rows)
    tapped_counts = Counter((r["arm"], r["node_class"]) for r in tapped)
    summary = [
        {
            "arm": arm,
            "node_class": node_class,
            "nodes": counts[(arm, node_class)],
            "tapped": tapped_counts[(arm, node_class)],
            "tap_rate_pct": (
                Decimal(tapped_counts[(arm, node_class)]) * 100
                / Decimal(counts[(arm, node_class)])
            ).quantize(Decimal("0.01"))
            if counts[(arm, node_class)]
            else None,
        }
        for arm, node_class in sorted(counts)
    ]
    (output / "population_summary.csv").write_bytes(
        deterministic_csv_bytes(
            summary, ("arm", "node_class", "nodes", "tapped", "tap_rate_pct"),
            sort_by=("arm", "node_class"),
        )
    )

    manifest = {
        "study": "STAGE_03_ROTATION",
        "year": args.year,
        "dataset_sha256": dataset_hash,
        "code_sha": code_sha,
        "bars": len(bars),
        "profiles_built": profiles,
        "node_rows": len(rows),
        "tapped_rows": len(tapped),
        "forbidden_year_rows_admitted": 0,
        "parameters": {
            "rolling_sessions": 20,
            "reanchor_minutes": 60,
            "live_bars": LIVE_BARS,
            "tap_band_atr": str(TAP_BAND_ATR),
            "tap_min_bars": TAP_MIN_BARS,
            "rotation_distances_atr": [str(d) for d in ROTATION_DISTANCES_ATR],
            "rotation_deadlines_bars": list(ROTATION_DEADLINES_BARS),
            "sustain_horizons_bars": list(SUSTAIN_HORIZONS_BARS),
        },
        "ingestion_audit": {
            "parsed_years": sorted(audit.parsed_years),
            "rows_admitted": audit.rows_admitted,
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
