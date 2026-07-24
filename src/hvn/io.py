from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timedelta, timezone
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
) -> tuple[Bar, ...]:
    """Read one allowed year, stopping before any later year is parsed.

    Databento OHLCV timestamps identify the minute interval start. The derived
    Bar.close_time is therefore ts_event + one minute. Only outright MNQ
    symbols are accepted; spreads and other instruments are rejected.
    """
    assert_development_year(allowed_year)
    assert_path_not_forbidden(path)
    try:
        import zstandard
    except ImportError as exc:
        raise RuntimeError("install the optional 'data' dependencies") from exc
    bars: list[Bar] = []
    with zipfile.ZipFile(path) as archive, archive.open(member) as compressed:
        with zstandard.ZstdDecompressor().stream_reader(compressed) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8")
            reader = csv.DictReader(text)
            for ordinal, row in enumerate(reader, 2):
                timestamp = datetime.fromisoformat(row["ts_event"].replace("Z", "+00:00"))
                if timestamp.year < allowed_year:
                    continue
                if timestamp.year > allowed_year:
                    break
                symbol = row["symbol"]
                if not symbol.startswith("MNQ") or "-" in symbol:
                    raise ValueError(f"non-outright-MNQ symbol at source row {ordinal}: {symbol}")
                bars.append(
                    Bar(
                        f"{path.name}:{member}:{ordinal}",
                        (timestamp + timedelta(minutes=1)).astimezone(NY),
                        Decimal(row["open"]),
                        Decimal(row["high"]),
                        Decimal(row["low"]),
                        Decimal(row["close"]),
                        Decimal(row["volume"]),
                        symbol,
                    )
                )
                if maximum_rows is not None and len(bars) >= maximum_rows:
                    break
    return tuple(bars)
