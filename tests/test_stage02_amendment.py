from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_amendment_is_locked_before_empirical_access():
    amendment = (ROOT / "research/hvn/STAGE_02_AMENDMENT_01.md").read_text()
    assert "AUTHORIZED AND LOCKED BEFORE EMPIRICAL ACCESS" in amendment
    assert "a966f74a3b5d27efe656f81887988514016bfa0c" in amendment
    assert not (ROOT / "outputs/stage_02").exists()
    access_log = (ROOT / "research/hvn/PARTITION_ACCESS_LOG.csv").read_text()
    assert "stage_02" not in access_log.lower()


def test_validation_holdout_and_2018_archives_have_no_stage02_access():
    access_log = (ROOT / "research/hvn/PARTITION_ACCESS_LOG.csv").read_text().lower()
    stage02_rows = [line for line in access_log.splitlines() if "stage_02" in line]
    assert stage02_rows == []
    assert all(
        forbidden not in "\n".join(stage02_rows)
        for forbidden in ("nq2018", "nq2020", "nq2022", "nq2024")
    )
