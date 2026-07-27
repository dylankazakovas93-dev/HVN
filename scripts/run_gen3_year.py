"""Run one Generation 3 development partition end to end."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

from hvn.gen3_pipeline import run_gen3_year, write_gen3_year
from hvn.io import databento_rows_with_audit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "stage_02_generation_3_final"
RESERVED = (
    ROOT / "outputs" / "stage_02",
    ROOT / "outputs" / "stage_02_generation_2",
    ROOT / "outputs" / "stage_02_generation_3_atomic",
    ROOT / "outputs" / "stage_02_generation_3_atomic_pilot_v2",
    ROOT / "outputs" / "stage_02_generation_3_atomic_pilot_v3",
    ROOT / "outputs" / "stage_02_generation_3_atomic_pilot_v4",
)
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


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="run_gen3_year.py",
        description="Run one Generation 3 development partition. Reads no forbidden year.",
    )
    parser.add_argument("--year", type=int, choices=sorted(SOURCES), required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    output = args.output_root.resolve()
    for reserved in RESERVED:
        if output == reserved or reserved in output.parents:
            parser.error(f"refusing to write into a preserved generation: {output}")
    args.output_root = output
    return args


def main(argv=None) -> None:
    args = parse_args(argv)
    started = time.time()
    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    archive, member = SOURCES[args.year]
    source = (args.data_root / archive).resolve()
    dataset_sha = archive_sha256(source)

    bars, audit = databento_rows_with_audit(
        source, member, allowed_year=args.year, dataset_sha256=dataset_sha
    )
    result = run_gen3_year(bars, year=args.year, code_sha=code_sha)
    detail = args.output_root / "detailed"
    write_gen3_year(result, detail, year=args.year)

    ledgers = {
        p.name: {"bytes": p.stat().st_size,
                 "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted(detail.glob(f"*_{args.year}.csv.gz"))
    }
    summary = {
        "year": args.year,
        "ingestion_audit": asdict(audit),
        "dataset_sha256": dataset_sha,
        "code_sha": code_sha,
        "bars": len(bars),
        "node_opportunities": len(result.node_opportunities),
        "node_events": len(result.node_events),
        "control_opportunities": len(result.control_opportunities),
        "control_events": len(result.control_events),
        "forward_metric_rows": len(result.forward_metrics),
        "activity_metric_rows": len(result.activity_metrics),
        "departure_rows": len(result.departure_metrics),
        "excursion_rows": len(result.excursion_metrics),
        "ledgers": ledgers,
        "runtime_seconds": round(time.time() - started, 1),
        "reproduction_command": (
            f"PYTHONPATH=src python3 scripts/run_gen3_year.py --year {args.year} "
            f"--data-root <data-root>"
        ),
    }
    (detail / f"checkpoint_{args.year}.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n"
    )
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("ledgers", "ingestion_audit")},
                     sort_keys=True, default=str))


if __name__ == "__main__":
    main()
