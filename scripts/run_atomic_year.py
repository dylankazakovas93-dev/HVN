"""Run one Generation 3 atomic partition from an authorized development archive.

Reads only the requested year. The year-prefix guard in `hvn.io` stops before
any row outside that year is parsed, so 2019 is read from nq2018.zip without
parsing a 2018 row.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from hvn.atomic_pipeline import run_atomic_year, write_atomic_year
from hvn.io import databento_rows_from_zip

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "stage_02_generation_3_atomic"

SOURCES = {
    2019: ("nq2018.zip", "glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst"),
    2021: ("nq2021.zip", "glbx-mdp3-20210101-20221230.ohlcv-1m.csv.zst"),
    2023: ("nq2023.zip", "glbx-mdp3-20230101-20241230.ohlcv-1m.csv.zst"),
    2025: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
    2026: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
}
FORBIDDEN_YEARS = (2018, 2020, 2022, 2024)


def archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="run_atomic_year.py",
        description="Run one Generation 3 atomic development partition.",
    )
    parser.add_argument("--year", type=int, choices=sorted(SOURCES), required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)

    output = args.output_root.resolve()
    # Path comparison, not substring: outputs/stage_02_generation_3_atomic is
    # not inside outputs/stage_02 even though its name starts with it.
    for reserved in (
        ROOT / "outputs" / "stage_02",
        ROOT / "outputs" / "stage_02_generation_2",
    ):
        if output == reserved or reserved in output.parents:
            parser.error(f"refusing to write into a preserved generation: {output}")

    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    archive, member = SOURCES[args.year]
    source = (args.data_root / archive).resolve()
    dataset_hash = archive_sha256(source)

    bars = databento_rows_from_zip(source, member, allowed_year=args.year)
    # Independent post-ingestion guard: no bar may carry a forbidden year.
    for bar in bars:
        if bar.close_time.year in FORBIDDEN_YEARS:
            raise AssertionError(
                f"forbidden partition row reached the parser: {bar.source_row_id}"
            )

    result = run_atomic_year(bars, year=args.year, code_sha=code_sha)
    detail = output / "detailed"
    write_atomic_year(result, detail, year=args.year)

    ledgers = {}
    for path in sorted(detail.glob(f"*_{args.year}.csv.gz")):
        ledgers[path.name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    summary = {
        "year": args.year,
        "archive": archive,
        "member": member,
        "dataset_sha256": dataset_hash,
        "code_sha": code_sha,
        "bars": len(bars),
        "profiles": len(result.profile_rows),
        "atomic_opportunities": len(result.opportunity_rows),
        "atomic_events": len(result.event_rows),
        "control_opportunities": len(result.control_opportunity_rows),
        "control_events": len(result.control_event_rows),
        "proximity_rows": len(result.proximity_rows),
        "residence_rows": len(result.residence_rows),
        "departure_rows": len(result.departure_rows),
        "excursion_rows": len(result.excursion_rows),
        "ledgers": ledgers,
        "reproduction_command": (
            f"PYTHONPATH=src python3 scripts/run_atomic_year.py --year {args.year} "
            f"--data-root <data-root> --output-root {output.name}"
        ),
    }
    (detail / f"checkpoint_{args.year}.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "ledgers"},
                     sort_keys=True, default=str))


if __name__ == "__main__":
    main()
