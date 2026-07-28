# Generation 4 Structural Pilot — 2019, under Amendment 01

Mode: **structural only**. No forward outcome was computed, loaded, written or
inspected. Verdict: **NOT ACCEPTED AS SPECIFIED — G4-S15 and G4-S16 fail**, but
by a margin two orders smaller than the pre-amendment run. Every mechanical and
causal condition passes and the population is now healthy.

The pre-amendment pilot at `outputs/stage_02_generation_4_hvn_zones_pilot/` is
preserved unchanged.

## 1. Provenance

```text
partition            2019 (development)
archive              nq2018.zip
dataset sha256       910fcd9faf31ea1a9a485398e6771e9e44eb3314f0ebbff84ed40b6bf2545203
producing code sha   3a2fc20
specification        STAGE_02_GENERATION_4_ZONE_SPEC.md + AMENDMENT_01
rows admitted        430,528   (481,125 excluded as 2018; 0 forbidden-year rows)
```

## 2. What the amendment changed

| | before | after |
|---|---|---|
| unique non-POC zones | 6 | **248** |
| accepted zones total | 129 | **1,139** |
| accepted POC zones | 123 | **891** |
| POC broad distributions | 762 | **1** |
| relationship opportunities | 174 | **1,468** |
| non-POC opportunities | 9 | **331** |

The POC broad-distribution count collapsing from 762 to 1 is the clearest sign
the scale contradiction is gone: under the old ceiling 85% of POC zones were
too wide to be a zone at all.

## 3. Widths

```text
non-POC   n=248   median 12.5 ticks   p90 19   max 28   median 1.19 ATR
POC       n=891   median 12   ticks   p90 18   max 30   median 1.62 ATR
```

A median zone is about 3 points wide — roughly one and a half one-minute bar
ranges, and about 5% of a typical RTH profile range. It is a localized region,
not the value area, and it is not a single tick.

## 4. Conditions

All mechanical and causal conditions pass:

```text
G4-S01 PASS  895 tick profiles reconcile exactly with the Generation 3
             (family, session_date, contract) source-profile universe
G4-S02 PASS  minimum accepted width 3 ticks
G4-S03 PASS  0 accepted zones below the ATR minimum and the tick floor
G4-S04 PASS  maximum accepted non-POC width 1.4992 ATR
G4-S05 PASS  maximum accepted POC width 2.4832 ATR
G4-S06 PASS  0 overlapping accepted pairs
G4-S07 PASS  0 accepted non-POC zones failing a gate
G4-S08 PASS  0 profiles frozen after their interaction session
G4-S09 PASS  14,780 candidates = 1,139 accepted + 13,641 rejected
G4-S10 PASS  all 17 artifacts byte-identical on an independent rerun
G4-S11 PASS  0 forbidden-year rows admitted
G4-S12 PASS  manifest forward_outcomes_computed = false
```

Sample support:

```text
G4-S13 PASS  median accepted non-POC zones per valid profile = 0
G4-S14 PASS  90th percentile accepted non-POC zones per profile = 1
G4-S15 FAIL  248 unique non-POC zones against a required 300
G4-S16 FAIL  R01=83  R02=83  R03=95  R04=16  R05=54  against a required 20 each
G4-S17 PASS  median accepted zone width 1.4597 ATR
G4-S18 PASS  median accepted zone width 12 ticks
G4-S19 PASS  95th-percentile accepted non-POC width 1.4595 ATR
```

G4-S13 and G4-S14 are now informative rather than vacuous: the detector produces
about one non-POC zone per profile at the 90th percentile, which is a sane
population rather than an empty one.

## 5. What still fails, and why

**G4-S15** misses by 52 zones on a 300 threshold. **G4-S16** passes for four of
five relationships; only R04 (`midnight` profile family) is thin at 16.

Both are **sample-support** gates — thresholds on whether 2019 alone carries
enough zones to run a study — not thresholds inside the detector. The detector's
own gates (percentile, peak activity, densities, separation, width) all pass on
every accepted zone.

Rejections by first-failure reason:

```text
PEAK_PERCENTILE_TOO_LOW         11,397
OVERLAPS_VOLUME_POC                851
PEAK_TO_VALLEY_TOO_LOW             787
NO_VALID_BASIN_SEPARATION          359
WIDTH_EXCEEDS_MAXIMUM              191
BASIN_TOO_NARROW                    34
PEAK_ACTIVITY_TOO_LOW               15
ZONE_VOLUME_DENSITY_TOO_LOW          5
ZONE_ACTIVITY_DENSITY_TOO_LOW        2
```

The percentile gate remains the dominant filter at 77% of candidates. The second
constraint is the POC veto: with POC zones now correctly sized, 851 non-POC
candidates fall inside one and are excluded by rule.

## 6. Discipline

No constant was swept. Amendment 01's values were derived from the diagnosed
scale contradiction and from the data's resolution, then run against 2019
**once**. This report records the result of that single run, including its
failures, rather than a search for values that clear a gate.

The next step is a principal decision on whether 248 zones and a thin R04 lane
are sufficient to proceed. No Generation 4 forward outcome has been computed.
