# Progress

## 2026-07-24

- Cloned an empty repository.
- Read the Stage 1 handoff and operating instructions.
- Inspected only container/header evidence needed to identify the supplied
  instrument mismatch; no 2020, 2022, or 2024 market-data row was parsed.
- Implemented the Stage 1 engine, ledgers, guarded ingestion, synthetic audit
  generator, and test suite.
- Recorded the NQ-versus-MNQ blocker without weakening the instrument contract.
- Did not begin acceptance, revisit, residence, departure, performance,
  validation, holdout, or trading work.
- Passed 52 tests and repeated byte-identical synthetic audit generation.
- Committed and pushed the Stage 1 repository. Stage 1 remains blocked only on
  authoritative MNQ input for the empirical audit gate.

## Stage 1B — 2026-07-24

- Verified local and remote `main` at required starting SHA
  `6aec1594745a1e2081f6a433106674c9bf0162db`.
- Preserved the historical MNQ-authoritative record and amended new work to NQ
  profiles/signals with MNQ execution explicitly untested.
- Replaced visual gate evidence with independent code/oracle/real-data numerical
  reconciliation. Historical SVG files remain untouched.
- Recorded independent findings before fixes in
  `reviews/STAGE_01B_FINDINGS.md`.
- Confirmed all supplied development archives as NQ parent-symbol extracts and
  recorded hashes, schemas, permitted coverage, duplicates, gaps, volume/OHLC,
  and discontinuity diagnostics.
- Resolved five preregistered audit findings with regression tests.
- Passed 6/6 independent fixtures, 16/16 real NQ profiles, exact uniform/TPO
  totals, 65 tests, post-freeze hashes, and byte-identical numerical reruns.
- Marked `STAGE_01_PROFILE_FOUNDATION = PASS`. Stage 2 was not begun.

## Stage 2 — 2026-07-24

- Created `stage-02-hvn-acceptance` from required SHA
  `697779c958f817a251b52721f1c82011c402e407`.
- Locked and pushed the five pre-results specifications in `521cf3d`.
- Implemented and pushed tick-exact events, causal features, both controls,
  acceptance metrics, censoring, and deterministic ledgers in `a966f74`; 98
  tests passed.
- Detected before empirical access that the original primary rules made every
  same-session match impossible: a 60-minute touch caliper contradicted
  disjoint 120-minute forward windows.
- Amendment 01 makes cross-session matching primary and same-session matching
  a separately labelled descriptive analysis.
