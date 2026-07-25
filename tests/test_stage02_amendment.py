import csv
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_amendment_is_locked_before_empirical_access():
    amendment = (ROOT / "research/hvn/STAGE_02_AMENDMENT_01.md").read_text()
    assert "AUTHORIZED AND LOCKED BEFORE EMPIRICAL ACCESS" in amendment
    assert "a966f74a3b5d27efe656f81887988514016bfa0c" in amendment
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", "e5010f5", "e3c4f27"],
        cwd=ROOT,
        check=True,
    )


def test_no_stage02_access_parses_a_forbidden_partition():
    """No Stage 2 access may parse rows from 2020, 2022 or 2024.

    The guard is the parsed-year column, not the archive filename. Archive
    names do not partition the data: nq2021.zip carries forbidden 2022 rows
    and is legitimately read for 2021, while nq2018.zip carries 2018 and the
    declared development year 2019 and is legitimately read for 2019. Only
    nq2020.zip is wholly a frozen validation partition, so naming it at all
    is forbidden.
    """
    with (ROOT / "research/hvn/PARTITION_ACCESS_LOG.csv").open(newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if "stage_02" in row["operation"]]
    assert rows, "expected at least one Stage 2 access row"
    for row in rows:
        assert "nq2020" not in row["path"].lower(), row["access_id"]
        parsed = row["years_whose_market_rows_parsed"]
        for forbidden in ("2020", "2022", "2024"):
            assert forbidden not in parsed, f"{row['access_id']} parsed {forbidden}"
