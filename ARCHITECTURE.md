# Architecture

The package is deliberately small and separates causal inputs from deterministic
derivations.

1. `hvn.io` reads Databento CSV/Zstandard streams with development-year and
   outright-MNQ guards. Source timestamps are interval starts and are converted
   to completed-bar close times by adding one minute.
2. `hvn.atr` computes completed one-minute Wilder ATR(24) and exposes the latest
   value available at or before profile source start.
3. `hvn.sessions` creates four explicit New York source windows. Upstream code
   must select actual trading dates; this module does not guess holidays.
4. `hvn.engine` maps inclusive bar ranges onto a global zero-origin,
   half-open-bin grid; constructs uniform-volume or TPO proxies; conserves
   volume; and freezes POC and profile data in immutable dataclasses.
5. `hvn.hvn` identifies plateaus/local peaks, local median baselines,
   prominence, half-peak node boundaries, and merged touching/overlapping nodes.
6. `hvn.ledger` emits stable, price-ordered CSV bytes with source row lineage.
7. `hvn.audit` creates deterministic synthetic engineering audit artifacts.

The same `construct_profile` function serves all profile families, allocation
methods, and authorized ATR ratios.
