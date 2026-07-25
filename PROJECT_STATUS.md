# Project Status

Status: **STAGE_02 GENERATION 2 MATCHING — AMENDMENT 02 AUTHORIZED**

```text
STAGE_02_GENERATION_1_MATCHING = UNDERPOWERED
```

That label describes the Generation 1 matching design. It is **not** a verdict
on the HVN hypothesis, which Generation 1 could not test.

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
