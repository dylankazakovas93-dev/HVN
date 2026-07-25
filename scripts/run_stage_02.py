from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from hvn.io import databento_rows_from_zip
from hvn.stage02_pipeline import run_year, write_year_result

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "stage_02" / "detailed"
SOURCES = {
    2019: ("nq2018.zip", "glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst"),
    2021: ("nq2021.zip", "glbx-mdp3-20210101-20221230.ohlcv-1m.csv.zst"),
    2023: ("nq2023.zip", "glbx-mdp3-20230101-20241230.ohlcv-1m.csv.zst"),
    2025: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
    2026: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
}


def archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, choices=sorted(SOURCES), required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    archive, member = SOURCES[args.year]
    source = args.data_root / archive
    # The dataset identity is computed from the bytes actually read, never asserted.
    dataset_hash = archive_sha256(source)
    bars = databento_rows_from_zip(source, member, allowed_year=args.year)
    result = run_year(bars, year=args.year, code_sha=sha)
    write_year_result(result, OUTPUT, year=args.year)
    summary = {
        "year": args.year,
        "archive": archive,
        "member": member,
        "dataset_sha256": dataset_hash,
        "code_sha": sha,
        "bars": len(bars),
        "profiles": len(result.profile_rows),
        "opportunities": len(result.opportunity_rows),
        "events": len(result.event_rows),
        "control_opportunities": len(result.control_opportunity_rows),
        "control_events": len(result.control_event_rows),
        "metric_rows": len(result.metric_rows),
        "match_events": len(result.match_events),
        "episode_events": len(result.episode_events),
    }
    (OUTPUT / f"checkpoint_{args.year}.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
