# NQ Historical Profile and HVN Engine

Stage 1 builds deterministic frozen historical profiles and locally prominent
high-volume-node (HVN) zones from NQ one-minute OHLCV.

The primary representation is a **uniform bar-volume allocation proxy**. It is
not an exact exchange volume-at-price profile because one-minute OHLCV does not
contain transaction-level volume at price. The secondary representation is a
**TPO/range-occupancy proxy**.

## Authoritative markets

```text
AUTHORITATIVE PROFILE MARKET = NQ
AUTHORITATIVE SIGNAL MARKET = NQ
EVENTUAL EXECUTION MARKET = MNQ, NOT YET TESTED
```

Stage 1B amended the original MNQ-authoritative contract after the supplied
archives were confirmed as NQ. The historical decision remains preserved in
Git and in the Stage 1 completion report. NQ and MNQ volume distributions are
not assumed identical, and no MNQ execution or portability result is claimed.

## Current evidence

The revised Stage 1 gate relies on direct code inspection, independent
hand-calculated Decimal oracles, property/metamorphic tests, real NQ numerical
ledger reconciliation, and byte-identical reruns. Charts are not gate evidence.
Historical synthetic SVG files remain in the repository but are not regenerated
or reviewed in Stage 1B.

No forward returns, MFE/MAE, trade simulation, strategy optimization, validation
analysis, or holdout analysis exists in this repository.

## Reproduce Stage 1B

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,data]'
PYTHONPATH=src .venv/bin/python reviews/run_stage_01b_oracle.py
PYTHONPATH=src .venv/bin/python scripts/run_stage_01b_reconciliation.py
PYTHONPATH=src .venv/bin/pytest
```

## Authorized scope

Only profile construction, HVN extraction, and their numerical audit are
authorized. Development years are 2019, 2021, 2023, 2025, and partial 2026.
Frozen validation years are 2020 and 2022; final untouched holdout is 2024.
Stage 1B must not access market data for 2020, 2022, or 2024 and must not use
2018.

See `research/hvn/STAGE_01_GATE.md` and
`reviews/STAGE_01B_CODE_AUDIT.md` for criterion-level evidence.
