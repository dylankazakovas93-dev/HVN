"""Collapse one-second bars into half-hour buckets, resumably.

Stage 6's cache held one histogram per session, which could serve the trailing
composite and nothing finer. Every other profile fell back to one-minute bars,
so eight of nine level sources never touched the one-second file. Bucketing at
thirty minutes serves all nine: each window this project uses is an exact sum of
buckets, including the cash session, which opens on a half hour.

Each bucket carries four things:

    volume     tick -> volume, uniformly allocated across a bar's range
    seconds    tick -> one-second bars touching it; time at price, measured
    n          bars, for coverage checks
    moments    volume, price*volume, price^2*volume, for anchored VWAP

The moments are why VWAP is finally computed from one-second data too. A VWAP
and its dispersion over any window are sums of those three numbers, so a
nine-hour band costs eighteen additions instead of a pass over thirty thousand
bars.

Work is written per row group and skipped if present, so a run killed at any
point resumes without repeating itself.
"""

from __future__ import annotations

import argparse
import json

from datetime import timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from hvn.bucket_histogram import EPOCH, NANOS_PER_BUCKET
from hvn.session_histogram import TICK_SIZE

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "outputs" / "stage_06_contract_validation"
DEFAULT_OUT = ROOT / "outputs" / "stage_07_buckets"
NANOS_PER_DAY = 86_400_000_000_000
PRICE_SCALE = 1_000_000_000

# In-sample development set, unchanged from Stage 6 so the two are comparable.
IS_YEARS = (2010, 2011, 2012, 2019, 2021, 2023, 2025)


def bucket_column(ts_event) -> pa.Array:
    return pc.divide(ts_event, NANOS_PER_BUCKET)


def bucket_rows(table, instrument_by_day: dict[int, int]) -> dict[int, dict]:
    """Per-bucket tick histograms and price moments, front month only."""
    from build_histograms import session_day

    table = table.append_column("day", session_day(table.column("ts_event")))
    days = table.column("day").to_numpy()
    wanted = np.array([instrument_by_day.get(int(d), -1) for d in days])
    table = table.filter(table.column("instrument_id").to_numpy() == wanted)
    if table.num_rows == 0:
        return {}

    table = table.append_column("bucket", bucket_column(table.column("ts_event")))
    tick_scale = int(TICK_SIZE * PRICE_SCALE)
    table = table.append_column(
        "low_tick", pc.divide(table.column("low"), tick_scale)
    ).append_column("high_tick", pc.divide(table.column("high"), tick_scale))

    out: dict[int, dict] = {}

    def entry(bucket: int) -> dict:
        return out.setdefault(
            int(bucket), {"v": {}, "s": {}, "n": 0, "vol": 0.0, "pv": 0.0, "p2v": 0.0}
        )

    # Moments first: one grouped pass, no Python loop over rows.
    typical = pc.divide(
        pc.cast(
            pc.add(
                pc.add(table.column("high"), table.column("low")), table.column("close")
            ),
            pa.float64(),
        ),
        3.0 * PRICE_SCALE,
    )
    volume = pc.cast(table.column("volume"), pa.float64())
    moments = pa.table(
        {
            "bucket": table.column("bucket"),
            "vol": volume,
            "pv": pc.multiply(typical, volume),
            "p2v": pc.multiply(pc.multiply(typical, typical), volume),
        }
    ).group_by(["bucket"], use_threads=False).aggregate(
        [("vol", "sum"), ("pv", "sum"), ("p2v", "sum")]
    )
    for bucket, vol, pv, p2v in zip(
        moments.column("bucket").to_pylist(),
        moments.column("vol_sum").to_pylist(),
        moments.column("pv_sum").to_pylist(),
        moments.column("p2v_sum").to_pylist(),
        strict=True,
    ):
        target = entry(bucket)
        target["vol"] += float(vol or 0.0)
        target["pv"] += float(pv or 0.0)
        target["p2v"] += float(p2v or 0.0)

    # Single-tick bars: the common case at one second, and the only case that
    # carries no allocation assumption at all.
    single = table.filter(pc.equal(table.column("low_tick"), table.column("high_tick")))
    if single.num_rows:
        grouped = single.group_by(["bucket", "low_tick"], use_threads=False).aggregate(
            [("volume", "sum"), ("ts_event", "count")]
        )
        for bucket, tick, vol, count in zip(
            grouped.column("bucket").to_pylist(),
            grouped.column("low_tick").to_pylist(),
            grouped.column("volume_sum").to_pylist(),
            grouped.column("ts_event_count").to_pylist(),
            strict=True,
        ):
            target = entry(bucket)
            key = str(int(tick))
            target["v"][key] = target["v"].get(key, 0.0) + float(vol or 0)
            target["s"][key] = target["s"].get(key, 0) + int(count)
            target["n"] += int(count)

    wide = table.filter(pc.not_equal(table.column("low_tick"), table.column("high_tick")))
    for bucket, lo, hi, vol in zip(
        wide.column("bucket").to_pylist(),
        wide.column("low_tick").to_pylist(),
        wide.column("high_tick").to_pylist(),
        wide.column("volume").to_pylist(),
        strict=True,
    ):
        first, last = int(lo), int(hi)
        if last < first:
            first, last = last, first
        share = float(vol or 0) / (last - first + 1)
        target = entry(bucket)
        for index in range(first, last + 1):
            key = str(index)
            target["v"][key] = target["v"].get(key, 0.0) + share
            target["s"][key] = target["s"].get(key, 0) + 1
        target["n"] += 1
    return out


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="build_buckets.py")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=10**9, help="exclusive")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    from build_histograms import front_month_by_day, front_month_by_session, session_day
    from scan_contracts import FILE_ID, open_parquet, resolved_url

    args.out.mkdir(parents=True, exist_ok=True)
    chosen = front_month_by_session(front_month_by_day())
    is_days = {
        day for day in chosen if (EPOCH + timedelta(days=day)).year in IS_YEARS
    }
    parquet = open_parquet(resolved_url(FILE_ID))
    end = min(args.end, parquet.metadata.num_row_groups)
    ts_column = parquet.schema_arrow.names.index("ts_event")

    written = 0
    for index in range(args.start, end):
        target = args.out / f"rg_{index:04d}.json"
        if target.exists():
            continue
        # Skip out-of-scope groups from statistics alone, without fetching a
        # byte. Most of the file is neither in sample nor needed here.
        stats = parquet.metadata.row_group(index).column(ts_column).statistics
        if stats is not None and stats.has_min_max:
            span = range(
                int(stats.min) // NANOS_PER_DAY, int(stats.max) // NANOS_PER_DAY + 1
            )
            if not (set(span) & is_days):
                target.write_text("{}")
                continue

        table = parquet.read_row_group(
            index,
            columns=["ts_event", "instrument_id", "low", "high", "close", "volume"],
        )
        days = set(session_day(table.column("ts_event")).to_pylist())
        if not (days & is_days):
            target.write_text("{}")
            continue
        rows = bucket_rows(table, {d: chosen[d] for d in days & is_days})
        target.write_text(json.dumps(rows, separators=(",", ":")))
        written += 1
        print(f"row group {index}: {len(rows)} buckets", flush=True)

    print(json.dumps({"written": written, "range": [args.start, end]}))


if __name__ == "__main__":
    main()
