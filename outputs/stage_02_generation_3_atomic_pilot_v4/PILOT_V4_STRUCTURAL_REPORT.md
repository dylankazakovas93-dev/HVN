# Generation 3 Pilot V4 — Structural Report

```text
GENERATION_3_PILOT_V1 = REJECTED_STRUCTURAL_DEFINITION
GENERATION_3_PILOT_V2 = STRUCTURALLY_VALID_BUT_SUPERSEDED_BEFORE_OUTCOME_ANALYSIS
GENERATION_3_PILOT_V3 = STRUCTURALLY_VALID_BUT_SUPERSEDED_BEFORE_OUTCOME_ANALYSIS
GENERATION_3_PILOT_V4_GLOBAL_AND_LOCAL = STRUCTURALLY ACCEPTED — FINAL DETECTOR
```

Mode: structural-only. No forward outcome was computed, loaded or inspected.
Scope: **2019 only**. The four other development partitions are untouched.

## Provenance

| Field | Value |
|---|---|
| Year | 2019 |
| Archive | `nq2018.zip`, member `glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst` |
| Dataset sha256 | `910fcd9faf31ea1a9a485398e6771e9e44eb3314f0ebbff84ed40b6bf2545203` |
| Code sha | `5c08da5640f534f3487097c8c360f3aa3e25edf0` |
| Bars | 430,528 |
| Reproduction | `PYTHONPATH=src python3 scripts/run_atomic_pilot_v4.py --year 2019 --data-root <data-root> --structural-only` |

## Hard conditions S01-S25

| ID | Result |
|---|---|
| S01 profiles = 6,852 | **PASS** |
| S02 Stage 1 universe unchanged | **PASS** — multiset identical to Generation 1 |
| S03/S17 width 1-5 | **PASS** — observed 1-5 |
| S04 non-POC meets all frozen floors | **PASS** |
| S05/S06 POC recorded and classified | **PASS** — 3,422 `POC_ATOMIC`, 4 `POC_BROAD` |
| S07 volume value area | **PASS** — 3,426/3,426 |
| S08 TPO value area | **PASS** — 3,426/3,426 |
| S09 no post-freeze data | **PASS** |
| S10/S18 ledgers reconcile | **PASS** — 116,114 = 8,594 + 107,520 |
| S11 deterministic rerun | **PASS** — all 18 artifacts byte-identical |
| S12 no forbidden year | **PASS** — year 2019 only |
| S13 no forward outcome | **PASS** — no forward module; manifest flag false |
| S14 POC population unchanged from V3 | **PASS** — 3,422 accepted rows, identical |
| S15 non-POC percentile >= 90 | **PASS** — 0 violations |
| S16 non-POC prominence >= 1.10 | **PASS** — 0 violations |
| S17 no individual volume/TPO prominence veto | **PASS** |
| S19 no zone double-counted | **PASS** — max 1 per (profile, relationship, span) |
| S20 controls frozen-only | **PASS** — 17,188 controls, 0 overlapping an accepted node |
| **S21** >= 200 unique non-POC | **PASS** — 4,072 |
| **S22** non-POC >= 5% | **PASS** — 60.3% |
| **S23** >= 10 per relationship | **PASS** — R01 1,100, R02 1,100, R03 1,213, R04 901, R05 858 |
| **S24** median non-POC per host profile <= 5 | **PASS** — median 1 |
| **S25** non-POC share <= 80% | **PASS** — 60.3% |

## Population across the three composite pilots

| | V2 | V3 | **V4** |
|---|---|---|---|
| unique non-POC | 43 | 28,489 | **4,072** |
| unique POC | 2,681 | 2,681 | **2,681** |
| non-POC share | 1.6% | 91.4% | **60.3%** |
| non-POC per host profile, median | - | ~8 | **1** |
| accepted rows | 10,395 | 42,105 | **8,594** |

Per-host-profile distribution over the 2,685 volume profiles that host nodes:
mean 1.52, median 1, p75 2, p90 4, max 12. 845 of 2,685 host profiles contain
no non-POC node at all.

S21-S23 and S24-S25 constrain in opposite directions and the frozen thresholds
landed between them without adjustment.

## Rejections

| reason | count |
|---|---|
| `ZONE_VOLUME_DENSITY_TOO_LOW` | 55,523 |
| `ACTIVITY_PERCENTILE_TOO_LOW` | 19,546 |
| `PEAK_VOLUME_DENSITY_TOO_LOW` | 15,323 |
| `LOCAL_ACTIVITY_PROMINENCE_TOO_LOW` | 13,965 |
| `WIDTH_TOO_LARGE` | 2,114 |
| `ZONE_TPO_DENSITY_TOO_LOW` | 522 |
| `COMPOSITE_ACTIVITY_TOO_LOW` | 382 |
| `OVERLAPS_VOLUME_POC` | 145 |

The two Amendment 03 gates removed 33,511 nodes that Pilot V3 accepted.

## Correction to the first audit pass

An initial S24 computation reported a median of 0.0. That divided by all 6,852
profile rows, including the 3,426 TPO profiles that cannot host a node. Against
the 2,685 volume profiles that do host nodes, the median is **1** and the mean
1.52. Both pass, but the correct figure is 1.

## Limitations carried forward

- These counts are **2019 only**. S21-S25 passing here does not guarantee they
  hold in 2021, 2023, 2025 or partial 2026; node density depends on profile
  shape and will be reported per partition.
- POC nodes bypass both Amendment 03 gates by design, so POC and non-POC
  populations are qualified by different rules and are never pooled.
- The activity percentile uses a ties-share-lowest convention and can be
  conservative in thin profiles with heavy integer tying.
