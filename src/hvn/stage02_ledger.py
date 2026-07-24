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


def deterministic_csv_bytes(
    records: Iterable[object | Mapping[str, object]],
    fields: tuple[str, ...] | list[str],
    *,
    sort_by: tuple[str, ...] | list[str] = (),
) -> bytes:
    normalized = []
    for record in records:
        if is_dataclass(record):
            row = asdict(record)
        else:
            row = dict(record)
        normalized.append({field: canonical(row.get(field)) for field in fields})
    if sort_by:
        normalized.sort(key=lambda row: tuple(row[field] for field in sort_by))
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
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(
        deterministic_gzip_csv_bytes(records, fields, sort_by=sort_by)
    )

