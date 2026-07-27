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
- Recomputed all five declared development partitions with dataset hashes
  derived from the ingested bytes, after finding the prior 2021 and 2023
  registry hashes did not match their archives (F-05). Both recomputations
  reproduced the voided row counts exactly, so the earlier computation was
  sound and only its recorded identity was wrong.
- Completed 2025 for the first time, after a streaming ledger writer replaced a
  path that held four full copies of each ledger and exhausted memory.
- First aggregation under the Amendment 01 matching rule produced 42 primary
  cross-session pairs and `UNDERPOWERED` for every gate and relationship.
  Exact `zone_width_bins` equality fragmented 3,235 treated events into 3,092
  strata (F-07).
- Amendment 02 replaces that exact stratum with an ATR-normalized width
  caliper, a log-width distance term and post-match width balance reporting,
  and opens `STAGE_02_GENERATION_2_MATCHING`. Generation 1 is preserved.
- Corrected an aggregator defect that silently excluded the declared 2019
  partition from Generation 1 (D-016).

## Stage 2 Generation 4 — 2026-07-27

- Stopped the Generation 3 partition sweep before 2021, 2023, 2025 or partial
  2026 was run under the one-tick atomic definition. No later Generation 3
  partition was ever accepted, and the interrupted launch never started, so
  there were no incomplete outputs to quarantine.
- Reclassified the accepted Generation 3 2019 checkpoint as
  `COMPUTATIONALLY_VALID_BUT_NOT_A_VALID_TEST_OF_THE_INTENDED_HVN_ZONE_HYPOTHESIS`
  on structural grounds: median accepted node width 0.25 points, most nodes one
  NQ tick wide. The checkpoint, its ledgers and its audit are preserved
  unchanged (D-G4-001).
- Opened `STAGE_02_GENERATION_4_HVN_ZONES`, replacing atomic price points with
  causally frozen, smoothed, multi-bin high-volume/high-occupancy zones.
- Locked six Generation 4 specifications before any empirical execution:
  charter, zone spec, outcome spec, control spec, statistics spec and gate.
  The zone spec fixes the triangular smoothing bandwidth, the 95th-percentile
  and 1.50 peak gates, the 70% core expansion, the four-tick / 0.10 ATR minimum
  width, the 0.75 ATR maximum, the zone density and peak-to-valley requirements,
  the adjacent-peak resolution, the POC zone, physical-zone deduplication, the
  rejection ordering and structural conditions G4-S01 through G4-S19.
- Recorded that Generation 4 is the final authorized structural definition for
  this development study, and that no Generation 4 threshold may be revised
  after its forward outcomes are opened.
- No Generation 4 code, pilot or outcome exists yet; no forward outcome has been
  computed or opened.
- Implemented the smoothed-zone detector (`src/hvn/zones_v4.py`, 22 fixtures) and
  the structural pilot runner, and ran the 2019 structural-only pilot into
  `outputs/stage_02_generation_4_hvn_zones_pilot/`. All 17 artifacts are
  byte-identical on an independent rerun.
- Found and corrected one implementation defect before acceptance: the POC width
  ceiling was clamped upward to the minimum zone width, admitting POC zones up to
  1.80 ATR wide and failing G4-S05. Corrected in `72e6777` with a regression
  fixture; the pilot was rerun from scratch.
- Structural conditions G4-S01 through G4-S14 and G4-S17 through G4-S19 pass.
  **G4-S15 and G4-S16 fail**: six unique non-POC zones exist in 2019 against a
  required 300, and no relationship reaches the required 20 opportunities.
- Diagnosed the cause as a width-band collapse at this project's ATR scale, not a
  sample accident. The frozen ATR is a one-minute Wilder ATR with a 2019 median
  of 1.924 points, so the four-tick absolute floor binds everywhere and is itself
  a median 0.52 ATR minimum width against a 0.75 ATR maximum. In 197 of 895
  profiles the ceiling falls below the floor. 85% of POC candidates exceed their
  ceiling and become broad distributions, whose span then vetoes 729 non-POC
  candidates.
- Stopped before the outcome study: automatic continuation is conditional on all
  structural conditions passing, and the cause is a specification contradiction
  whose resolution is the principal's decision. No threshold was retuned and no
  further detector generation was created.
