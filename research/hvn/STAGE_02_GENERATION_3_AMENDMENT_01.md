# Generation 3 Amendment 01 — Session-Normalized Atomic Nodes

Status: **LOCKED BEFORE ANY FORWARD OUTCOME WAS INSPECTED**

Authorized: 2026-07-25 by Dylan
Amendment: `STAGE_02_GENERATION_3_AMENDMENT_01`
Definition: `SESSION_NORMALIZED_ATOMIC_NODES`

```text
GENERATION_3_PILOT_V1 = REJECTED_STRUCTURAL_DEFINITION
GENERATION_3_PILOT_V2_SESSION_NORMALIZED = authorized
```

Pilot V1 is preserved in `outputs/stage_02_generation_3_atomic/` with its
finding in `reviews/STAGE_02_GENERATION_3_PILOT_FINDING.md`. Its
forward-outcome tables — proximity, residence, departure, excursion — have
never been opened and must not be. Pilot V2 writes to a separate directory.

## 1. The relative-prominence failure mechanism

The V1 detector qualified a candidate on local prominence alone: the peak
weight divided by the median weight of non-plateau bins within +/- 0.50 ATR.
Prominence is a purely **relative** quantity with no absolute or
session-relative floor, which inverts the selection.

In a dense region the neighbourhood is nearly as heavy as the peak, so the
ratio approaches 1 and the peak is rejected. Reconciled against a real rebuilt
profile (`39f78407347ad3f7c87c`, TPO, ratio 0.05, ATR 1.503, 259 bins):

```text
POC bin 25702, weight 67, local baseline 62, prominence 1.081 -> REJECTED
48 candidates, 0 qualifying at threshold 1.5
```

In a sparse tail the neighbourhood is nearly empty, so a trivial bump clears
any threshold:

| class | count | median prominence | median peak weight |
|---|---|---|---|
| 1 bin | 1,938 | 1.60 | 78.9 |
| >= 10 bins | 923 | 2.00 | 3.0 |

Consequences measured on the 2019 pilot: only **25 of 6,019** qualifying peaks
contained the profile POC; **923** were at least ten bins wide; the widest
covered **51 bins and 6.10 ATR**. Generations 1 and 2 masked this because every
peak was then expanded through 50%-weight bins and merged.

## 2. Raw volume is not comparable across sessions

An overnight Globex profile and an RTH profile differ in total traded volume by
a large factor. A fixed absolute volume floor would admit almost every RTH bin
and almost no overnight bin, which would silently turn the node definition into
a session filter.

Therefore **every threshold in this amendment is normalized within the single
completed frozen source profile that produced the node**. Prior-RTH nodes
normalize against that prior-RTH profile; full-overnight nodes against that
overnight profile; midnight nodes against that midnight-to-open profile;
opening-hour nodes against that opening-hour profile. Raw totals are never
compared between profiles or between sessions.

All totals, active-bin counts, percentiles, TPO counts, POC, value areas and
thresholds are frozen at the profile freeze time. No interaction bar may change
them.

## 3. Profile-level quantities

```text
V_total  = sum of allocated volume over all profile bins
T_total  = sum of TPO counts over all profile bins
N_active = number of bins with positive volume or positive TPO occupancy
```

The Stage 1 uniform bar-volume allocation is the primary volume profile. The
Stage 1 completed-bar TPO/range-occupancy construction is the independent
time-at-price proxy. Stage 1 profile construction is unchanged.

The volume proxy is an allocation of one-minute OHLCV bar volume across the
bins a bar's range intersects. It is **not** transaction-level volume at price,
and is never described as such.

## 4. Bin-level normalized features

```text
volume_share_i         = V_i / V_total
volume_density_ratio_i = V_i / (V_total / N_active)
tpo_share_i            = T_i / T_total
tpo_density_ratio_i    = T_i / (T_total / N_active)
```

`volume_density_ratio = 1.0` means the bin holds exactly the average volume of
an active price bin in that same source profile; `2.0` means twice that. This
makes quiet and busy sessions comparable without comparing raw totals.

Percentile ranks are computed among **positive** profile bins using an
explicitly frozen convention:

```text
percentile_i = (count of positive bins with weight strictly less than w_i)
               / (count of positive bins)
```

Ties therefore share the lowest percentile of their group, and the convention
is deterministic under equal weights. Tie handling is covered by test.

## 5. Atomic candidate geometry

A candidate is either `ONE_BIN_LOCAL_MAXIMUM` or `FLAT_TOP_PLATEAU`, where a
flat-top plateau is a maximal contiguous run of bins sharing the same local
maximum weight under the existing deterministic profile precision.

No 50%-of-peak shoulder expansion. No merging of separate peaks. No growth
through lower-weight shoulder bins.

```text
zone_width_bins = high_bin_index - low_bin_index + 1
1 <= zone_width_bins <= 5
```

A plateau wider than five bins is **not** an atomic node. It is recorded
separately as `BROAD_HIGH_VOLUME_PLATEAU` and excluded from atomic interaction
events. It is never truncated to five bins.

## 6. Zone-level session-normalized features

```text
zone_volume        = sum(V_i for i in z)
zone_tpo           = sum(T_i for i in z)
zone_volume_share  = zone_volume / V_total
zone_tpo_share     = zone_tpo / T_total

zone_volume_density_ratio = zone_volume_share / (zone_width_bins / N_active)
zone_tpo_density_ratio    = zone_tpo_share    / (zone_width_bins / N_active)
```

`zone_volume_density_ratio = 2.0` means the zone holds twice the volume of an
average equally wide section of the active profile. This is the primary
session-relative volume floor, and it is width-normalized so a five-bin zone is
not advantaged over a one-bin zone.

