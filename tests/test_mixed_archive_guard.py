"""A mixed-year archive must yield the authorized year and nothing else.

`nq2018.zip` carries both 2018 and 2019 rows. The research partition is defined
by parsed timestamps, not by the archive filename, so reading 2019 from it is
authorized provided zero 2018 rows enter the pipeline.
"""

from __future__ import annotations

import io
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest

from hvn.io import databento_rows_with_audit

HEADER = "ts_event,rtype,publisher_id,instrument_id,open,high,low,close,volume,symbol\n"


def row(timestamp: str, symbol: str = "NQH9", volume: str = "10") -> str:
    return (
        f"{timestamp},33,1,10204,100.00,101.00,99.00,100.50,{volume},{symbol}\n"
    )


def build_mixed_archive(path: Path, member: str) -> None:
    """A member holding 2018 rows, then 2019 rows, then 2020 rows."""
    import zstandard

    body = HEADER
    for minute in range(5):
        body += row(f"2018-12-31T20:{minute:02d}:00.000000000Z")
    for minute in range(8):
        body += row(f"2019-01-02T14:{minute:02d}:00.000000000Z")
    body += row("2019-06-03T15:00:00.000000000Z", symbol="NQM9-NQU9")   # spread
    for minute in range(4):
        body += row(f"2020-01-02T14:{minute:02d}:00.000000000Z")
    compressed = zstandard.ZstdCompressor().compress(body.encode())
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, compressed)


def test_mixed_archive_yields_the_authorized_year_and_no_2018_row(tmp_path):
    member = "glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst"
    archive = tmp_path / "nq2018.zip"
    build_mixed_archive(archive, member)

    bars, audit = databento_rows_with_audit(
        archive, member, allowed_year=2019, dataset_sha256="deadbeef"
    )

    # Every admitted bar belongs to the authorized partition.
    assert bars, "expected 2019 bars"
    for bar in bars:
        assert bar.start_time.year == 2019, bar.source_row_id

    # Zero 2018 rows reached a constructed Bar.
    assert not any(bar.start_time.year == 2018 for bar in bars)
    assert not any(bar.close_time.year == 2018 for bar in bars)

    # The audit distinguishes container access from admitted empirical rows.
    assert audit.archive == "nq2018.zip"
    assert audit.requested_year == 2019
    assert 2018 in audit.parsed_years          # the container was traversed
    assert audit.rows_excluded_earlier_year == 5
    assert audit.rows_admitted == 8            # the spread row is not admitted
    assert audit.rows_skipped_non_outright == 1
    assert audit.dataset_sha256 == "deadbeef"


def test_ingestion_stops_before_any_later_year_row(tmp_path):
    member = "glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst"
    archive = tmp_path / "nq2018.zip"
    build_mixed_archive(archive, member)
    bars, audit = databento_rows_with_audit(
        archive, member, allowed_year=2019, dataset_sha256="x"
    )
    assert not any(bar.start_time.year == 2020 for bar in bars)
    # It breaks on the first later-year row rather than scanning them all.
    assert audit.rows_excluded_later_year == 1


def test_forbidden_partition_cannot_be_requested(tmp_path):
    member = "glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst"
    archive = tmp_path / "nq2018.zip"
    build_mixed_archive(archive, member)
    for forbidden in (2018, 2020, 2022, 2024):
        with pytest.raises(PermissionError):
            databento_rows_with_audit(
                archive, member, allowed_year=forbidden, dataset_sha256="x"
            )


def test_audit_matches_the_plain_reader_on_the_same_input(tmp_path):
    """The audited path admits exactly what the accepted reader admits."""
    from hvn.io import databento_rows_from_zip

    member = "glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst"
    archive = tmp_path / "nq2018.zip"
    build_mixed_archive(archive, member)
    plain = databento_rows_from_zip(archive, member, allowed_year=2019)
    audited, _ = databento_rows_with_audit(
        archive, member, allowed_year=2019, dataset_sha256="x"
    )
    assert [b.source_row_id for b in plain] == [b.source_row_id for b in audited]
    assert [b.close for b in plain] == [b.close for b in audited]
