from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import zstandard

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "stage_01b" / "nq_archive_audit.json"
ARCHIVES = [
    {
        "path": Path("/Users/mariusvidziunas/Downloads/quant-data-upload/NQ/nq2021.zip"),
        "member": "glbx-mdp3-20210101-20221230.ohlcv-1m.csv.zst",
        "allowed_years": {2021},
    },
    {
        "path": Path("/Users/mariusvidziunas/Downloads/quant-data-upload/NQ/nq2023.zip"),
        "member": "glbx-mdp3-20230101-20241230.ohlcv-1m.csv.zst",
        "allowed_years": {2023},
    },
    {
        "path": Path("/Users/mariusvidziunas/Downloads/quant-data-upload/NQ/nq2025.zip"),
        "member": "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst",
        "allowed_years": {2025, 2026},
    },
]


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan(config: dict) -> dict:
    path: Path = config["path"]
    allowed_years: set[int] = config["allowed_years"]
    minimum_year, maximum_year = min(allowed_years), max(allowed_years)
    raw_rows = outright_rows = spread_rows = non_nq_rows = 0
    nonpositive_volume = invalid_ohlc = 0
    duplicate_symbol_timestamps = repeated_timestamp_rows = 0
    observed_gap_count = discontinuity_count = 0
    maximum_observed_gap_minutes = 0
    maximum_adjacent_price_change = Decimal(0)
    first_timestamp = last_timestamp = None
    current_timestamp = None
    symbols_at_timestamp: set[str] = set()
    contract_rows = defaultdict(int)
    contract_volume = defaultdict(int)
    spread_symbols: set[str] = set()
    previous_by_symbol: dict[str, tuple[datetime, Decimal]] = {}

    with zipfile.ZipFile(path) as archive:
        member_names = archive.namelist()
        metadata = json.loads(archive.read("metadata.json"))
        with archive.open(config["member"]) as compressed:
            with zstandard.ZstdDecompressor().stream_reader(compressed) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
                schema = text.readline().rstrip("\r\n").split(",")
                position = {name: index for index, name in enumerate(schema)}
                for line in text:
                    row_year = int(line[:4])
                    if row_year < minimum_year:
                        continue
                    if row_year > maximum_year:
                        break
                    if row_year not in allowed_years:
                        continue
                    values = line.rstrip("\r\n").split(",")
                    timestamp = datetime.fromisoformat(
                        values[position["ts_event"]].replace("Z", "+00:00")
                    )
                    symbol = values[position["symbol"]]
                    open_ = Decimal(values[position["open"]])
                    high = Decimal(values[position["high"]])
                    low = Decimal(values[position["low"]])
                    close = Decimal(values[position["close"]])
                    volume = int(values[position["volume"]])
                    raw_rows += 1
                    first_timestamp = first_timestamp or timestamp
                    last_timestamp = timestamp
                    if timestamp != current_timestamp:
                        current_timestamp = timestamp
                        symbols_at_timestamp = set()
                    else:
                        repeated_timestamp_rows += 1
                    if symbol in symbols_at_timestamp:
                        duplicate_symbol_timestamps += 1
                    symbols_at_timestamp.add(symbol)
                    if volume <= 0:
                        nonpositive_volume += 1
                    if low > high or not (low <= open_ <= high and low <= close <= high):
                        invalid_ohlc += 1
                    if not symbol.startswith("NQ"):
                        non_nq_rows += 1
                        continue
                    if "-" in symbol:
                        spread_rows += 1
                        spread_symbols.add(symbol)
                        continue
                    outright_rows += 1
                    contract_rows[symbol] += 1
                    contract_volume[symbol] += volume
                    previous = previous_by_symbol.get(symbol)
                    if previous is not None:
                        previous_time, previous_close = previous
                        elapsed = timestamp - previous_time
                        if elapsed > timedelta(minutes=1):
                            observed_gap_count += 1
                            maximum_observed_gap_minutes = max(
                                maximum_observed_gap_minutes,
                                int(elapsed.total_seconds() // 60),
                            )
                        change = abs(open_ - previous_close)
                        maximum_adjacent_price_change = max(
                            maximum_adjacent_price_change, change
                        )
                        if elapsed <= timedelta(minutes=2) and change >= Decimal(100):
                            discontinuity_count += 1
                    previous_by_symbol[symbol] = (timestamp, close)
        return {
            "archive_filename": path.name,
            "archive_path": str(path),
            "sha256": file_hash(path),
            "internal_member_names": member_names,
            "instrument_identifier": metadata["query"]["symbols"],
            "dataset": metadata["query"]["dataset"],
            "schema_name": metadata["query"]["schema"],
            "csv_schema": schema,
            "compression": "ZIP container with Zstandard-compressed CSV member",
            "timestamp_representation": "ISO-8601 nanosecond text with Z suffix",
            "source_timezone": "UTC",
            "timestamp_convention": "Databento OHLCV interval start; close availability is +1 minute",
            "first_permitted_timestamp": first_timestamp.isoformat() if first_timestamp else None,
            "last_permitted_timestamp": last_timestamp.isoformat() if last_timestamp else None,
            "allowed_years": sorted(allowed_years),
            "series_status": "parent-symbol extract containing individual contracts and calendar spreads; not a documented continuous series",
            "roll_methodology": "UNKNOWN",
            "raw_rows": raw_rows,
            "outright_nq_rows": outright_rows,
            "calendar_spread_rows": spread_rows,
            "non_nq_rows": non_nq_rows,
            "outright_contract_symbols": sorted(contract_rows),
            "outright_contract_row_counts": dict(sorted(contract_rows.items())),
            "outright_contract_volumes": dict(sorted(contract_volume.items())),
            "calendar_spread_symbol_count": len(spread_symbols),
            "duplicate_symbol_timestamps": duplicate_symbol_timestamps,
            "repeated_timestamp_rows_across_distinct_instruments": repeated_timestamp_rows
            - duplicate_symbol_timestamps,
            "missing_bars": "UNKNOWN without a session/holiday/contract-listing calendar",
            "observed_gt_one_minute_intervals_within_contract": observed_gap_count,
            "maximum_observed_gap_minutes": maximum_observed_gap_minutes,
            "nonpositive_volume_rows": nonpositive_volume,
            "invalid_ohlc_rows": invalid_ohlc,
            "price_discontinuity_rule": "absolute same-contract close-to-next-open change >=100 points when elapsed <=2 minutes",
            "price_discontinuity_count": discontinuity_count,
            "maximum_adjacent_price_change_points": format(maximum_adjacent_price_change, "f"),
            "repair_actions": [],
        }


def main() -> None:
    results = [scan(config) for config in ARCHIVES]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for result in results:
        print(
            result["archive_filename"],
            result["allowed_years"],
            result["raw_rows"],
            result["outright_nq_rows"],
            result["invalid_ohlc_rows"],
        )


if __name__ == "__main__":
    main()
