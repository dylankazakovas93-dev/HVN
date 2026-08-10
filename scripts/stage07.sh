#!/usr/bin/env bash
# Stage 7, end to end, one command. Safe to Ctrl-C and re-run: every step skips
# work already on disk, so a re-run resumes rather than restarts.
#
#   ./scripts/stage07.sh
#
# Steps 1 and 3 stream ~1.9 GB of remote Parquet over tens of thousands of
# ranged reads across many hours, and the host drops one every so often. The
# reader retries individual reads; this loop retries the whole step, because a
# failure can also land on the redirect that resolves the download URL, which
# the reader never sees. Both layers are needed and neither loses progress.

set -uo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH="src:scripts"
PY="${PYTHON:-python3}"
ATTEMPTS="${ATTEMPTS:-8}"

log() { printf '\n=== %s ===\n' "$1"; }

persist() {
  # Re-run a resumable step until it completes or the budget runs out.
  local label="$1"; shift
  local attempt=1 delay=15
  while true; do
    if "$@"; then
      return 0
    fi
    if [ "$attempt" -ge "$ATTEMPTS" ]; then
      echo "$label: giving up after $attempt attempts" >&2
      return 1
    fi
    echo "$label: attempt $attempt failed, retrying in ${delay}s (progress is kept)" >&2
    sleep "$delay"
    attempt=$((attempt + 1))
    delay=$((delay * 2))
    [ "$delay" -gt 300 ] && delay=300
  done
}

log "1/4  building half-hour buckets from the one-second file (resumable)"
persist "buckets" "$PY" scripts/build_buckets.py || exit 1

log "2/4  tier frequencies (level counts only, no outcomes)"
if [ -f outputs/stage_07_calibration/frequency.json ]; then
  echo "already calibrated; delete outputs/stage_07_calibration to redo"
else
  persist "calibration" "$PY" scripts/calibrate_tiers.py --sessions 20 || exit 1
fi

log "3/4  the scan: tap, then race to 1/3/5 ATR (resumable)"
persist "scan" "$PY" scripts/run_stage07.py || exit 1

log "4/4  aggregating"
"$PY" scripts/aggregate_stage07.py || exit 1

log "done"
echo "Full output written under outputs/stage_07_races/aggregate/"
echo "Send back everything printed by step 4."
