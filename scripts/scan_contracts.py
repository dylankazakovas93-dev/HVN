"""Per-session instrument volume, scanned row group by row group, resumably.

The mapping check needs one small fact per session — how much each instrument
traded and where it closed — not the 142M rows behind it. This walks the Parquet
file a slice of row groups at a time, aggregates inside Arrow rather than
Python, and appends compact JSON so a run killed halfway loses only its current
slice.

Reads are HTTP byte ranges against the Drive object, so nothing is downloaded
beyond the row groups requested.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq
import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "outputs" / "stage_06_contract_validation" / "sessions"
FILE_ID = "1aop7eaNO56pM9kZKyxelMcD6Uf8fG-Yf"
NANOS_PER_DAY = 86_400_000_000_000
PRICE_SCALE = 1_000_000_000


def resolved_url(file_id: str) -> str:
    """Drive serves large files behind a scan interstitial; carry its token."""
    session = requests.Session()
    response = session.get(
        f"https://drive.usercontent.google.com/download?id={file_id}&export=download",
        timeout=60,
        allow_redirects=True,
    )
    if response.headers.get("Content-Type", "").startswith("application/octet-stream"):
        return response.url
    fields = dict(re.findall(r'name="([^"]+)"\s+value="([^"]*)"', response.text))
    from urllib.parse import urlencode

    return "https://drive.usercontent.google.com/download?" + urlencode(fields)


def open_parquet(url: str) -> pq.ParquetFile:
    import sys

    sys.path.insert(0, "/workspace/dylankazakovas93-dev/nq1sdata/src")
    from nq_data.remote import HTTPRangeReader

    return pq.ParquetFile(HTTPRangeReader(url))


def scan_group(parquet: pq.ParquetFile, index: int) -> list[dict]:
    """Aggregate one row group to (utc_date, instrument) totals.

    Grouping happens in Arrow. A Python loop over half a million rows per group,
    286 times, is the difference between minutes and hours.
    """
    table = parquet.read_row_group(
        index, columns=["ts_event", "instrument_id", "close", "volume"]
    )
    # Calendar UTC date. The exchange session roll is applied later, from the
    # canonical session rules; this stage only needs a stable bucket.
    day = pc.divide(table.column("ts_event"), NANOS_PER_DAY)
    table = table.append_column("day", day)
    # `last` is an ordered aggregator, which Arrow will not run multi-threaded.
    grouped = table.group_by(["day", "instrument_id"], use_threads=False).aggregate(
        [("volume", "sum"), ("close", "last"), ("ts_event", "count")]
    )
    out = []
    for day, instrument, volume, close, count in zip(
        grouped.column("day").to_pylist(),
        grouped.column("instrument_id").to_pylist(),
        grouped.column("volume_sum").to_pylist(),
        grouped.column("close_last").to_pylist(),
        grouped.column("ts_event_count").to_pylist(),
        strict=True,
    ):
        out.append(
            {
                "day": int(day),
                "instrument_id": int(instrument),
                "volume": int(volume or 0),
                "close": (close / PRICE_SCALE) if close is not None else None,
                "bars": int(count),
            }
        )
    return out


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="scan_contracts.py")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True, help="exclusive")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    parquet = open_parquet(resolved_url(FILE_ID))
    total = parquet.metadata.num_row_groups
    end = min(args.end, total)

    written = 0
    for index in range(args.start, end):
        target = args.out / f"rg_{index:04d}.json"
        if target.exists():
            continue
        rows = scan_group(parquet, index)
        target.write_text(json.dumps(rows, separators=(",", ":")))
        written += 1
        print(f"row group {index}: {len(rows)} session-instrument rows", flush=True)

    print(json.dumps({"scanned": written, "range": [args.start, end], "row_groups": total}))


if __name__ == "__main__":
    main()
