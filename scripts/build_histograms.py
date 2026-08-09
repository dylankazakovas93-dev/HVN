"""Collapse one-second bars into one histogram per session, resumably.

This is the step that makes 142M rows usable. Each session becomes a compact
`tick -> (volume, seconds)` map for the front-month instrument only; every
profile after this is a sum of those maps and never touches a raw bar again.

Only the front month is kept. The selection comes from the validated scan, so a
session's histogram is single-contract by construction and `combine` can refuse
to mix instruments without ever having to.

Work is done a row group at a time and written per row group, so a run killed by
the environment loses only its current slice. Sessions spanning a row group
boundary are merged at load time rather than during the scan, which keeps every
slice independent.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc

from hvn.session_histogram import TICK_SIZE

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "outputs" / "stage_06_contract_validation"
DEFAULT_OUT = ROOT / "outputs" / "stage_06_histograms"
NANOS_PER_DAY = 86_400_000_000_000
# The exchange session rolls at 17:00 Chicago, so shifting local time forward by
# seven hours puts a session boundary on midnight and the calendar date of the
# shifted timestamp *is* the session date. Keying on UTC calendar day instead —
# as the first build did — splits every overnight session across two buckets and
# would feed a 20-session composite the wrong twenty windows.
SESSION_ROLL_HOURS = 7
EXCHANGE_TZ = "America/Chicago"
PRICE_SCALE = 1_000_000_000
EPOCH = date(1970, 1, 1)

# Development set from STAGE_06_ONE_SECOND_SPEC.md. The burned years are here by
# force; 2010-2012 top the set up to ~40%.
IS_YEARS = (2010, 2011, 2012, 2019, 2021, 2023, 2025)


def front_month_by_day() -> dict[int, int]:
    """day-number -> chosen instrument_id, from the validated scan."""
    from hvn.contract_selection import choose_front_month

    per_day: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(lambda: [0, None]))
    for path in sorted((VALIDATION / "sessions").glob("rg_*.json")):
        for row in json.loads(path.read_text()):
            entry = per_day[row["day"]][row["instrument_id"]]
            entry[0] += row["volume"]
            if row["close"] is not None:
                entry[1] = row["close"]
    chosen: dict[int, int] = {}
    for day, instruments in per_day.items():
        rows = [(i, v, c) for i, (v, c) in instruments.items()]
        choice = choose_front_month(str(day), rows)
        if choice is not None:
            chosen[day] = choice.instrument_id
    return chosen


def front_month_by_session(chosen: dict[int, int]) -> dict[int, int]:
    """Translate UTC-day choices onto session days.

    A session spans two UTC dates, so its front month is the choice they agree
    on. When they disagree the session straddles a roll, and it is **dropped**
    rather than assigned a guess: those are precisely the sessions where two
    contracts both trade heavily, so a wrong pick would contaminate a profile
    with the other contract's price levels. Four sessions a year at most.
    """
    out: dict[int, int] = {}
    for day, instrument in chosen.items():
        previous = chosen.get(day - 1)
        if previous is None or previous == instrument:
            out[day] = instrument
    return out


def session_day(ts_event) -> pa.Array:
    """Session-date day number for UTC nanosecond timestamps."""
    utc = pc.cast(ts_event, pa.timestamp("ns", tz="UTC"))
    local = pc.local_timestamp(pc.cast(utc, pa.timestamp("ns", tz=EXCHANGE_TZ)))
    shifted = pc.add(
        pc.cast(local, pa.int64()), SESSION_ROLL_HOURS * 3_600_000_000_000
    )
    return pc.divide(shifted, NANOS_PER_DAY)


def histogram_rows(table, instrument_by_day: dict[int, int]) -> dict[int, dict]:
    """Per-session tick histograms for the front month, computed inside Arrow."""
    table = table.append_column("day", session_day(table.column("ts_event")))

    # Keep only the front-month rows. Building the mask in Arrow avoids a Python
    # pass over half a million rows per group.
    days = table.column("day").to_numpy()
    instruments = table.column("instrument_id").to_numpy()
    import numpy as np

    wanted = np.array([instrument_by_day.get(int(d), -1) for d in days])
    mask = instruments == wanted
    table = table.filter(mask)
    if table.num_rows == 0:
        return {}

    tick_scale = int(TICK_SIZE * PRICE_SCALE)
    low_tick = pc.divide(table.column("low"), tick_scale)
    high_tick = pc.divide(table.column("high"), tick_scale)
    table = table.append_column("low_tick", low_tick).append_column("high_tick", high_tick)

    out: dict[int, dict] = {}
    single = table.filter(pc.equal(table.column("low_tick"), table.column("high_tick")))
    if single.num_rows:
        grouped = single.group_by(["day", "low_tick"], use_threads=False).aggregate(
            [("volume", "sum"), ("ts_event", "count")]
        )
        for d, tick, volume, count in zip(
            grouped.column("day").to_pylist(),
            grouped.column("low_tick").to_pylist(),
            grouped.column("volume_sum").to_pylist(),
            grouped.column("ts_event_count").to_pylist(),
            strict=True,
        ):
            entry = out.setdefault(int(d), {"volume": {}, "seconds": {}, "bars": 0})
            key = str(int(tick))
            entry["volume"][key] = entry["volume"].get(key, 0.0) + float(volume or 0)
            entry["seconds"][key] = entry["seconds"].get(key, 0) + int(count)
            entry["bars"] += int(count)

    # Multi-tick bars are the minority at one-second resolution; allocate them
    # uniformly, exactly as every earlier stage did.
    wide = table.filter(pc.not_equal(table.column("low_tick"), table.column("high_tick")))
    for d, lo, hi, volume in zip(
        wide.column("day").to_pylist(),
        wide.column("low_tick").to_pylist(),
        wide.column("high_tick").to_pylist(),
        wide.column("volume").to_pylist(),
        strict=True,
    ):
        first, last = int(lo), int(hi)
        if last < first:
            first, last = last, first
        share = float(volume or 0) / (last - first + 1)
        entry = out.setdefault(int(d), {"volume": {}, "seconds": {}, "bars": 0})
        for index in range(first, last + 1):
            key = str(index)
            entry["volume"][key] = entry["volume"].get(key, 0.0) + share
            entry["seconds"][key] = entry["seconds"].get(key, 0) + 1
        entry["bars"] += 1
    return out


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="build_histograms.py")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True, help="exclusive")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    from scan_contracts import open_parquet, resolved_url, FILE_ID

    args.out.mkdir(parents=True, exist_ok=True)
    chosen = front_month_by_session(front_month_by_day())
    is_days = {
        day for day in chosen
        if (EPOCH + timedelta(days=day)).year in IS_YEARS
    }
    parquet = open_parquet(resolved_url(FILE_ID))
    end = min(args.end, parquet.metadata.num_row_groups)
    ts_column = parquet.schema_arrow.names.index("ts_event")

    written = 0
    for index in range(args.start, end):
        target = args.out / f"rg_{index:04d}.json"
        if target.exists():
            continue
        # Skip out-of-scope groups from row-group statistics alone, without
        # fetching a byte of their data. Roughly six years of the file are
        # neither IS nor needed here.
        stats = parquet.metadata.row_group(index).column(ts_column).statistics
        if stats is not None and stats.has_min_max:
            span = range(int(stats.min) // NANOS_PER_DAY, int(stats.max) // NANOS_PER_DAY + 1)
            if not (set(span) & is_days):
                target.write_text("{}")
                continue

        table = parquet.read_row_group(
            index, columns=["ts_event", "instrument_id", "low", "high", "volume"]
        )
        days = set(session_day(table.column("ts_event")).to_pylist())
        if not (days & is_days):
            target.write_text("{}")
            continue
        rows = histogram_rows(table, {d: chosen[d] for d in days & is_days})
        target.write_text(json.dumps(rows, separators=(",", ":")))
        written += 1
        print(f"row group {index}: {len(rows)} sessions", flush=True)

    print(json.dumps({"written": written, "range": [args.start, end]}))


if __name__ == "__main__":
    main()
