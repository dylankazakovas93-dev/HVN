# Generation 4 Outcome Specification

Status: **LOCKED BEFORE ANY GENERATION 4 FORWARD OUTCOME WAS INSPECTED**

Zone definition: `STAGE_02_GENERATION_4_ZONE_SPEC.md`, frozen permanently once
the 2019 structural pilot is accepted. No Generation 4 threshold — in the zone
definition, in this outcome specification, in the control specification or in
the statistics specification — may be revised after any Generation 4 forward
outcome is opened. **A negative outcome is not a defect.**

Generation 3 outcomes may not be used to tune any Generation 4 threshold.

## 1. Relationship to the Generation 3 outcome engine

The Generation 3 outcome engine (`src/hvn/gen3_outcomes.py`) is reused
unchanged in its metric mathematics. The single substantive change is the
**event interval**: every metric that previously operated on a one-tick atomic
node interval now operates on the complete multi-tick Generation 4 zone
interval `[zone_low, zone_high)`.

This applies to inside-close share, range-overlap share, residence, activity
concentration, midpoint crossings, rotation, and to the confirmed-departure
rule, which requires closes fully outside the **complete** zone.

No one-tick Generation 3 node may enter Generation 4. Because
`minimum_zone_width_ticks >= 4`, a one-tick interval cannot be constructed;
this is asserted, not assumed.

## 2. Partitions

Development: 2019, 2021, 2023, 2025, partial 2026 through the frozen endpoint.
**Primary full years: 2019, 2021, 2023, 2025.** Partial 2026 is supporting
evidence only and never counts toward year-consistency gates.

Forbidden: 2018, 2020, 2022, 2024. Not opened, parsed, listed, summarized or
hashed for empirical use. A research partition is defined by parsed timestamps,
never by an archive filename; the mixed-container ingestion guard and access
log carried over from Generation 3 remain in force unchanged.

## 3. Causal event construction

Every frozen zone produces an opportunity record whether or not it is touched.
Untouched opportunities are retained, never discarded.

```text
source_bar_close_time <= profile_freeze_time < eligible_interaction_time
```

Zone interval `[zone_low, zone_high)`, tick-exact overlap. Only completed
one-minute bars. The event is known only at the **close of the touch bar**, and
all forward measurement begins with the **next completed bar**. The touch bar
never enters a post-touch metric; it is reported separately as contemporaneous
information.

One first causal touch per zone, relationship and interaction session.

## 4. Event classes

Approach: `APPROACH_FROM_BELOW`, `APPROACH_FROM_ABOVE`, `START_INSIDE`.
Primary conditional inference uses the two directional classes only;
`START_INSIDE` is reported separately and never pooled into them.

Touch: `WICK_ONLY_SAME_SIDE`, `CLOSE_INSIDE`, `CROSS_THROUGH`.

Zone class `POC_HVN_ZONE` or `NONPOC_HVN_ZONE` is recorded on every row.
**POC and non-POC results are reported separately and are never silently
pooled.** `BROAD_ACTIVITY_DISTRIBUTION` and `POC_BROAD_DISTRIBUTION` are
recorded structurally and are excluded from primary interaction events; they
may be reported as a separate descriptive contrast only.

## 5. Pre-touch context

Recorded from information available at the touch-bar close, usable for matching
and stratification: `ATR_1m_at_touch`; zone width in ticks, points and ATR;
distance from interaction open, from volume POC/VAL/VAH and from TPO
POC/VAL/VAH, all in ATR; 15-minute pre-touch signed displacement, absolute path
length, path efficiency, mean bar volume and mean true range; profile age in
minutes; touch time within the interaction window; prior interaction in the
same session.

**No post-touch field may enter event construction, control selection or
matching.**

## 6. Touch-bar signature (contemporaneous, not an outcome)

```text
touch_bar_volume_ratio = touch bar volume / median volume of previous 15 completed bars
touch_bar_range_ratio  = touch bar true range / ATR_1m_at_touch
touch_bar_zone_overlap_share = overlap(bar range, zone) / bar range
```

Zero denominators: a zero median volume yields a null ratio recorded as
`undefined`; a zero-range bar yields overlap share 1 if its price is inside the
zone, else 0.

## 7. Horizons

5, 15, 30, 60, 120 minutes. **Primary horizon 30 minutes.** Horizons must be
complete; partial 60- and 120-minute windows near session ends are excluded and
the excluded count is reported.

## 8. Acceptance metrics

