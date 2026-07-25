"""Rebuild outputs/stage_02/LEDGER_HASHES.csv from the ledgers on disk.

Ledger bytes embed the producing code SHA, so a hash is only meaningful next to
that SHA. Reruns at a later commit legitimately produce different bytes; the
invariant that must hold across commits is equality ignoring the code_sha
column, not equality of these digests.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAILED = ROOT / "outputs" / "stage_02" / "detailed"


def main() -> None:
    rows = []
    for checkpoint in sorted(DETAILED.glob("checkpoint_*.json")):
        summary = json.loads(checkpoint.read_text())
        year = summary["year"]
        for ledger in sorted(DETAILED.glob(f"*_{year}.csv.gz")):
            rows.append(
                {
                    "year": year,
                    "filename": ledger.name,
                    "bytes": ledger.stat().st_size,
                    "sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
                    "code_sha": summary["code_sha"],
                    "dataset_sha256": summary["dataset_sha256"],
                }
            )
    destination = ROOT / "outputs" / "stage_02" / "LEDGER_HASHES.csv"
    fields = ("year", "filename", "bytes", "sha256", "code_sha", "dataset_sha256")
    with destination.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"recorded {len(rows)} ledgers across {len({r['year'] for r in rows})} partitions")


if __name__ == "__main__":
    main()