## 7. Local prominence, retained as a separate condition

Computed on the existing +/- 0.50 ATR neighbourhood, excluding all bins of the
candidate plateau, using the median weight of the remaining neighbourhood bins,
with no post-freeze value substituted:

```text
local_volume_prominence = candidate_peak_weight / local_neighbourhood_median
```

A zero baseline is handled explicitly: prominence is recorded as undefined and
the candidate **fails** the prominence condition rather than passing on an
infinite ratio. This closes the V1 path by which empty neighbourhoods admitted
trivial bumps.

Local prominence alone never qualifies a node.

## 8. Non-POC atomic requirements

A non-POC candidate qualifies as `NONPOC_ATOMIC_HVN` only when **all** hold:

```text
1 <= zone_width_bins <= 5
zone_volume_density_ratio >= 1.50
zone_tpo_density_ratio    >= 1.25
peak volume percentile    >= 0.75
local_volume_prominence   >= 1.50
```

The peak volume percentile refers to the maximum-volume bin inside the
candidate zone. Thresholds are frozen here and are not searched. No alternative
floor may be tried after outcomes are seen.

Rejections are recorded with the first failed reason from:

```text
WIDTH_TOO_LARGE
VOLUME_DENSITY_TOO_LOW
TPO_DENSITY_TOO_LOW
VOLUME_PERCENTILE_TOO_LOW
LOCAL_PROMINENCE_TOO_LOW
INVALID_PROFILE_TOTAL
INVALID_TPO_TOTAL
INVALID_ACTIVE_BIN_COUNT
```

## 9. POC treatment

Every valid profile records its volume POC: the bin, or contiguous tied
plateau, of maximum allocated volume. Ties extend the plateau contiguously; a
non-contiguous tie resolves to the lowest bin index, deterministically.

The POC always appears in the structural profile ledger even when it is not
atomic, classified as:

```text
POC_ATOMIC  tied maximum plateau is 1 to 5 bins wide
POC_BROAD   tied maximum plateau is wider than 5 bins
```

`POC_ATOMIC` is **exempt from the local-prominence threshold**, because the
profile's maximum-volume price can legitimately sit among heavy neighbours —
which is exactly the case V1 rejected. It must still satisfy width, valid
totals, and `zone_volume_density_ratio >= 1.50`. Its TPO metrics and
percentiles are computed and recorded, but it is not excluded solely for TPO
density below 1.25.

`POC_ATOMIC` and `NONPOC_ATOMIC_HVN` are separate event classes in every ledger
and every analysis, never silently pooled. A non-POC node may not overlap the
POC zone.

## 10. 70% volume value area

Built on the allocated-volume profile:

1. start with the complete POC bin or tied POC plateau;
2. set cumulative volume to that region's volume;
3. examine the next unselected adjacent bin above and below;
4. add the side with greater allocated volume;
5. on an exact tie, add the **lower** side, a frozen deterministic rule;
6. continue one bin at a time, contiguously;
7. stop when cumulative volume is at least `0.70 * V_total`.

Recorded: `volume_VAL`, `volume_VAH`, `volume_POC`,
`volume_value_area_volume_share`, `volume_value_area_bin_count`.

Invariants: the POC lies inside the area; `VAL <= POC <= VAH`; cumulative share
is at least 70%; bounds are contiguous; no post-freeze data are used;
construction is deterministic. The final added bin may overshoot 70%, and the
result is not forced to equal exactly 70%.

## 11. 70% TPO value area

The same contiguous expansion with TPO counts replacing volume weights,
starting from the TPO POC. Recorded: `tpo_VAL`, `tpo_VAH`, `tpo_POC`,
`tpo_value_area_tpo_share`, `tpo_value_area_bin_count`.

The two value areas are separate structural descriptions — where allocated
volume concentrated, and where completed bars spent time. Neither replaces the
other.

## 12. Value-area annotations

Every atomic node records `inside_volume_value_area`, `inside_tpo_value_area`,
the six `overlaps_*` flags for VAL, VAH and POC on both areas, and the six
`distance_to_*_atr` measures, using causally frozen ATR.

```text
VALUE-AREA LOCATION IS AN ANNOTATION, NOT AN ELIGIBILITY REQUIREMENT.
```

No node is excluded for lying outside the 70% area. This preserves the ability
to compare inside-area, edge, outside-area, POC and non-POC nodes as
predeclared strata. Outcome differences among these categories are not to be
inspected until the definition is committed and the sweep is authorized.

## 13. Session-phase contributions

Where a source profile contains them, zone-level contributions are recorded for
the existing fixed ET anchors already in the session contract:

```text
18:00-00:00 ET
00:00-09:30 ET
09:30-10:30 ET
10:30-16:00 ET
```

Only sub-windows contained within that source profile are recorded, as
`subwindow_volume_share_of_zone` and `subwindow_tpo_share_of_zone`. No
DST-sensitive "London" label is invented. These are annotations only; raw
sub-window totals are never used as eligibility thresholds. Primary
normalization remains against the entire completed source profile.

## 14. Structural-only mode

`--structural-only` constructs profiles, normalized bin features, POC, both
value areas, candidates, accepted and rejected nodes, controls and structural
audit ledgers. It must not compute, load, inspect, summarize or write forward
proximity, residence, departure, excursion, matched-outcome or
future-price-based gate results.

`--help` exits without reading market data. Unknown arguments fail loudly.

## 15. Provenance of this amendment

The failure was diagnosed entirely from structural quantities: zone widths,
POC containment, prominence ratios, peak weights and one reconciled profile.
**No forward outcome from Pilot V1 was inspected before this amendment was
frozen**, and its outcome ledgers remain unread. The thresholds above were
supplied in the authorization, not searched, and no alternative was evaluated.
