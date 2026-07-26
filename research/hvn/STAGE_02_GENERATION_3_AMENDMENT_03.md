# Generation 3 Amendment 03 — Global Significance and Local Distinctness

Status: **LOCKED BEFORE ANY FORWARD OUTCOME WAS INSPECTED**
**This is the final authorized detector definition for Generation 3.**

Authorized: 2026-07-26 by Dylan
Amendment: `STAGE_02_GENERATION_3_AMENDMENT_03`
Definition: `GLOBAL_SIGNIFICANCE_AND_LOCAL_DISTINCTNESS`

```text
GENERATION_3_PILOT_V1 = REJECTED_STRUCTURAL_DEFINITION
GENERATION_3_PILOT_V2 = STRUCTURALLY_VALID_BUT_SUPERSEDED_BEFORE_OUTCOME_ANALYSIS
GENERATION_3_PILOT_V3 = STRUCTURALLY_VALID_BUT_SUPERSEDED_BEFORE_OUTCOME_ANALYSIS
GENERATION_3_PILOT_V4_GLOBAL_AND_LOCAL = authorized
```

## 1. Pilot V3's accepted structural results

Pilot V3 passed all twenty-three hard conditions and is preserved intact in
`outputs/stage_02_generation_3_atomic_pilot_v3/`. It is **not** defective:

- 6,852 profiles, `(profile_id, method, ratio)` multiset identical to Generation 1;
- 116,114 candidates = 42,105 accepted + 74,009 rejected, reconciling exactly;
- every node 1-5 bins; both value areas valid in 3,426 of 3,426 profiles;
- all 17 artifacts byte-identical on rerun;
- the POC population unchanged from Pilot V2.

It also solved the problem it was written for: unique non-POC nodes rose from
43 to 28,489, and R01 and R02 went from zero to over ten thousand each.

## 2. The excessive non-POC population

| measure | Pilot V3 |
|---|---|
| unique `NONPOC_ATOMIC_HVN` | 28,489 |
| unique `POC_ATOMIC` | 2,681 |
| non-POC share of unique accepted | 91.4% |
| non-POC nodes per profile | approximately 8 |
| median accepted local activity prominence | ~1.07 |
| minimum accepted local prominence | 0.78 |

A minimum below 1.00 means some accepted nodes were *weaker* than their own
local background while still clearing every density floor. Combined with eight
nodes per profile, the detector was identifying common composite ripples rather
than a smaller population of meaningful secondary high-activity nodes.

## 3. Discovered before outcome access

Every quantity above is structural: node classes, widths, densities,
percentiles and prominences of frozen source profiles. **No forward outcome has
been inspected at any point.** Pilots V2 and V3 ran structural-only and computed
none; Pilot V1's four outcome ledgers exist on disk and have never been opened.
The thresholds below are fixed before any outcome is read.

## 4. TPO remains integral

TPO stays in candidate formation and in qualification. Candidates are still
discovered from the composite activity profile, and `zone_tpo_density_ratio`
remains a floor. The volume construction allocates each completed bar's volume
uniformly across the bins its range intersects, so it is a proxy and never
transaction-level volume at price; time-at-price is the independent
corroboration. The new percentile gate is applied to **composite** activity, so
it too depends on TPO.

## 5. Raw volume is never compared across sessions

All normalization remains inside the single completed frozen source profile.
Prior-RTH, full-overnight, midnight-to-open and opening-hour profiles are never
compared by raw activity. The new percentile is profile-relative by
construction: it ranks a bin against the other active bins of its own profile.

## 6. Why global profile significance is needed

The Amendment 02 floors are relative to the profile mean. A bin at 1.35x the
mean is above average but can still be unremarkable in a profile with a long
right tail. Requiring the peak to sit in the **top 10% of active bins of its own
profile** makes the node globally important within the object it belongs to,
without ever comparing across profiles.

## 7. Why mild local distinctness is needed

A node weaker than its own surroundings is not a node. Requiring
`local_activity_prominence >= 1.10` removes candidates at or below their local
background — including every case in V3's accepted population with prominence
under 1.00.

## 8. Why the 1.50 veto stays rejected

