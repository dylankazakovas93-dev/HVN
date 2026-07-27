# Generation 4 — HVN Zone Construction Specification

Status: **LOCKED BEFORE ANY GENERATION 4 OUTCOME WAS OBSERVED**

Every threshold below is frozen. None may be revised after any Generation 4
forward outcome is opened, and no Generation 3 outcome may inform any of them.

## 1. Source profiles and relationships

Unchanged from the locked project definitions: source-profile windows Prior
RTH, Full overnight, Midnight-to-open and Opening hour; relationships R01-R05.
Only bars whose close time is no later than the profile freeze time contribute.

## 2. Raw tick-grid profile

Tick size `0.25` points. All calculations are on the tick grid.

For each completed one-minute bar in the source window:

1. determine every NQ tick occupied by `[bar_low, bar_high]`;
2. allocate the bar's volume **uniformly** across those occupied ticks;
3. add **one TPO occupancy to every occupied tick**.

Per tick `i`:

```text
volume_density_i = allocated_volume_i / mean allocated volume across positive-volume ticks
tpo_density_i    = tpo_count_i       / mean TPO count across positive-TPO ticks
activity_density_i = sqrt(volume_density_i * tpo_density_i)
```

Raw volume, TPO and composite activity profiles are all retained in the
structural ledger.

## 3. Smoothing

A deterministic triangular kernel over the composite activity profile.

```text
smoothing_half_width_ticks = max(2, round_half_up(0.05 * frozen_profile_ATR / 0.25))
```

so the full span is approximately `0.10 ATR`. Triangular weights, centre
outward:

```text
centre            = h + 1
one tick out      = h
...
outermost         = 1
```

normalized to sum to one. At profile edges only available bins are used and the
remaining weights are renormalized.

Recorded: `raw_activity_density`, `smoothed_activity_density`,
`smoothing_half_width_ticks`, `smoothing_span_points`, `smoothing_span_atr`.

**One frozen bandwidth.** No competing primary smoothing definitions, and no
bandwidth chosen after viewing outcomes.

## 4. Peak candidates

A non-POC candidate peak must satisfy all of:

1. a local maximum, or deterministic flat-top maximum, in the **smoothed**
   composite activity profile;
2. `smoothed_activity_percentile >= 95.0` among active ticks of that completed
   profile;
3. `peak_smoothed_activity_density >= 1.50`;
4. no overlap with the volume POC peak or its eventual POC zone.

A candidate plateau is the maximal contiguous group of equal smoothed maxima
under the frozen decimal precision. Percentile convention: ties share the lowest
percentile of their group, on a 0-100 scale, over active ticks. No future bars.

## 5. Local basin

From each candidate peak, search left and right until the first of:

1. a local minimum in the smoothed activity profile;
2. `smoothed_activity_density <= 1.00`;
3. the valid profile boundary;
4. distance from the peak exceeds `1.00 * frozen_profile_ATR`.

The interval is the candidate basin. Nearby peaks are separated by the lowest
smoothed-activity valley between them. Two final zones may never overlap.

## 6. Zone core

Initialise with the peak or tied peak plateau. Expand contiguously while the
adjacent tick satisfies:

```text
smoothed_activity_density >= max(1.00, 0.70 * peak_smoothed_activity_density)
```

When both sides qualify, add the side with greater smoothed activity first;
exact ties add the **lower-price** side. This is the natural high-activity core.

No Generation 1 broad 50%-of-peak expansion. No merging of separate peaks
through a meaningful valley.

## 7. Minimum economic width

```text
minimum_zone_width_ticks = max(4, ceil(0.10 * frozen_profile_ATR / 0.25))
```

**No Generation 4 zone may be one tick wide, and none may be narrower than
1.00 NQ point.**

If the natural 70% core is narrower than the minimum, continue expanding
**inside the candidate basin**, adding the adjacent tick with higher smoothed
activity, until the minimum is reached. If the complete basin is narrower than
the minimum, reject as `BASIN_TOO_NARROW`. Width is never fabricated outside
the basin.

## 8. Maximum zone width

```text
maximum_zone_width_ticks = floor(0.75 * frozen_profile_ATR / 0.25)
```

never smaller than the minimum. A zone exceeding it is classified
`BROAD_ACTIVITY_DISTRIBUTION`, recorded structurally and excluded from primary
HVN interaction events. It is **never truncated** to the maximum.

## 9. Zone-level requirements

```text
zone_volume_density   = zone volume share / zone tick-width share of the active profile
zone_tpo_density      = zone TPO share    / zone tick-width share of the active profile
zone_activity_density = sqrt(zone_volume_density * zone_tpo_density)
```

Require:

```text
zone_volume_density   >= 1.25
zone_tpo_density      >= 1.00
zone_activity_density >= 1.35
```

Local distinctness, using the smoothed activity at the basin boundaries:

```text
reference_valley_activity = max(left_valley_activity, right_valley_activity)
peak_to_valley_ratio = peak_smoothed_activity_density / reference_valley_activity
peak_to_valley_ratio >= 1.10
```

At a valid profile edge, the available internal valley is used. With no valid
valley, reject `NO_VALID_BASIN_SEPARATION`. The Generation 3 Amendment 01
neighbourhood-median veto of 1.50 is **not** restored.

## 10. Adjacent peaks

