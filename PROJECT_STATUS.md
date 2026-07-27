# Project Status

Status: **STAGE_02 GENERATION 4 HVN ZONES — STRUCTURAL PILOT RUN AND NOT ACCEPTED**

```text
STAGE_02_GENERATION_1_MATCHING = UNDERPOWERED
STAGE_02_GENERATION_3_2019     = COMPUTATIONALLY_VALID_BUT_NOT_A_VALID_TEST_OF_THE_INTENDED_HVN_ZONE_HYPOTHESIS
STAGE_02_GENERATION_4          = STRUCTURAL_PILOT_NOT_ACCEPTED (G4-S15, G4-S16 fail)
```

The Generation 1 label describes the Generation 1 matching design. It is **not**
a verdict on the HVN hypothesis, which Generation 1 could not test.

## Generation 3 (`outputs/stage_02_generation_3_final/`, `_atomic`, pilots V2-V4)

The atomic detector and its accepted 2019 outcome checkpoint are preserved in
full and remain computationally valid for the one-tick object they measured.
Median accepted node width was 0.25 points, so `inside_close_share` measured
whether a future one-minute close landed on essentially one exact tick. That is
not the intended HVN zone, so the checkpoint is reclassified as above and is not
cited as evidence about HVN zones in either direction.

The remaining partition sweep is stopped: 2021, 2023, 2025 and partial 2026 were
never run under the one-tick definition, and no later Generation 3 partition was
ever accepted. See D-G4-001.

## Generation 4 (`STAGE_02_GENERATION_4_HVN_ZONES`)

Generation 4 replaces atomic price points with causally frozen, smoothed,
multi-bin high-volume/high-occupancy zones. Six specifications are locked before
any empirical execution: charter, zone spec, outcome spec, control spec,
statistics spec and gate. No zone may be one tick wide
(`minimum_zone_width_ticks = max(4, ceil(0.10 ATR / 0.25))`).

The detector (`src/hvn/zones_v4.py`) and the 2019 structural pilot are complete.
Mechanical and causal conditions G4-S01 through G4-S12 all pass, all 17 artifacts
are byte-identical on an independent rerun, and zero forbidden-year rows were
admitted. **G4-S15 and G4-S16 fail**: six unique non-POC zones exist in 2019
against a required 300, and no relationship reaches its required 20
opportunities.

The cause is a width-band collapse at this project's ATR scale, not a sample
accident. The frozen ATR is a one-minute Wilder ATR with a 2019 median of 1.924
points, so the four-tick absolute floor binds everywhere and is itself a median
0.52 ATR minimum width against a 0.75 ATR maximum; in 197 of 895 profiles the
ceiling falls below the floor. See
`outputs/stage_02_generation_4_hvn_zones_pilot/GENERATION_4_STRUCTURAL_REPORT.md`.

The outcome study did not begin: automatic continuation is conditional on all
structural conditions passing. No Generation 4 forward outcome has been computed
or opened, no threshold was retuned and no further detector generation was
created.

Next authorized action: a principal decision on how to resolve the width-band
contradiction.

## Development partitions

All five declared development partitions are complete, each carrying a dataset
sha256 computed from the bytes actually ingested:

| partition | bars | profiles | HVN events | control events | metric rows |
|---|---|---|---|---|---|
| 2019 | 430,528 | 6,852 | 2,898 | 127,463 | 521,444 |
| 2021 | 454,877 | 7,278 | 3,388 | 201,994 | 821,528 |
| 2023 | 456,312 | 7,176 | 3,211 | 207,662 | 843,492 |
| 2025 | 456,913 | 7,242 | 3,265 | 284,838 | 1,152,412 |
| partial 2026 | 199,294 | 3,156 | 1,419 | 102,161 | 414,320 |

No 2020, 2022 or 2024 market row has been parsed at any stage.

## Generation 1 (preserved, `outputs/stage_02/`)

42 primary cross-session pairs; G01–G08 `UNDERPOWERED` for R01–R05. Aggregated
over four partitions, because 2019 was omitted by an implementation defect
(D-016). Retained unchanged as the authoritative result of the Amendment 01
matching rule.

## Generation 2 (`outputs/stage_02_generation_2/`)

Amendment 02 replaces exact `zone_width_bins` equality with an ATR-normalized
width caliper, a log-width distance term and post-match width balance
reporting. Year, approach side, relationship, allocation method, bin ratio,
prominence threshold and control family remain exact strata. All Amendment 01
calipers are retained. All five partitions are aggregated.

## Earlier stages

Implemented: one generic immutable profile constructor for four families;
uniform bar-volume and TPO/range-occupancy proxies; ATR(24) reference freezing
and 0.05/0.10/0.20 ratios; deterministic binning, POC, local prominence,
plateaus, boundaries, and touching/overlapping node merges; source-row lineage
and byte-stable profile ledgers; independent oracle and real NQ numerical
reconciliation; deterministic unit and integration tests.

Authoritative profile/signal market is NQ. Eventual execution market is MNQ,
not yet tested. Source roll methodology remains unknown.

Stage 1B evidence:

- 6/6 independent oracle fixtures match production;
- 16/16 real NQ profiles reconcile;
- exact uniform total: 1,598,303 source and allocated units;
- exact TPO total: 57,260 expected and actual intersections;
- all production bins independently equal;
- all post-freeze hashes equal;
- all revised gate criteria pass.

## Findings

- F-05 fabricated dataset hashes in the pre-recomputation registry
- F-06 ledger digests embed the producing code SHA
- F-07 Generation 1 primary matching structurally underpowered
