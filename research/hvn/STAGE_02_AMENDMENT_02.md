# Stage 2 Specification Amendment 02

Status: **AUTHORIZED — NEW MATCHING GENERATION**

Authorized: 2026-07-25 by Dylan  
Detected: 2026-07-25, on the first aggregation over all completed partitions  
Applies to: Stage 2 primary cross-session matching, match-quality reporting,
and G01–G08 evaluation  
Generation: `STAGE_02_GENERATION_1_MATCHING` → `STAGE_02_GENERATION_2_MATCHING`

## 1. The original exact-width rule

Amendment 01 required that a primary treated event and its control share
exactly:

```text
relationship_id
allocation_method
bin_ratio
prominence_threshold
year
approach_side
zone_width_bins
control_family
```

with different interaction-session dates. `zone_width_bins` is an integer zone
width, so equality on it is an exact-equality stratum, not a tolerance.

## 2. The resulting sample fragmentation

Generation 1 produced **42 primary cross-session pairs** from 3,235 treated
events with complete covariates and 532,653 control events. Every gate G01–G08
returned `UNDERPOWERED` for every relationship R01–R05.

The 3,235 treated events fell into 3,092 distinct strata — about 1.05 treated
events per stratum. Controls occupied 5,675 strata; only 1,658 contained both a
treated and a control event.

| Elimination stage | Treated events |
|---|---|
| No control anywhere in its stratum | 1,452 |
| Stratum has controls, all same-session | 1,273 |
| Reached caliper evaluation | ~510 |
| At least one control passed all four calipers | 35 |

Two thirds of treated events were eliminated before any caliper was evaluated.
The calipers were never the binding constraint; the strata were.

## 3. The eligibility-only diagnosis

Counting only how many treated events retain at least one eligible
cross-session control. No outcome metric, acceptance result, gate status or
forward metric was consulted to produce this table:

| Stratum definition | Treated with >= 1 eligible control |
|---|---|
| LOCKED: zone width in bins + year | 35 |
| drop zone width in bins, keep year | 1,100 |
| keep zone width in bins, drop year | 101 |
| drop both | 1,727 |

Exact `zone_width_bins` equality is the binding design constraint. Dropping the
year stratum contributes comparatively little and would destroy the regime
control the year term provides, so year is retained.

## 4. The authorized replacement

Exact equality on `zone_width_bins` is removed from the primary stratum. Zone
width becomes a continuous, ATR-normalized quantity controlled by a caliper, a
matching-distance term, and post-match balance reporting.

Revised primary stratum — treated and control must still share exactly:

```text
relationship_id
allocation_method
bin_ratio
prominence_threshold
data_year
approach_side
control_family
```

Width is defined as:

```text
zone_width_points = (zone_high_ticks - zone_low_ticks) * 0.25
zone_width_atr    = zone_width_points / atr_1m_at_touch
```

Caliper, for treated width `W_T` and control width `W_C`:

```text
0.67 <= W_C / W_T <= 1.50
```

Events with invalid, missing, zero or nonpositive ATR-normalized width are
rejected before matching.

The primary matching distance gains one term:

```text
D =
  1.0 * absolute touch-time-of-day difference in minutes / 60
+ 1.0 * absolute pre-touch displacement difference in ATR
+ 1.0 * absolute pre-touch path-efficiency difference
+ 0.5 * absolute interaction-open-distance difference in ATR
+ 0.5 * absolute POC-distance difference in ATR
+ 1.0 * absolute ATR-at-touch proportional difference
+ 1.0 * absolute log width ratio
```

All Amendment 01 calipers are retained unchanged: touch-time-of-day difference
at most 60 minutes, absolute 15-minute pre-touch displacement difference at
most `0.75 ATR`, interaction-open-distance difference at most `1.00 ATR`, and
ATR-at-touch proportional difference at most 20%.

### Caliper form

The authorization gives the caliper twice, as a ratio bound and as
`abs(log(W_T / W_C)) <= log(1.50)`. These are not identical: the log form
admits ratios down to `1 / 1.50 = 0.6667`, while the literal lower bound is
`0.67`. The **literal ratio bound is implemented**, because it is the stricter
of the two and matching a caliper wider than authorized is not a defensible
default. Both stated boundary values, `0.67` and `1.50`, are inclusive and are
covered by tests.

This makes the caliper very slightly asymmetric in the treated/control roles.
Roles are fixed by the greedy treated-to-control direction, so the rule remains
well defined, but the asymmetry is recorded in `KNOWN_LIMITATIONS.md`.

## 5. Year remains an exact matching stratum

`data_year` is retained as an exact stratum. Controls from a different year are
rejected. Cross-year matching is not authorized by this amendment, and the
eligibility table above shows it is not needed: the width term alone accounts
for the fragmentation.

## 6. Width remains controlled

Removing the exact stratum does not remove width from the design. Width is
controlled at three points: the caliper bounds admissible pairs, the log-ratio
distance term prefers closer widths among admissible controls, and pre- and
post-match standardized mean differences are reported per lane in
`width_balance.csv`. The preferred post-match condition is absolute width
SMD <= 0.20; if width remains above 0.20 it is reported plainly and reflected
in G07 match validity rather than resolved by adjusting the caliper.

## 7. No outcome-based threshold selection

The caliper bounds and the distance weight were supplied in the authorization
and were not searched. No forward metric, acceptance result, paired result or
gate status was inspected to choose them. The eligibility diagnosis in section
3 counts admissible controls only. No alternative width caliper has been
evaluated, and none may be evaluated after Generation 2 results are observed.

Forward outcomes enter neither eligibility nor distance.

## 8. This is a new matching generation, not a bug fix

Amendment 01 resolved a logical impossibility: the original same-session rules
could not produce any pair at all. The amended cross-session design is
satisfiable but yields 42 pairs, which cannot support its own gates. Both are
the same class of defect — a preregistered matching rule that cannot deliver
the sample its gates require — and the second was not visible until real
partitions existed.

Because the change was proposed after observing that the locked stratum is
underpowered, section 13 applies. The research generation is incremented,
Generation 1 artifacts are preserved unchanged, Generation 2 artifacts are
written separately, and both remain in the trial registry.

Generation 1 is labelled `STAGE_02_GENERATION_1_MATCHING = UNDERPOWERED`. That
label describes the matching design, **not** the HVN hypothesis. Generation 1
provides no evidence for or against HVN acceptance; it establishes only that
the Generation 1 matching rule could not produce an evaluable sample.

## 9. Concurrent implementation defect — omitted 2019 partition

Independently of the matching change, `scripts/aggregate_stage_02.py` declared
`YEARS = (2021, 2023, 2025, 2026)`. `PARTITIONS.json` declares development
years 2019, 2021, 2023, 2025 and partial 2026. The Generation 1 aggregation
therefore consumed four of five completed partitions and silently excluded
2019, whose ledgers were computed, accepted and committed under
`S02-RECOMP-2019-001`.

This is an implementation defect, not a specification choice: no document
authorizes excluding 2019, and D-012 restored it to the partition set. It is
corrected in Generation 2, which aggregates all five declared partitions. No
event-generation recomputation is required, because the 2019 ledgers already
exist.

Generation 1 is preserved as produced, over four partitions. Generation 1 and
Generation 2 therefore differ in both matching rule and partition coverage, and
their pair counts are not directly comparable. The comparison that remains
valid is the eligibility diagnosis in section 3, which was computed over the
same four-partition input as Generation 1.
