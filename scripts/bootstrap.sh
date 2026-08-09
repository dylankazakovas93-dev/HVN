#!/usr/bin/env bash
# Restore a rolled-back workspace to the last pushed state and verify the caches.
# The container discards anything not on the remote between turns, so this is the
# first command of every session. It is idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."

git fetch -q origin stage-02-atomic-hvn
git reset --hard -q origin/stage-02-atomic-hvn
echo "code:      $(git log --oneline -1)"

PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from hvn.histogram_store import HistogramStore

scan = len(list(Path("outputs/stage_06_contract_validation/sessions").glob("rg_*.json")))
store = HistogramStore("outputs/stage_06_histograms")
print(f"scan cache: {scan} row groups")
print(f"histograms: {len(store.sessions)} sessions "
      f"{store.sessions[0]} .. {store.sessions[-1]}")
PY
