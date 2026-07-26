# Generation 3 Pilot V3 — Structural Report

```text
GENERATION_3_PILOT_V1 = REJECTED_STRUCTURAL_DEFINITION
GENERATION_3_PILOT_V2 = STRUCTURALLY_VALID_BUT_SUPERSEDED_BEFORE_OUTCOME_ANALYSIS
GENERATION_3_PILOT_V3_COMPOSITE_ACTIVITY = STRUCTURALLY ACCEPTED
```

Mode: structural-only. No forward proximity, residence, departure or excursion
value was computed, loaded or inspected.

## Provenance

| Field | Value |
|---|---|
| Year | 2019 |
| Archive | `nq2018.zip`, member `glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst` |
| Dataset sha256 | `910fcd9faf31ea1a9a485398e6771e9e44eb3314f0ebbff84ed40b6bf2545203` |
| Code sha | `d02e251e04840cd2610c35405c0dcd0be0599782` |
| Bars | 430,528 |
| Reproduction | `PYTHONPATH=src python3 scripts/run_atomic_pilot_v3.py --year 2019 --data-root <data-root> --structural-only` |

## Hard conditions

| ID | Condition | Result |
|---|---|---|
| S01 | profiles = 6,852 | **PASS** |
| S02 | Stage 1 universe unchanged | **PASS** — `(profile_id, method, ratio)` multiset identical to Generation 1 |
| S03/S17 | node width 1-5 bins | **PASS** — observed 1-5 |
| S04/S14 | non-POC meets all fixed floors | **PASS** — 0 violations of 38,683 |
| S05/S06 | POC recorded and classified | **PASS** — 3,422 `POC_ATOMIC`, 4 `POC_BROAD` |
| S07 | volume value area | **PASS** — 3,426/3,426 contiguous, POC inside, >= 70% |
| S08 | TPO value area | **PASS** — 3,426/3,426 |
| S09 | no post-freeze information | **PASS** |
| S10/S18 | ledgers reconcile | **PASS** — 116,114 = 42,105 + 74,009 |
| S11 | deterministic rerun | **PASS** — all 17 artifacts byte-identical |
| S12 | no forbidden year | **PASS** — year 2019 only |
| S13 | no forward outcome | **PASS** — no forward module imported; manifest flag false |
| S15 | prominence/percentile never gate | **PASS** — absent from every rejection reason and from `_rejection_reason` |
| S16 | non-POC are genuine composite maxima | **PASS** — 36,492 one-bin, 2,191 flat-top |
| S19 | no physical zone double-counted | **PASS** — max 1 per `(profile, relationship, span)`; no POC/non-POC collision |
| S20 | controls use frozen features only | **PASS** — no forward identifier in the selection code |
| **S21** | >= 200 unique non-POC | **PASS** — **28,489** |
| **S22** | non-POC >= 5% of unique accepted | **PASS** — **91.4%** |
| **S23** | >= 10 unique non-POC per relationship | **PASS** — R01 10,194, R02 10,194, R03 6,815, R04 7,143, R05 4,337 |

## Non-POC sample growth

| | Pilot V2 | Pilot V3 |
|---|---|---|
| unique `NONPOC_ATOMIC_HVN` | 43 | **28,489** |
| unique `POC_ATOMIC` | 2,681 | 2,681 |
| non-POC share of unique accepted | 1.6% | **91.4%** |
| relationships with zero non-POC | R01, R02 | none |

The POC population is unchanged, as intended: Amendment 02 altered only the
non-POC rules.

## Counts

116,114 candidates, 42,105 accepted, 74,009 rejected. Accepted rows: 3,422
`POC_ATOMIC`, 38,683 `NONPOC_ATOMIC_HVN`.

Widths: 1 bin 39,859; 2 bins 1,546; 3 bins 468; 4 bins 158; 5 bins 74.

Rejections: `ZONE_VOLUME_DENSITY_TOO_LOW` 55,523; `PEAK_VOLUME_DENSITY_TOO_LOW`
15,323; `WIDTH_TOO_LARGE` 2,114; `ZONE_TPO_DENSITY_TOO_LOW` 522;
`COMPOSITE_ACTIVITY_TOO_LOW` 382; `OVERLAPS_VOLUME_POC` 145. No rejection cites
prominence or percentile.

## Accepted non-POC distributions

| metric | min | p25 | median | p75 | max |
|---|---|---|---|---|---|
| zone volume density | 1.50 | 1.71 | 1.95 | 2.33 | 8.23 |
| zone TPO density | 1.00 | 1.71 | 2.04 | 2.50 | 9.25 |
| composite activity | 1.35 | 1.72 | 1.99 | 2.39 | 8.10 |
| peak volume density | 1.50 | 1.71 | 1.95 | 2.33 | 8.23 |
| local volume prominence | 0.78 | 1.04 | **1.07** | 1.11 | 2.81 |
| zone width (ATR) | 0.04 | 0.10 | 0.14 | 0.20 | 1.43 |

The median accepted local prominence of **1.07** is the amendment working as
designed: these are prices carrying roughly twice the profile's average volume
and time, embedded among neighbours of similar activity. Under Amendment 01's
1.50 prominence veto essentially none of them could qualify.

A minimum prominence of 0.78 means some accepted nodes sit slightly *below*
their neighbourhood median while still being composite local maxima and
clearing every density floor. That is permitted by Amendment 02 and is recorded
rather than filtered.

## Value-area location (annotation only)

| | inside | outside |
|---|---|---|
| volume value area | 33,542 | 5,141 |
| TPO value area | 32,843 | 5,840 |

## Non-POC by profile family

`prior_rth` 20,388 (R01 and R02 share it); `midnight` 7,143;
`full_overnight` 6,815; `opening_hour_rth` 4,337.

## Controls

84,210 control zones: 42,105 `C01_NEUTRAL` and 42,105 `C02_ACTIVITY_MATCHED`,
one pair per accepted node, width-matched (79,718 one-bin, 3,092 two-bin, 936
three-bin, 316 four-bin, 148 five-bin).

## Defects found and corrected during this pilot

- **`control_summary.csv` contained rejection reasons, not controls.** The
  mislabelled call was inherited from the accepted V2 runner, and no controls
  were being constructed at all, leaving S20 untestable and a required artifact
  silently wrong. Controls are now implemented, rejection counts moved to
  `rejection_summary.csv`, and the missing `node_class_summary.csv` and
  `prominence_summary.csv` added. The pilot was rerun.
- An initial S19 check reported duplicate spans. Investigation showed the check
  was too crude: R01 and R02 legitimately share the prior-RTH profile, exactly
  as Generation 1 does. Keyed by `(profile, relationship, span)` the maximum is
  1, and no POC and non-POC pair shares a span.

## Structural limitation to carry into the sweep

The population has moved from 98.8% POC under V2 to **91.4% non-POC** under V3,
about eight accepted non-POC nodes per profile. The floors are modest by
construction — a zone volume density of 1.25 is 25% above the profile's own
average — so an accepted node denotes a common local concentration rather than
a rare standout.

This is not an acceptance failure. S21-S23 are the specified sample-support
conditions and they pass, and no discretionary "too permissive" condition was
invented. It does shape interpretation: with this many nodes per profile,
economic-episode clustering and control matching carry more weight than usual,
and any result must be read as a statement about common local concentrations,
not about rare structural features.
