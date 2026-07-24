from __future__ import annotations

import csv
import io
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from .models import FrozenProfile, HvnNode, PeakCandidate


def _format(value) -> str:
    if isinstance(value, Decimal):
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def profile_ledger_bytes(profile: FrozenProfile) -> bytes:
    fields = [
        "profile_id", "profile_family", "source_session_date", "source_start",
        "source_end", "freeze_time", "allocation_method", "atr_reference_time",
        "atr_value", "bin_ratio", "bin_size_raw", "bin_size_rounded", "bin_index",
        "profile_range_low", "profile_range_high",
        "bin_low", "bin_high", "bin_center", "profile_weight", "weight_share",
        "cumulative_weight_share", "is_poc", "source_bar_count",
        "source_row_ids", "source_total_volume", "allocated_total_volume",
        "code_sha", "data_partition",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    common = {
        "profile_id": profile.profile_id,
        "profile_family": profile.window.family.value,
        "source_session_date": profile.window.source_session_date,
        "source_start": profile.window.source_start,
        "source_end": profile.window.source_end,
        "freeze_time": profile.window.freeze_time,
        "allocation_method": profile.allocation_method.value,
        "atr_reference_time": profile.atr_reference_time,
        "atr_value": profile.atr_value,
        "bin_ratio": profile.bin_ratio,
        "bin_size_raw": profile.bin_size_raw,
        "bin_size_rounded": profile.bin_size_rounded,
        "profile_range_low": profile.profile_range_low,
        "profile_range_high": profile.profile_range_high,
        "source_bar_count": len(profile.source_row_ids),
        "source_row_ids": "|".join(profile.source_row_ids),
        "source_total_volume": profile.source_total_volume,
        "allocated_total_volume": profile.allocated_total_volume,
        "code_sha": profile.code_sha,
        "data_partition": profile.data_partition,
    }
    for bin_ in profile.bins:
        row = common | asdict(bin_)
        writer.writerow({key: _format(row[key]) for key in fields})
    return output.getvalue().encode("utf-8")


def write_profile_ledger(profile: FrozenProfile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(profile_ledger_bytes(profile))


def write_records(
    records: tuple[PeakCandidate, ...] | tuple[HvnNode, ...],
    destination: Path,
    *,
    record_type: type[PeakCandidate] | type[HvnNode] | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        if record_type is None:
            raise ValueError("record_type is required for an empty ledger")
        fields = list(record_type.__dataclass_fields__)
        with destination.open("w", newline="", encoding="utf-8") as stream:
            csv.DictWriter(stream, fieldnames=fields, lineterminator="\n").writeheader()
        return
    fields = list(asdict(records[0]))
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({k: _format(v) for k, v in asdict(record).items()})
