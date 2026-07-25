from __future__ import annotations

import csv
import gzip
import io
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping

_WRITE_BATCH_ROWS = 50_000


def canonical(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (tuple, list)):
        return "|".join(canonical(item) for item in value)
    return str(value)


def _normalized_rows(
    records: Iterable[object | Mapping[str, object]],
    fields: tuple[str, ...] | list[str],
    *,
    sort_by: tuple[str, ...] | list[str] = (),
) -> list[dict[str, str]]:
    normalized = []
    for record in records:
        if is_dataclass(record):
            row = asdict(record)
        else:
            row = dict(record)
        normalized.append({field: canonical(row.get(field)) for field in fields})
    if sort_by:
        normalized.sort(key=lambda row: tuple(row[field] for field in sort_by))
    return normalized


def deterministic_csv_bytes(
    records: Iterable[object | Mapping[str, object]],
    fields: tuple[str, ...] | list[str],
    *,
    sort_by: tuple[str, ...] | list[str] = (),
) -> bytes:
    normalized = _normalized_rows(records, fields, sort_by=sort_by)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(normalized)
    return stream.getvalue().encode("utf-8")


def deterministic_gzip_csv_bytes(
    records: Iterable[object | Mapping[str, object]],
    fields: tuple[str, ...] | list[str],
    *,
    sort_by: tuple[str, ...] | list[str] = (),
) -> bytes:
    payload = deterministic_csv_bytes(records, fields, sort_by=sort_by)
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
        compressed.write(payload)
    return output.getvalue()


def write_deterministic_gzip_csv(
    destination: Path,
    records: Iterable[object | Mapping[str, object]],
    fields: tuple[str, ...] | list[str],
    *,
    sort_by: tuple[str, ...] | list[str] = (),
) -> None:
    """Stream one deterministic gzip CSV straight to disk.

    Byte-for-byte identical to compressing deterministic_csv_bytes in memory:
    the same rows are normalized and sorted in the same order, and the same
    gzip parameters are used. Rows are handed to the compressor incrementally
    rather than materializing the CSV payload, its encoded copy, and the
    compressed buffer at once, which is what exhausted memory on the largest
    partition.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalized_rows(records, fields, sort_by=sort_by)
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            # Batches are staged in a text buffer and handed to the compressor as
            # encoded bytes. GzipFile.flush() is never called: it would emit a
            # Z_SYNC_FLUSH marker and change the compressed bytes.
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for start in range(0, len(normalized), _WRITE_BATCH_ROWS):
                writer.writerows(normalized[start : start + _WRITE_BATCH_ROWS])
                compressed.write(stream.getvalue().encode("utf-8"))
                stream.seek(0)
                stream.truncate(0)
            compressed.write(stream.getvalue().encode("utf-8"))

