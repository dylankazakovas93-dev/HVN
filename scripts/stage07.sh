#!/usr/bin/env bash
# Stage 7, end to end, one command. Safe to Ctrl-C and re-run: every step skips
# work that is already on disk, so a re-run resumes rather than restarts.
#
#   ./scripts/stage07.sh
#
# Steps 1 and 3 are the long ones. Step 2 only prints level counts and cannot
# see an outcome; it is here so the tier frequencies are visible before the
# scan, not to gate it.

set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="src:scripts"
PY="${PYTHON:-python3}"

log() { printf '\n=== %s ===\n' "$1"; }

log "1/4  building half-hour buckets from the one-second file (resumable)"
"$PY" scripts/build_buckets.py

log "2/4  tier frequencies (level counts only, no outcomes)"
"$PY" scripts/calibrate_tiers.py --sessions 20

log "3/4  the scan: tap, then race to 1/3/5 ATR (resumable)"
"$PY" scripts/run_stage07.py

log "4/4  aggregating"
"$PY" scripts/aggregate_stage07.py

log "done"
echo "Full output written under outputs/stage_07_races/aggregate/"
echo "Send back everything printed by step 4."
