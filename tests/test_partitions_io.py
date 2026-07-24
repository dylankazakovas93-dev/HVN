from __future__ import annotations

from pathlib import Path

import pytest

from hvn.io import databento_rows_from_zip
from hvn.partitions import assert_development_year, assert_path_not_forbidden


@pytest.mark.parametrize("year", [2020, 2022, 2024, 2018])
def test_non_development_year_access_rejected(year):
    with pytest.raises(PermissionError):
        assert_development_year(year)


@pytest.mark.parametrize("year", [2019, 2021, 2023, 2025, 2026])
def test_declared_development_years_allowed(year):
    assert_development_year(year)


@pytest.mark.parametrize("name", ["nq2020.zip", "data_2022.csv", "/tmp/2024/file"])
def test_forbidden_year_path_access_rejected(name):
    with pytest.raises(PermissionError):
        assert_path_not_forbidden(name)


def test_instrument_guard_accepts_supplied_outright_nq_archive():
    path = Path("/Users/mariusvidziunas/Downloads/quant-data-upload/NQ/nq2025.zip")
    if not path.exists():
        pytest.skip("user-supplied mismatch fixture is unavailable")
    member = "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"
    bars = databento_rows_from_zip(path, member, allowed_year=2025, maximum_rows=1)
    assert len(bars) == 1
    assert bars[0].symbol == "NQH5"