- **A01 `inside_close_share_h`** = post-touch bars closing inside the complete
  zone / complete post-touch bars in h. **Primary acceptance metric:
  `inside_close_share_30`.**
- **A02 `mean_range_overlap_share_h`**, per bar
  `overlap(bar range, zone) / bar range`; a zero-range bar contributes 1 if its
  price is inside the zone, else 0.
- **A03** probability of first inside close within 5 and 15 minutes, and
  minutes to first inside close.
- **A04 `midpoint_crossings_h`** across the frozen zone midpoint. A close
  exactly at the midpoint carries the previous non-neutral side forward.
- **A05 `full_rotation_count_h`** and probability of at least one rotation.
  Close state -1 below, 0 inside, +1 above. A rotation requires a confirmed
  outside state, an intervening zone interaction or inside close, then a
  confirmed outside state on the opposite side. Alternating completions count.
- **A06 `close_path_efficiency_h`** = |net close displacement| / sum |close-to-
  close movement|, zero when total movement is zero.

## 9. Activity concentration

Post-touch concentration is computed over the complete zone against a local
comparison band, using **bin-level occupancy**, not binary per-bar
intersection. For each post-touch bar, volume is allocated uniformly across the
ticks it occupies and one TPO occupancy is added to every occupied tick; zone
and band totals accumulate those per-tick contributions.

```text
post_touch_volume_concentration_ratio_h   = (zone_volume × band_ticks) / (band_volume × zone_ticks)
post_touch_tpo_concentration_ratio_h      = (zone_tpo    × band_ticks) / (band_tpo    × zone_ticks)
post_touch_activity_concentration_ratio_h = sqrt(volume ratio × tpo ratio)
```

Ratios are formed as a single exact division to avoid compounded rounding.
Binary per-bar touch counts are retained under distinct names
(`bars_touching_zone`, `bars_touching_band`) and are never used as TPO.

**`post_touch_activity_concentration_ratio_30` is the primary concentration
metric.**

## 10. Residence

`inside_residence_minutes_h`, `continuous_residence_after_first_inside_close`,
`longest_inside_close_run_h`, `local_band_occupancy_share_h`, `reentry_count_h`.

```text
R_T = inside_residence_minutes × ATR_1m_at_touch / zone_width_points
```

Both raw minutes and normalized `R_T` are reported, each accompanied by the
zone-width distribution. Because Generation 4 zones are at least four ticks and
at least 0.10 ATR wide, the degenerate one-tick inflation of `R_T` observed in
Generation 3 cannot arise; this is stated as a property of the definition, not
as a claim about the result.

## 11. Confirmed departure

Two consecutive completed closes fully outside the **complete** zone on the
same side; the second confirms. Excursion begins after the confirmation bar.

For `APPROACH_FROM_BELOW`: departure below is `SAME_SIDE_REJECTION`, above is
`OPPOSITE_SIDE_TRAVERSAL`. For `APPROACH_FROM_ABOVE`, reversed.

Reported: probability of confirmed departure by 15/30/60/120; minutes to
departure; same-side rejection probability; opposite-side traversal
probability; no-confirmed-departure probability.

## 12. Post-departure excursion

Over 15, 30, 60 minutes after the confirmation bar: directional excursion in
the departure direction, adverse excursion against it, re-entry probability,
time to first re-entry. Normalized separately by `ATR_1m_at_touch` and by
`zone_width_points`, and reported in raw points as well.

These are **not** called profit, loss, MFE or MAE. No entry, stop, target or
execution assumption exists anywhere in this study.

## 13. Opportunity and touch propensity

Before conditioning on a touch: probability that a treated zone is touched,
that C01 is touched, that C02 is touched; minutes from interaction open to
first touch. Reported as touch probability ratio, percentage-point difference
and time-to-touch ratio.

A zone that attracts price more often is a **different finding** from a zone
that creates acceptance once touched, and the two are never conflated.

## 14. Cross-generation comparison

Generation 3 `inside_close_share_30` measured a one-tick object; Generation 4
measures a multi-tick region. **The two must not be compared as though the
metric represented the same object.** Any reference to Generation 3 numbers in
Generation 4 reporting must state the width difference explicitly.

## 15. Required regression tests before any outcome run

1. inside-close share uses the full multi-tick zone;
2. range overlap uses the full zone;
3. residence uses the full zone;
4. activity concentration uses the full zone;
5. confirmed departure requires closes outside the complete zone;
6. no one-tick Generation 3 node can enter Generation 4.
