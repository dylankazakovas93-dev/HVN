from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class IngestionAudit:
    """Record of which rows a year-filtered ingestion admitted and excluded.

    An archive filename does not define a research partition; parsed timestamps
    do. `nq2018.zip` carries both 2018 and 2019 rows and is a legitimate source
    for the authorized 2019 partition, provided no 2018 row is admitted.
    """

    archive: str
    member: str
    requested_year: int
    parsed_years: tuple[int, ...]
    rows_admitted: int
    rows_excluded_earlier_year: int
    rows_excluded_later_year: int
    rows_skipped_non_outright: int
    dataset_sha256: str


def databento_rows_with_audit(
    path: Path,
    member: str,
    *,
    allowed_year: int,
    dataset_sha256: str,
    symbol: str | None = None,
) -> tuple[tuple[Bar, ...], IngestionAudit]:
    """Read exactly one year from a possibly mixed-year archive, with an audit.

    Streams rows, admitting only timestamps belonging to `allowed_year`. Raises
    immediately if a row outside that year would reach a constructed Bar.
    """
    assert_development_year(allowed_year)
    assert_path_not_forbidden(path)
    try:
        import zstandard
    except ImportError as exc:
        raise RuntimeError("install the optional 'data' dependencies") from exc

    bars: list[Bar] = []
    years_seen: set[int] = set()
    earlier = later = skipped = 0
    with zipfile.ZipFile(path) as archive, archive.open(member) as compressed:
        with zstandard.ZstdDecompressor().stream_reader(compressed) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            header = text.readline().rstrip("\r\n").split(",")
            positions = {name: index for index, name in enumerate(header)}
            required = {"ts_event", "open", "high", "low", "close", "volume", "symbol"}
            if not required <= positions.keys():
                raise ValueError(
                    f"missing required OHLCV columns: {sorted(required - positions.keys())}"
                )
            for ordinal, line in enumerate(text, 2):
                # The year prefix is read before any CSV field or price is parsed.
                row_year = int(line[:4])
                years_seen.add(row_year)
                if row_year < allowed_year:
                    earlier += 1
                    continue
                if row_year > allowed_year:
                    later += 1
                    break
                fields = line.rstrip("\r\n").split(",")
                timestamp = datetime.fromisoformat(
                    fields[positions["ts_event"]].replace("Z", "+00:00")
                )
                if timestamp.year != allowed_year:
                    raise AssertionError(
                        f"row outside the authorized partition reached ingestion: "
                        f"{timestamp.isoformat()} while reading {allowed_year}"
                    )
                row_symbol = fields[positions["symbol"]]
                if not row_symbol.startswith("NQ") or "-" in row_symbol:
                    skipped += 1
                    continue
                if symbol is not None and row_symbol != symbol:
                    skipped += 1
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
    for bar in bars:
        if bar.close_time.year != allowed_year and not (
            bar.close_time.year == allowed_year + 1
            and bar.close_time.month == 1
            and bar.close_time.day == 1
        ):
            raise AssertionError(f"admitted bar outside {allowed_year}: {bar.source_row_id}")
    return tuple(bars), IngestionAudit(
        archive=path.name,
        member=member,
        requested_year=allowed_year,
        parsed_years=tuple(sorted(years_seen)),
        rows_admitted=len(bars),
        rows_excluded_earlier_year=earlier,
        rows_excluded_later_year=later,
        rows_skipped_non_outright=skipped,
        dataset_sha256=dataset_sha256,
    )