1. sort candidates by peak smoothed activity descending;
2. accept the strongest valid zone first;
3. reject any weaker candidate whose final zone overlaps an accepted zone;
4. if two candidate cores are separated by fewer than two ticks **and** the
   valley between them is at least `0.85 * the lower peak's activity`, classify
   them as one `BROAD_ACTIVITY_DISTRIBUTION` rather than two HVNs;
5. if the valley is below that threshold, retain them as separate zones.

No accepted zones overlap.

## 11. POC zone

The volume POC is built from the **raw allocated-volume** profile and is always
recorded. Its zone uses the same smoothed profile, 70% core expansion, minimum
economic width, local basin and deterministic expansion.

The POC is exempt from the 95th-percentile and local-separation requirements
because it is globally defined as the maximum allocated-volume price.

```text
POC_HVN_ZONE            minimum width <= POC zone width <= 1.00 ATR
POC_BROAD_DISTRIBUTION  wider than 1.00 ATR
```

POC and non-POC zones stay separate in all results.

## 12. Value areas

The locked contiguous 70% volume and 70% TPO value areas are retained
unchanged, along with every membership, overlap and ATR-distance annotation.
Value-area position is an annotation and a predefined stratum, **never** an
eligibility gate.

## 13. Physical-zone deduplication

```text
physical_zone_id = f(contract, source-profile freeze time, source-profile family,
                     zone price interval, zone class)
```

R01 and R02 may consume the same source zone under different interaction
relationships. The structural population report distinguishes **unique physical
zones**, **relationship opportunities**, **touched relationship events** and
**economic interaction episodes**. Opportunity rows are never presented as
unique zones.

## 14. Rejection reasons

Deterministic first-failure ordering:

```text
INVALID_PROFILE_TOTAL
INVALID_TPO_TOTAL
INVALID_ACTIVE_TICK_COUNT
PEAK_PERCENTILE_TOO_LOW
PEAK_ACTIVITY_TOO_LOW
OVERLAPS_VOLUME_POC
BASIN_TOO_NARROW
NO_VALID_BASIN_SEPARATION
PEAK_TO_VALLEY_TOO_LOW
ZONE_VOLUME_DENSITY_TOO_LOW
ZONE_TPO_DENSITY_TOO_LOW
ZONE_ACTIVITY_DENSITY_TOO_LOW
WIDTH_EXCEEDS_MAXIMUM
OVERLAPS_ACCEPTED_ZONE
```

## 15. Structural pilot

The 2019 partition is run first in **structural-only** mode. No forward outcome
is calculated or inspected during the structural pilot. Output directory:

```text
outputs/stage_02_generation_4_hvn_zones_pilot/
```

Required artifacts:

```text
profile_summary.csv
raw_tick_profile_summary.csv
smoothed_profile_summary.csv
peak_candidates.csv.gz
accepted_hvn_zones.csv.gz
rejected_candidates.csv.gz
broad_distributions.csv.gz
poc_zone_summary.csv
volume_value_area_summary.csv
tpo_value_area_summary.csv
zone_width_summary.csv
zone_density_summary.csv
zone_separation_summary.csv
zones_per_profile_summary.csv
relationship_opportunity_summary.csv
structural_reconciliation.csv
manifest.json
GENERATION_4_STRUCTURAL_REPORT.md
```

The report states: dataset hash; producing code SHA; bars admitted; profile
count; reconciliation against the existing Stage 1 source-profile universe;
peak candidates; accepted POC zones; POC broad distributions; accepted non-POC
zones; broad non-POC distributions; rejections by reason; unique physical
zones; relationship opportunity rows; zones per physical profile (mean, median,
75th, 90th, maximum); width in ticks, points and ATR; volume density; TPO
density; composite activity density; peak percentile; peak-to-valley ratio;
value-area location; determinism; forbidden-year proof; and explicit
confirmation that no forward result was computed or opened.

## 16. Structural hard conditions

Mechanical and causal conditions:

```text
G4-S01 source-profile universe reconciles exactly
G4-S02 no accepted zone is narrower than four ticks
G4-S03 no accepted zone is narrower than 0.10 ATR, subject to the
       four-tick absolute floor
G4-S04 no accepted non-POC zone exceeds 0.75 ATR
G4-S05 no accepted POC zone exceeds 1.00 ATR
G4-S06 accepted zones do not overlap within one physical profile
G4-S07 every accepted non-POC zone satisfies all density, percentile
       and separation requirements
G4-S08 every zone is frozen before its eligible interaction
G4-S09 raw, smoothed, accepted, broad and rejected ledgers reconcile
G4-S10 deterministic rerun reproduces content and row order, excluding
       explicit commit metadata
G4-S11 no forbidden year is admitted
G4-S12 no forward outcome is computed or inspected
```

Sample-support conditions:

```text
G4-S13 median accepted non-POC zones per physical profile <= 3
G4-S14 90th percentile accepted non-POC zones per profile <= 6
G4-S15 at least 300 unique non-POC zones exist in 2019
G4-S16 every relationship R01-R05 has at least 20 eligible non-POC
       relationship opportunities
G4-S17 median accepted zone width >= 0.10 ATR
G4-S18 median accepted zone width >= 4 ticks
G4-S19 95th-percentile accepted non-POC width <= 0.75 ATR
```

The definition is not adjusted to force any of these gates after the counts are
seen. If a mechanical or causal condition fails, only the demonstrated
implementation defect is fixed and the pilot is rerun. If only a sample-support
condition fails, the pilot is preserved and the failure reported. No further
detector generation is invented.
