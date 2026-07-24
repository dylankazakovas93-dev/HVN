from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Bar
from .partitions import assert_development_year, assert_path_not_forbidden

NY = ZoneInfo("America/New_York")


def databento_rows_from_zip(
    path: Path,
    member: str,
    *,
    allowed_year: int,
    maximum_rows: int | None = None,
    symbol: str | None = None,
    start_utc: datetime | None = None,
    end_utc: datetime | None = None,
) -> tuple[Bar, ...]:
    """Read one allowed year, stopping before any later year is parsed.

    Databento OHLCV timestamps identify the minute interval start. The derived
    Bar.close_time is therefore ts_event + one minute. Only outright NQ
    contracts are retained; calendar spreads and other instruments are skipped.
    A requested contract symbol must itself be an outright NQ symbol.
    """
    assert_development_year(allowed_year)
    assert_path_not_forbidden(path)
    if symbol is not None and (not symbol.startswith("NQ") or "-" in symbol):
        raise ValueError(f"not an outright NQ contract: {symbol}")
    for boundary in (start_utc, end_utc):
        if boundary is not None and boundary.tzinfo is None:
            raise ValueError("UTC range boundaries must be timezone-aware")
    try:
        import zstandard
    except ImportError as exc:
        raise RuntimeError("install the optional 'data' dependencies") from exc
    bars: list[Bar] = []
    with zipfile.ZipFile(path) as archive, archive.open(member) as compressed:
        with zstandard.ZstdDecompressor().stream_reader(compressed) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            header = text.readline().rstrip("\r\n").split(",")
            positions = {name: index for index, name in enumerate(header)}
            required = {"ts_event", "open", "high", "low", "close", "volume", "symbol"}
            if not required <= positions.keys():
                raise ValueError(f"missing required OHLCV columns: {sorted(required - positions.keys())}")
            for ordinal, line in enumerate(text, 2):
                # The year prefix is checked before CSV fields or prices are parsed.
                row_year = int(line[:4])
                if row_year < allowed_year:
                    continue
                if row_year > allowed_year:
                    break
                fields = line.rstrip("\r\n").split(",")
                timestamp = datetime.fromisoformat(
                    fields[positions["ts_event"]].replace("Z", "+00:00")
                )
                if timestamp.year < allowed_year:
                    continue
                if timestamp.year > allowed_year:
                    break
                if start_utc is not None and timestamp < start_utc:
                    continue
                if end_utc is not None and timestamp >= end_utc:
                    break
                row_symbol = fields[positions["symbol"]]
                if not row_symbol.startswith("NQ") or "-" in row_symbol:
                    continue
                if symbol is not None and row_symbol != symbol:
                    continue
                bars.append(
                    Bar(
                        f"{path.name}:{member}:{ordinal}",
                        (timestamp + timedelta(minutes=1)).astimezone(NY),
                        Decimal(fields[positions["open"]]),
                        Decimal(fields[positions["high"]]),
                        Decimal(fields[positions["low"]]),
                        Decimal(fields[positions["close"]]),
                        Decimal(fields[positions["volume"]]),
                        row_symbol,
                    )
                )
                if maximum_rows is not None and len(bars) >= maximum_rows:
                    break
    return tuple(bars)
