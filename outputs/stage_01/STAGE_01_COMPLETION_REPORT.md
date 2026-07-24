# Stage 1 Completion Report

## Outcome

Stage 1 is **BLOCKED**, not failed. The deterministic engine and synthetic audit
evidence are complete, but the supplied files are NQ—not authoritative MNQ—so
the required empirical MNQ audit pack was not fabricated from the wrong
instrument.

This project uses a uniform bar-volume allocation proxy and a TPO/range-
occupancy proxy. Neither is exact exchange volume at price.

## Repository

- Starting state: empty GitHub repository; no starting SHA.
- Implementation/source-audit SHA:
  `018038824dfabea5e01b4184bbc990206d483bf7`.
- Branch: `main`.
- Remote: `https://github.com/dylankazakovas93-dev/HVN.git`.
- Final SHA: see `git rev-parse HEAD` after the completion commit.

## Data access

Inspected archives:

| File | SHA-256 | Market rows parsed |
|---|---|---|
| `nq2021.zip` | `0336cfac5fe804a4c756ff9372a0bad314e526c389e5dd8da3774883a29b2f62` | first 5 rows, 2021 only |
| `nq2023.zip` | `c982860543d8db5d18d9cbe751d9655f8e46bf76ae5513b7fd7a9dcd7b740773` | first row, 2023 only |
| `nq2025.zip` | `b4fcf58ff5db70d2a8d45d605ce5a2742ab003a1cf694ef2721a04562b6608e2` | first row, 2025 only |

The 2025 archive metadata identifies `NQ.FUT`. Parsed row years were exactly
2021, 2023, and 2025. No 2020, 2022, or 2024 market-data row was parsed,
profiled, summarized, or calculated. `nq2018.zip` and `nq2020.zip` were not
opened. The mixed-year member names were visible in the 2021/2023 archive
central directories; stream reads stopped within the permitted year.

Full evidence is in `research/hvn/PARTITION_ACCESS_LOG.csv`.

## Implementation

Profile families: prior RTH, full overnight, midnight, opening-hour RTH.

Allocation methods: uniform bar-volume allocation proxy and TPO/range-occupancy
proxy.

Bin definitions: ATR(24) ratios 0.05, 0.10, 0.20; round-half-up to 0.25 ticks;
global 0.00 origin; half-open `[low, high)` bins; exact-boundary high exclusion.

HVN definitions: local/plateau peaks, ±0.50 ATR median baseline, prominence
thresholds 1.5/2.0/2.5, inclusive threshold equality, 50% peak boundary, and
deterministic touching/overlap merges.

Synthetic uniform profiles each conserved exactly 600 source-volume units into
600 allocated units. Synthetic TPO profiles each produced exactly 60 occupancy
units from 60 bars. Two consecutive full audit generations had identical file
hashes.

## Verification

- `PYTHONPATH=src pytest`: **52 passed**.
- `python3 -m compileall -q src tests scripts`: passed.
- `git diff --check`: passed.
- end-to-end audit integration covers all 4 families × 2 methods;
- profile ledger reruns and full audit-pack reruns are byte-identical;
- criterion evidence is in `research/hvn/STAGE_01_GATE.md`.

## Files

Created control files:

`README.md`, `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`,
`KNOWN_LIMITATIONS.md`, `PROJECT_STATUS.md`, `PROGRESS.md`,
`RUN_REGISTRY.csv`, `.gitignore`, and `pyproject.toml`.

Created research contracts:

`research/hvn/RESEARCH_CHARTER.md`, `DATA_CONTRACT.md`,
`SESSION_CONTRACT.md`, `PROFILE_SPEC.md`, `HVN_SPEC.md`, `PARTITIONS.json`,
`PARTITION_ACCESS_LOG.csv`, and `STAGE_01_GATE.md`.

Created implementation:

`src/hvn/__init__.py`, `models.py`, `atr.py`, `sessions.py`, `engine.py`,
`hvn.py`, `ledger.py`, `partitions.py`, `io.py`, `audit.py`, and `cli.py`;
`scripts/generate_stage_01_audit.py`.

Created verification:

`tests/conftest.py`, `test_engine.py`, `test_atr_sessions.py`, `test_hvn.py`,
`test_partitions_io.py`, `test_audit.py`, and three manual CSV fixtures plus
their README.

Created audit outputs:

`outputs/stage_01/README.md`, this report, and
`outputs/stage_01/synthetic/` containing a manifest plus profile, candidate,
node, and SVG artifacts for all eight family/method combinations.

## Commands

Material terminal commands, in execution order:

```text
git clone https://github.com/dylankazakovas93-dev/HVN.git HVN
shasum -a 256 <each authorized development archive>
unzip -l <each authorized development archive>
python3 <bounded Zstandard stream readers for 2021/2023/2025 headers and rows>
PYTHONPATH=src pytest
PYTHONPATH=src python3 -m hvn.cli synthetic-audit --output outputs/stage_01/synthetic
shasum -a 256 outputs/stage_01/synthetic/*
PYTHONPATH=src pytest
python3 -m compileall -q src tests scripts
git diff --check
git add .
git commit -m 'Build deterministic Stage 1 MNQ profile engine'
PYTHONPATH=src python3 -m hvn.cli synthetic-audit --output outputs/stage_01/synthetic --code-sha 018038824dfabea5e01b4184bbc990206d483bf7
PYTHONPATH=src pytest
git diff --check
git add .
git commit -m 'Finalize Stage 1 audit evidence'
git push origin main
```

Early failed/diagnostic runs are retained in `RUN_REGISTRY.csv`.

## Known limitations and next action

Holiday/early-close and causal roll-selection behavior cannot be empirically
verified without authoritative MNQ source documentation. No forward/revisit or
performance work exists.

The exact next authorized action is to supply an outright MNQ one-minute OHLCV
development archive (small 2021, 2023, or 2025/partial-2026 samples are enough)
with contract/roll documentation, rerun the Stage 1 empirical numerical/visual
audit, and update criterion 14. Do not begin Stage 2.

## Historical status amended by Stage 1B

This report preserves the original MNQ-authoritative Stage 1 decision and
blocked result. Stage 1B subsequently authorized NQ as the profile and signal
market, kept MNQ as an untested eventual execution market, replaced visual gate
evidence with independent numerical/code reconciliation, and passed the revised
Stage 1 gate. See `outputs/stage_01b/STAGE_01B_COMPLETION_REPORT.md`.
