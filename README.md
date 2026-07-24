# MNQ Historical Profile and HVN Engine

Stage 1 builds deterministic frozen historical profiles and locally prominent
high-volume-node (HVN) zones from MNQ one-minute OHLCV.

The primary representation is a **uniform bar-volume allocation proxy**. It is
not an exact exchange volume-at-price profile because one-minute OHLCV does not
contain transaction-level volume at price. The secondary representation is a
**TPO/range-occupancy proxy**.

## Current status

The engine, synthetic fixtures, ledgers, and tests are implemented. Empirical
MNQ audit generation is **BLOCKED**: the supplied archives document and contain
`NQ.FUT`, including calendar spreads, rather than MNQ. The code refuses to
silently substitute NQ for the authoritative MNQ instrument.

No forward returns, MFE/MAE, trade simulation, strategy optimization, validation
analysis, or holdout analysis exists in this repository.

## Reproduce

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,data]'
.venv/bin/pytest
.venv/bin/hvn-stage1 synthetic-audit --output outputs/stage_01/synthetic --code-sha "$(git rev-parse HEAD)"
shasum -a 256 outputs/stage_01/synthetic/* | sort
```

The audit command writes profile, candidate, and node ledgers plus SVG audit
charts for all four families and both allocation methods. These artifacts use
synthetic data only and are engineering evidence, not market evidence.

## Authorized scope

Only profile construction and HVN extraction are authorized. Development years
are 2019, 2021, 2023, 2025, and partial 2026. The first frozen validation years
are 2020 and 2022; the final untouched holdout is 2024. Stage 1 must not access
market-data rows for 2020, 2022, or 2024.

See `research/hvn/STAGE_01_GATE.md` for criterion-level status.
