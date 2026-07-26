# Generation 3 Pilot V2 — Structural Report

```text
GENERATION_3_PILOT_V1 = REJECTED_STRUCTURAL_DEFINITION
GENERATION_3_PILOT_V2_SESSION_NORMALIZED = STRUCTURALLY ACCEPTED
```

Mode: structural-only. No forward proximity, residence, departure or excursion
value was computed, loaded or written.

## Provenance

| Field | Value |
|---|---|
| Year | 2019 |
| Archive | `nq2018.zip`, member `glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst` |
| Dataset sha256 | `910fcd9faf31ea1a9a485398e6771e9e44eb3314f0ebbff84ed40b6bf2545203` |
| Code sha | `0a247034f6512db7fa15a5a1f94790d1b208c3e7` |
| Bars | 430,528 |
| Reproduction | `PYTHONPATH=src python3 scripts/run_atomic_pilot_v2.py --year 2019 --data-root <data-root> --structural-only` |

## Hard acceptance conditions

| ID | Condition | Result |
|---|---|---|
| S01 | profile count = 6,852 | **PASS** — 6,852, split 3,426 volume / 3,426 TPO |
| S02 | Stage 1 construction unchanged | **PASS** — identical `(profile_id, method, ratio)` multiset vs Generation 1 |
| S03 | every atomic node 1-5 bins | **PASS** — observed 1-4 |
| S04 | every non-POC node meets all frozen thresholds | **PASS** — 0 violations |
| S05 | every profile has a deterministic volume POC | **PASS** — 3,426 of 3,426 profile pairs |
| S06 | every POC classified | **PASS** — `POC_ATOMIC` 3,422, `POC_BROAD` 4 |
| S07 | volume VA contiguous, contains POC, >= 70% | **PASS** — 3,426/3,426, none below 70% |
| S08 | TPO VA contiguous, contains TPO POC, >= 70% | **PASS** — 3,426/3,426, none below 70% |
| S09 | no post-freeze information | **PASS** — detector references no forward identifier |
| S10 | ledgers reconcile | **PASS** — 388,854 candidates = 10,395 accepted + 378,459 rejected |
| S11 | deterministic rerun | **PASS** — all 13 artifacts byte-identical |
| S12 | no forbidden year | **PASS** — accepted nodes carry year 2019 only |
| S13 | no forward outcome inspected | **PASS** — no forward module imported, manifest `forward_outcomes_computed: false` |

## Node counts

388,854 candidates, **10,395 accepted**, 378,459 rejected.

Accepted rows repeat across the three prominence thresholds. Collapsing to
unique `(profile, start bin, class)`:

| class | unique nodes | accepted rows |
|---|---|---|
| `POC_ATOMIC` | **2,681** | 10,266 |
| `NONPOC_ATOMIC_HVN` | **43** | 129 |

Geometry: 10,224 one-bin maxima, 171 flat-top plateaus. Widths 1 bin (10,224),
2 (96), 3 (45), 4 (30). No accepted node reaches 5 bins.

`POC_BROAD`: 4 profiles. Broad plateaus excluded by width: 3,420 candidates.

## Rejection reasons

| reason | count |
|---|---|
| `VOLUME_DENSITY_TOO_LOW` | 250,263 |
| `LOCAL_PROMINENCE_TOO_LOW` | 115,797 |
| `TPO_DENSITY_TOO_LOW` | 5,799 |
| `WIDTH_TOO_LARGE` | 3,420 |
| `VOLUME_PERCENTILE_TOO_LOW` | 3,180 |

The session-normalized volume floor is the dominant filter, which is the
intended correction: it is exactly the condition V1 lacked.

## Accepted-node distributions

| metric | min | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|
| volume density ratio | 1.56 | 2.34 | 2.69 | 3.21 | 3.90 | 8.87 |
| TPO density ratio | 0.98 | 2.29 | 2.81 | 3.39 | 4.13 | 9.44 |
| volume percentile | 0.88 | 0.99 | 0.99 | 1.00 | 1.00 | 1.00 |
| local prominence | 1.00 | 1.07 | 1.11 | 1.15 | 1.21 | 3.73 |
| zone width (ATR) | 0.04 | 0.11 | 0.15 | 0.21 | 0.26 | 0.89 |

Zone width in points: min 0.25, median 0.25, max 2.00 — one to eight ticks.
Compare Pilot V1, whose widest zone spanned 51 bins and 6.10 ATR.

The median accepted local prominence of 1.11 sits below the 1.50 non-POC
threshold because 98.8% of accepted nodes are POC nodes, which are exempt. TPO
density minimum 0.98 is below the 1.25 floor for the same reason.

## Value-area location (annotation only)

| | inside | outside |
|---|---|---|
| volume value area | 10,374 | 21 |
| TPO value area | 9,672 | 723 |

No node was excluded for its location.

## By relationship

| relationship | `POC_ATOMIC` | `NONPOC_ATOMIC_HVN` |
|---|---|---|
| R01 | 2,223 | **0** |
| R02 | 2,223 | **0** |
| R03 | 1,593 | 87 |
| R04 | 2,016 | 36 |
| R05 | 2,211 | 6 |

## The dominant structural limitation

**98.8% of accepted nodes are the profile POC.** Only 43 unique non-POC atomic
nodes exist in a full development year, and R01 and R02 have none at all.

Under the frozen thresholds, Generation 3 is therefore in practice a study of
**POC behaviour**, not of non-POC high-volume nodes. The non-POC class will
almost certainly be underpowered for every relationship, and empty for two of
them, before any outcome is measured.

This is reported, not acted upon. The thresholds were supplied by
authorization, no alternative was evaluated, and adjusting them now — after
seeing structural counts — would be threshold tuning. The acceptance conditions
contain no minimum node count, and none was invented. Whether 43 non-POC nodes
per year is a usable sample is a research decision for Dylan, informed by the
five-partition counts rather than by this single year.

## Notes

- V1's two failure modes are corrected. Sparse tail structure is now removed by
  the volume-density floor (250,263 rejections), and dense peaks with heavy
  neighbours survive via the POC prominence exemption — the median accepted POC
  prominence is 1.11, which V1 would have rejected outright.
- One earlier V2 run was stopped: it recorded 3,426 profile rows because the
  ledger collapsed the two allocation methods into one row per ratio, failing
  S01. The construction was never wrong; the ledger under-counted it. Recorded
  in the run registry and superseded by this run.
