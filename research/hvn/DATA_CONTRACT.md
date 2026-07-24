# Data Contract

Authoritative research input is outright MNQ one-minute OHLCV. Required raw
fields are source row identity, event timestamp, open, high, low, close, volume,
and symbol/contract identity.

- Raw data are immutable.
- `ts_event` from Databento one-minute OHLCV is treated as interval start;
  completed-bar close time is one minute later.
- Derived times use `America/New_York` with IANA DST behavior.
- Prices and volume are parsed as exact decimals.
- MNQ tick size is 0.25 points.
- Negative volume, inconsistent OHLC, duplicate row IDs, and duplicate
  symbol/timestamps are rejected and recorded; none is silently repaired.
- Calendar spreads and non-MNQ symbols are rejected.
- The ingestion stream checks the authorized year before constructing a Bar and
  stops before a later year is parsed.
- Source row IDs are carried into every profile ledger.

Development: 2019, 2021, 2023, 2025, partial 2026. Frozen validation: 2020 and
2022. Final untouched holdout: 2024.

The supplied archives are documented as `NQ.FUT` and therefore fail this
contract. Their SHA-256 values are logged as access evidence, not approved MNQ
dataset identities.
