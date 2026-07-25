# Stage 2 Generation 2 Completion Report

```text
STAGE_02_GENERATION_1_MATCHING = UNDERPOWERED   (preserved, outputs/stage_02/)
STAGE_02_GENERATION_2_MATCHING = UNDERPOWERED
```

Generation 2 increased primary pairs from 42 to 876 and achieved excellent
post-match width balance, but every relationship still fails G01's requirement
of at least 20 matched pairs in at least three development years. No gate
advanced. This is a statement about sample support, **not** about the HVN
hypothesis, which remains untested.

## Provenance

| Field | Value |
|---|---|
| Branch | `stage-02-recompute` |
| Amendment | `STAGE_02_AMENDMENT_02` |
| Reproduction | `PYTHONPATH=src python3 scripts/aggregate_stage_02.py --generation generation_2 --amendment amendment_02 --input-root outputs/stage_02/detailed --output-root outputs/stage_02_generation_2` |

Input partitions, pinned in `STAGE_02_GENERATION_2_MANIFEST.json`:

| year | HVN events | dataset sha256 | producing code sha |
|---|---|---|---|
| 2019 | 2,898 | `910fcd9faf31…` | `cd327bf9` |
| 2021 | 3,388 | `0336cfac5fe8…` | `5b5a3de0` |
| 2023 | 3,211 | `c982860543d8…` | `754ecce7` |
| 2025 | 3,265 | `b4fcf58ff5db…` | `cd327bf9` |
| 2026 | 1,419 | `b4fcf58ff5db…` | `81dac586` |

No event-generation recomputation was performed. No market archive was read.
No 2020, 2022 or 2024 row was parsed.

## Matching eligibility, before and after

| Stratum | Treated with >= 1 eligible control |
|---|---|
| Generation 1 (exact width + year) | 35 |
| Generation 2 (width caliper + year) | 1,100 (diagnosed), 876 pairs realized |

619,655 match events were loaded: 4,111 treated and 615,544 control events with
complete covariates and all four forward horizons. 876 primary cross-session
pairs and 3,079 secondary same-session pairs were formed. 7,346 treated/family
combinations went unmatched.

## Primary pairs and match rates

| Relationship | C01 pairs | C01 rate | C02 pairs | C02 rate |
|---|---|---|---|---|
| R01 | 13 | 2.26% | 1 | 0.17% |
| R02 | 87 | 8.90% | 27 | 2.76% |
| R03 | 182 | 20.80% | 79 | 9.03% |
| R04 | 166 | 20.60% | 74 | 9.18% |
| R05 | 175 | 19.93% | 72 | 8.20% |

Control reuse is zero in every lane.

## Width control

The caliper and distance term achieved their purpose. All realized width ratios
fall inside the authorized `[0.67, 1.50]`, observed range `0.6718`–`1.4981`.

| Lane | pairs | pre-match width SMD | post-match width SMD | balanced |
|---|---|---|---|---|
| R01 C01 | 13 | 0.691 | −0.116 | yes |
| R01 C02 | 1 | 0.683 | undefined (n=1) | no |
| R02 C01 | 87 | 0.944 | 0.091 | yes |
| R02 C02 | 27 | 0.918 | 0.104 | yes |
| R03 C01 | 182 | 0.218 | −0.011 | yes |
| R03 C02 | 79 | 0.093 | −0.064 | yes |
| R04 C01 | 166 | 0.490 | 0.005 | yes |
| R04 C02 | 74 | 0.267 | −0.015 | yes |
| R05 C01 | 175 | 0.716 | 0.041 | yes |
| R05 C02 | 72 | 0.672 | 0.069 | yes |

Nine of ten lanes are far inside the 0.20 preference, from pre-match imbalance
as high as 0.944. The tenth has a single pair, so its SMD is undefined rather
than adverse. Removing the exact width stratum did not cost width balance.

## Other covariate balance

Maximum absolute post-match SMD across the six matching covariates:

| Lane | max abs SMD | material imbalance |
|---|---|---|
| R02 C01 | 0.073 | no |
| R04 C01 | 0.142 | no |
| R04 C02 | 0.160 | no |
| R03 C02 | 0.239 | yes |
| R02 C02 | 0.248 | yes |
| R03 C01 | 0.227 | yes |
| R05 C01 | 0.452 | yes |
| R05 C02 | 0.566 | yes |
| R01 C01 | 0.598 | yes |
| R01 C02 | infinite (n=1) | yes |

