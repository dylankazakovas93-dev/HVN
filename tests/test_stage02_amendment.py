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


def test_validation_holdout_and_2018_archives_have_no_stage02_access():
    access_log = (ROOT / "research/hvn/PARTITION_ACCESS_LOG.csv").read_text().lower()
    stage02_rows = [line for line in access_log.splitlines() if "stage_02" in line]
    assert all(
        forbidden not in "\n".join(stage02_rows)
        for forbidden in ("nq2018", "nq2020", "nq2022", "nq2024")
    )
