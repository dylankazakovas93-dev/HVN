# Generation 3 Amendment 02 — Composite Volume/TPO Atomic Nodes

Status: **LOCKED BEFORE ANY FORWARD OUTCOME WAS INSPECTED**

Authorized: 2026-07-26 by Dylan
Amendment: `STAGE_02_GENERATION_3_AMENDMENT_02`
Definition: `COMPOSITE_VOLUME_TPO_ATOMIC_NODES`

```text
GENERATION_3_PILOT_V1 = REJECTED_STRUCTURAL_DEFINITION
GENERATION_3_PILOT_V2 = STRUCTURALLY_VALID_BUT_SUPERSEDED_BEFORE_OUTCOME_ANALYSIS
GENERATION_3_PILOT_V3_COMPOSITE_ACTIVITY = authorized
```

## 1. Pilot V2's accepted structural results

Pilot V2 passed all thirteen hard conditions. It is **not** computationally
defective and is preserved intact in
`outputs/stage_02_generation_3_atomic_pilot_v2/`:

- 6,852 profiles, with a `(profile_id, method, ratio)` multiset identical to
  Generation 1, proving Stage 1 construction unchanged;
- 388,854 candidates, 10,395 accepted, 378,459 rejected, reconciling exactly;
- every accepted node 1-4 bins wide, at most 0.89 ATR, median 0.25 points,
  against Pilot V1's widest zone of 51 bins and 6.10 ATR;
- both 70% value areas contiguous and containing their POC in 3,426 of 3,426
  profiles;
- byte-identical deterministic rerun across all thirteen artifacts.

It corrected both V1 pathologies: sparse tail structure is removed by the
volume-density floor, and dense peaks with heavy neighbours survive through the
POC prominence exemption.

## 2. The 98.8% POC concentration

Collapsing accepted rows to unique physical `(profile, start bin, class)`:

| class | unique nodes |
|---|---|
| `POC_ATOMIC` | 2,681 |
| `NONPOC_ATOMIC_HVN` | **43** |

Non-POC rows by relationship: R01 **0**, R02 **0**, R03 87, R04 36, R05 6.

Under the V2 thresholds, Generation 3 would in practice be a study of POC
behaviour alone, with two relationships contributing no non-POC evidence at all.

## 3. This is a population-definition problem, not an outcome finding

The concentration was measured from structural quantities only — node classes,
widths, densities, percentiles and prominences of the *frozen source profiles*.
It says nothing about what price did afterwards.

**No forward outcome has been inspected.** Pilot V2 ran in structural-only mode
and computed none. Pilot V1's four forward-outcome ledgers exist on disk and
have never been opened. That property is preserved by this amendment: the
thresholds below are fixed now, before any outcome is read.

## 4. Why TPO remains part of the detector

The volume profile is a *proxy*: each completed one-minute bar's volume is
allocated uniformly across the bins its range intersects. It is not
transaction-level volume at price and is never described as such. A single
wide-range bar spreads volume across many bins it may barely have traded in.

Time-at-price is independent evidence. A bin where many completed bars actually
sat is corroborated; a bin credited with volume by one sweeping bar is not.
Removing TPO would leave the detector resting entirely on the weaker proxy, so
TPO stays in both candidate discovery and node qualification.

## 5. Why local prominence is no longer a hard eligibility gate

V2 required every non-POC node to clear `local_volume_prominence >= 1.50`
against the median of its +/- 0.50 ATR neighbourhood. That vetoes exactly the
objects worth studying: a genuinely busy price embedded inside other busy
prices. In V2's accepted population the median prominence was 1.11, sustainable
only because 98.8% of those nodes were POCs exempt from the rule.

Prominence remains **recorded** — for volume, TPO and composite activity — as a
descriptive annotation and a predefined analysis stratum. It no longer decides
eligibility, and it may not appear as a rejection reason.

## 6. Composite activity

Per active bin, retaining the V2 density definitions:

```text
volume_density_ratio_i = V_i / mean positive-bin volume
tpo_density_ratio_i    = T_i / mean positive-bin TPO count

activity_density_ratio_i = sqrt(volume_density_ratio_i * tpo_density_ratio_i)
```

The geometric mean is deliberate. It requires agreement between volume and
time-at-price without demanding that each independently clear a severe floor:

```text
volume 1.50, TPO 1.50 -> activity 1.50
volume 2.25, TPO 1.00 -> activity 1.50
```