Six of ten lanes carry a residual imbalance above 0.20 on some covariate. Under
G07 this is an unresolved match-validity concern, reported rather than
adjusted away.

## Gates

All 40 gate rows are `UNDERPOWERED`. The binding criterion is G01: at least 100
pooled pairs **and** at least 20 pairs in at least three development years.

| Relationship | unique primary episodes | years with >= 20 pairs | G01 |
|---|---|---|---|
| R01 | 6 | 0 | UNDERPOWERED |
| R02 | 61 | 1 | UNDERPOWERED |
| R03 | 89 | 2 | UNDERPOWERED |
| R04 | 73 | 2 | UNDERPOWERED |
| R05 | 70 | 1 | UNDERPOWERED |

R03, R04 and R05 now clear the 100 pooled-pair threshold on C01, but none
reaches three years at 20 pairs. Because G01 does not pass, G02–G08 cannot
advance a relationship regardless of their individual values.

## Why the per-year requirement binds

14,181 raw definition events collapse to **3,383 unique economic episodes**,
4.19 definitions per episode — the expected consequence of the 2 method x 3
ratio x 3 prominence grid. Independent evidence is roughly a quarter of the raw
event count. Unique episodes per year, C01:

| Lane | 2019 | 2021 | 2023 | 2025 | 2026 |
|---|---|---|---|---|---|
| R01 | 0 | 5 | 1 | 0 | 0 |
| R02 | 6 | 31 | 11 | 9 | 3 |
| R03 | 18 | 15 | 23 | 25 | 8 |
| R04 | 4 | 14 | 19 | 31 | 4 |
| R05 | 15 | 22 | 15 | 9 | 9 |

Partial 2026 is roughly half a year and contributes correspondingly little.

## Grid stability

`stable_neighborhood` is false for every relationship, allocation method and
control family. Positive-cell counts and medians are mixed in sign, for example
R03 C01 uniform bar volume at 2 of 5 positive with median −0.022, and R02 C01
TPO range occupancy at 3 of 3 positive with median 0.15. No parameter
neighbourhood is stable.

## Concentration and leave-one-year-out

Base pooled effects on `inside_close_share_30` for C01 are small and mixed:
R01 −0.0181, R02 −0.0030, R03 −0.0040, R04 +0.0043, R05 +0.0343. Leave-one-year-out
means change sign for several relationships — R02 moves from −0.046 excluding
2021 to +0.042 excluding 2023 — on episode counts between 29 and 57. At these
sample sizes such swings are expected and are not evidence of an effect or of
its absence.

`REMOVE_LARGEST_1_PERCENT` and `REMOVE_TOP5_EPISODES_PER_YEAR` are computed and
recorded. For R01 the top-five-episode diagnostic has zero remaining
observations.

## Verdict

```text
IMPLEMENTATION_VALID   = YES for the matching and aggregation path exercised here
STATISTICALLY_CREDIBLE = UNDERPOWERED
ECONOMICALLY_CREDIBLE  = NOT_ASSESSED
DEPLOYMENT_READY       = NOT_ASSESSED
HVN_ACCEPTANCE_EFFECT  = UNDERPOWERED
```

Generation 2 does not support, refute, or partially support the HVN acceptance
hypothesis. G01 fails first, so no relationship reaches the gates that would
speak to the hypothesis at all.

## Known limitations

- Six of ten lanes retain a post-match covariate imbalance above 0.20 on at
  least one covariate, an unresolved G07 concern.
- R01 C02 has a single pair; its balance statistics are undefined, not adverse.
- No parameter neighbourhood is stable, so no cell would be credible for
  selection even with adequate samples.
- The width caliper is implemented as the literal ratio bound and is therefore
  slightly asymmetric in the treated/control roles.
- The log-width distance term is correctly rounded rather than exact; ties
  break on control event id, so matching stays deterministic.
- Generation 1 aggregated four partitions and Generation 2 five, so their pair
  counts are not directly comparable.
- Effect magnitudes are reported for completeness only. With G01 failing they
  carry no inferential weight and must not be read as evidence of direction.

## Reproducibility

The full Generation 2 aggregation was executed twice. All thirteen CSV
artifacts, including `gate_results.csv`, `paired_primary_results.csv` and
`width_balance.csv`, were byte-identical between runs.

## Exact next authorized action

Stop. Report to Dylan and await an explicit decision on whether to seek a
further amendment, extend the development sample, or conclude Stage 2 as
underpowered. No further stratum may be dropped without new authorization.
Stage 3, departure, MFE/MAE, grading, strategy, validation, holdout and
execution work remain unauthorized.