Amendment 01 required `local_volume_prominence >= 1.50`, which vetoed
high-activity prices embedded inside dense accepted regions and left 43 non-POC
nodes in a year. The new rule is far weaker and is applied to composite activity
rather than volume alone:

```text
candidate activity 1.50, local median 1.40 -> prominence 1.071 -> reject
candidate activity 1.60, local median 1.40 -> prominence 1.143 -> accept
```

It demands only that a node exceed its background, not that it be an isolated
spike.

## 9. Immutable thresholds

Retained from Amendment 02, unchanged:

```text
1 <= zone_width_bins <= 5
no overlap with the volume POC plateau
zone_volume_density_ratio   >= 1.25
peak_volume_density_ratio   >= 1.50
zone_tpo_density_ratio      >= 1.00
zone_activity_density_ratio >= 1.35
```

Added:

```text
peak_activity_percentile   >= 90.0
local_activity_prominence  >= 1.10
```

### Percentile convention

`peak_activity_percentile` is computed on the composite activity of the
candidate's peak bin against **all active bins of the same completed source
profile**, on a 0-100 scale:

```text
percentile = 100 * |{active bins with activity strictly less than x}|
                 / |{active bins}|
```

Ties therefore share the lowest percentile of their group, matching the
convention already frozen elsewhere in the project. The computation uses exact
`Decimal` arithmetic and integer counts only, so it is identical across
operating systems, and it uses no future data. The exact 90.0 boundary passes
and is covered by test.

Under heavy tying — for example small integer TPO counts in sparse profiles — a
large group of bins can share one percentile value, so this gate can be
conservative in thin profiles. That is recorded as a known limitation.

### Prominence convention

```text
local_activity_prominence = peak composite activity
                          / median composite activity of the neighbourhood
```

over the frozen +/- 0.50 ATR neighbourhood, excluding the candidate plateau's
own bins, using only bins inside the completed source profile and the project's
existing deterministic median convention. A missing, empty, zero or nonpositive
baseline is **invalid** and fails the gate; a zero baseline is never treated as
infinite prominence. Exactly 1.10 passes; immediately below fails.

Volume prominence and TPO prominence remain recorded annotations and may not
veto a candidate individually. Only composite activity prominence gates.

## 10. Frozen rejection ordering

```text
INVALID_PROFILE_TOTAL
INVALID_TPO_TOTAL
INVALID_ACTIVE_BIN_COUNT
WIDTH_TOO_LARGE
OVERLAPS_VOLUME_POC
ZONE_VOLUME_DENSITY_TOO_LOW
PEAK_VOLUME_DENSITY_TOO_LOW
ZONE_TPO_DENSITY_TOO_LOW
COMPOSITE_ACTIVITY_TOO_LOW
ACTIVITY_PERCENTILE_TOO_LOW
LOCAL_ACTIVITY_PROMINENCE_TOO_LOW
```

## 11. POC rules unchanged

Every volume POC remains classified `POC_ATOMIC` or `POC_BROAD` under the
Amendment 01 rules. A POC is **not** subject to the percentile or local
prominence gates: it is already, by definition, the maximum allocated-volume
location of its profile. All volume, TPO, activity, prominence and value-area
annotations are still computed for it. The Pilot V4 POC population must be
identical to Pilots V2 and V3.

## 12. Value areas unchanged

Both 70% contiguous value areas and every membership, overlap and distance
annotation carry over unmodified. Value-area location remains an annotation and
a predefined stratum, never an eligibility gate.

## 13. Controls

Controls are rebuilt against the final accepted-node universe and must not
overlap the POC, any accepted non-POC node, any broad composite plateau,
another control in the same lane, or off-grid space. `C02_ACTIVITY_MATCHED` now
also matches on `peak_activity_percentile` and `local_activity_prominence`.

Controls are **not** required to be composite local maxima. That is the point:
C02 compares an actual local high-activity node against an ordinary zone of
similar overall activity, isolating local peak geometry.

## 14. Finality

No further detector amendment is authorized after Pilot V4 unless a mechanical
or causal defect is discovered. Thresholds may not be revised after structural
counts are seen, and may never be revised using an outcome.