Both describe meaningful concentration. Because the geometric mean collapses
toward zero when either input does, high volume cannot rescue near-zero
time-at-price, and high TPO cannot rescue negligible volume.

Percentile ranks are recorded for volume, TPO and composite density as
annotations and audit fields. They are **not** eligibility thresholds under
this amendment.

## 7. Candidate geometry

Non-POC candidates are detected from the **composite activity profile**, not
from volume alone:

```text
ONE_BIN_COMPOSITE_LOCAL_MAXIMUM
COMPOSITE_FLAT_TOP_PLATEAU
```

A plateau is a maximal contiguous run of bins sharing the same composite
maximum under the frozen numeric precision. No 50% shoulder expansion, no
expansion through lower-activity neighbours, no merging of distinct peaks, no
truncation, no future information.

```text
1 <= zone_width_bins <= 5
```

Wider composite plateaus are recorded as `BROAD_COMPOSITE_PLATEAU` and excluded
from atomic events. POC construction remains based on allocated volume, not on
the composite score.

## 8. Revised non-POC definition

A candidate qualifies as `NONPOC_ATOMIC_HVN` only when all hold:

```text
1. it is a composite local maximum or flat-top composite plateau
2. 1 <= zone_width_bins <= 5
3. it does not overlap the volume POC plateau
4. zone_volume_density_ratio     >= 1.25
5. peak_volume_density_ratio     >= 1.50
6. zone_tpo_density_ratio        >= 1.00
7. zone_activity_density_ratio   >= 1.35
8. all profile totals and frozen inputs are valid
```

In plain terms: the zone carries above-average volume, its peak is meaningfully
high-volume, price spent at least average time there, combined volume and time
concentration is strong, and it is an actual local composite peak.

Explicitly **not** required: any local prominence threshold, and any volume,
TPO or activity percentile threshold.

Fixed thresholds, not to be tuned after the pilot or after any outcome:

```text
zone volume density  1.25
peak volume density  1.50
zone TPO density     1.00
composite activity   1.35
maximum width        5 bins
```

## 9. POC definition unchanged

The accepted V2 POC rules carry over. Every volume POC is classified
`POC_ATOMIC` or `POC_BROAD`; `POC_ATOMIC` requires width <= 5 bins, valid
totals and `zone_volume_density_ratio >= 1.50`. The POC remains exempt from
local-prominence and TPO-density gates because it is by definition the maximum
allocated-volume location. All TPO and composite features are still computed and
recorded for it. POC and non-POC events stay strictly separate everywhere.

## 10. Value areas unchanged

Both 70% contiguous value areas are carried over from V2 unmodified, along with
every membership flag, overlap flag and ATR distance. Value-area location
remains a predefined annotation and analysis stratum, never an eligibility
filter.

## 11. Rejection ledger

Every composite candidate appears in the accepted or rejected ledger, with a
deterministic first-failure reason from:

```text
WIDTH_TOO_LARGE
OVERLAPS_VOLUME_POC
ZONE_VOLUME_DENSITY_TOO_LOW
PEAK_VOLUME_DENSITY_TOO_LOW
ZONE_TPO_DENSITY_TOO_LOW
COMPOSITE_ACTIVITY_TOO_LOW
INVALID_PROFILE_TOTAL
INVALID_TPO_TOTAL
INVALID_ACTIVE_BIN_COUNT
```

Local prominence and percentile may not appear as rejection reasons. Ledger
counts reconcile exactly, and a physical zone recognised as both the POC and a
composite candidate is counted once.

## 12. Controls

`C01_NEUTRAL` represents ordinary profile locations without high composite
activity. `C02_ACTIVITY_MATCHED` matches the treated node's general activity
level without being a composite local maximum, calipered on zone width, zone
volume density, zone TPO density, zone composite activity, value-area location,
distance from the volume POC, profile family and relationship.

C02 therefore asks whether **local peak geometry** matters after controlling
for the general amount of volume and time-at-price. Controls may not overlap
the POC, any accepted node, another selected control in the same lane, or
unprofiled price space, and no post-touch information is used to select them.

## 13. Preservation

Generations 1 and 2, Pilot V1 and Pilot V2 remain byte-unchanged in their own
directories. Pilot V3 writes only to
`outputs/stage_02_generation_3_atomic_pilot_v3/`. No threshold in this
amendment may be altered after any forward outcome is viewed.
