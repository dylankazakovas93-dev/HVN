# Generation 3 Outcome Specification

Status: **LOCKED BEFORE ANY FORWARD OUTCOME WAS INSPECTED**

Detector: `STAGE_02_GENERATION_3_AMENDMENT_03`, Pilot V4 accepted.
The detector is frozen. No threshold in it may change for any reason other
than a proven mechanical or causal defect with a minimal failing fixture.
**A negative outcome is not a detector defect.**

## 1. Partitions

Development: 2019, 2021, 2023, 2025, partial 2026 through the frozen endpoint.
**Primary full years: 2019, 2021, 2023, 2025.** Partial 2026 is robustness
evidence only and never counts toward year-consistency gates.

Forbidden: 2018, 2020, 2022, 2024. Not opened, parsed, listed, summarized or
hashed.

## 2. Causal event construction

Every frozen node produces an opportunity record whether or not it is touched.
Untouched opportunities are retained, never discarded.

```text
source_bar_close_time <= profile_freeze_time < eligible_interaction_time
```

Node interval `[node_low, node_high)`, tick-exact overlap. Only completed
one-minute bars. The event is known only at the **close of the touch bar**, and
all forward measurement begins with the **next completed bar**. The touch bar
never enters a post-touch metric; it is reported separately as contemporaneous
information.

One first causal touch per node, relationship and interaction session.

## 3. Event classes

Approach: `APPROACH_FROM_BELOW`, `APPROACH_FROM_ABOVE`, `START_INSIDE`.
Primary conditional inference uses the two directional classes only;
`START_INSIDE` is reported separately and never pooled into them.

Touch: `WICK_ONLY_SAME_SIDE`, `CLOSE_INSIDE`, `CROSS_THROUGH`.

Node class `POC_ATOMIC` or `NONPOC_ATOMIC_HVN` is recorded on every row and the
two are never silently pooled.

## 4. Pre-touch context

Recorded from information available at the touch-bar close, usable for matching
and stratification: `ATR_1m_at_touch`; node width in points and ATR; distance
from interaction open, from volume POC/VAL/VAH and from TPO POC/VAL/VAH, all in
ATR; 15-minute pre-touch signed displacement, absolute path length, path
efficiency, mean bar volume and mean true range; profile age in minutes; touch
time within the interaction window; prior interaction in the same session.

**No post-touch field may enter event construction, control selection or
matching.**

## 5. Touch-bar signature (contemporaneous, not an outcome)

```text
touch_bar_volume_ratio = touch bar volume / median volume of previous 15 completed bars
touch_bar_range_ratio  = touch bar true range / ATR_1m_at_touch
touch_bar_node_overlap_share = overlap(bar range, node) / bar range
```

Zero denominators: a zero median volume yields a null ratio recorded as
`undefined`; a zero-range bar yields overlap share 1 if its price is inside the
node, else 0.

## 6. Horizons

5, 15, 30, 60, 120 minutes. **Primary horizon 30 minutes.** Horizons must be
complete; partial 60- and 120-minute windows near session ends are excluded and
the excluded count is reported.

## 7. Acceptance metrics

- **A01 `inside_close_share_h`** = post-touch bars closing inside the node /
  complete post-touch bars in h. **Primary acceptance metric:
  `inside_close_share_30`.**
- **A02 `mean_range_overlap_share_h`**, per bar
  `overlap(bar range, node) / bar range`; a zero-range bar contributes 1 if its
  price is inside the node, else 0.
- **A03** probability of first inside close within 5 and 15 minutes, and
  minutes to first inside close.
- **A04 `midpoint_crossings_h`** across the frozen node midpoint. A close
  exactly at the midpoint carries the previous non-neutral side forward.
- **A05 `full_rotation_count_h`** and probability of at least one rotation.
  Close state -1 below, 0 inside, +1 above. A rotation requires a confirmed
  outside state, an intervening node interaction or inside close, then a
  confirmed outside state on the opposite side. Alternating completions count.
- **A06 `close_path_efficiency_h`** = |net close displacement| / sum |close-to-
  close movement|, zero when total movement is zero. Low means rotation, high
  means directional departure.

## 8. Residence

`inside_residence_minutes_h`, `continuous_residence_after_first_inside_close`,
`longest_inside_close_run_h`, `local_band_occupancy_share_h`, `reentry_count_h`.

```text
R_T = inside_residence_minutes * ATR_1m_at_touch / node_width_points
```

**Both raw minutes and normalized `R_T` are reported.** A one-tick node can
produce a mechanically large `R_T`, so every `R_T` table is accompanied by the
node-width distribution.

## 9. Confirmed departure

Two consecutive completed closes fully outside the node on the same side; the
second confirms. Excursion begins after the confirmation bar.

For `APPROACH_FROM_BELOW`: departure below is `SAME_SIDE_REJECTION`, above is
`OPPOSITE_SIDE_TRAVERSAL`. For `APPROACH_FROM_ABOVE`, reversed.

Reported: probability of confirmed departure by 15/30/60/120; minutes to
departure; same-side rejection probability; opposite-side traversal
probability; no-confirmed-departure probability.

## 10. Post-departure excursion

Over 15, 30, 60 minutes after the confirmation bar: directional excursion in the
departure direction, adverse excursion against it, re-entry probability, time to
first re-entry. Normalized separately by `ATR_1m_at_touch` and by
`node_width_points`, and reported in raw points as well.

These are **not** called profit, loss, MFE or MAE. No entry, stop, target or
execution assumption exists anywhere in this study.

## 11. Opportunity and touch propensity

Before conditioning on a touch: probability that a treated node is touched, that
C01 is touched, that C02 is touched; minutes from interaction open to first
touch. Reported as touch probability ratio, percentage-point difference and
time-to-touch ratio.

A zone that attracts price more often is a **different finding** from a zone
that creates acceptance once touched, and the two are never conflated.

## 12. Archive containers versus research partitions (clarification)

This clarifies a data-container detail. It is **not** a change to the research
sample or to outcome methodology.

A research partition is defined by **parsed timestamps**, never by an archive
filename. `nq2018.zip` contains both 2018 and 2019 rows and is a legitimate
source for the authorized 2019 partition, exactly as `nq2021.zip` contains
forbidden 2022 rows and is a legitimate source for 2021.

Resolution order:

1. prefer an existing staged, verified 2019-only dataset if present;
2. verify its sha256 against the accepted 2019 dataset hash;
3. if valid, use it and do not reopen the mixed archive;
4. otherwise read the mixed archive **only** through the year-filtered
   ingestion path;
5. stream rows and admit only timestamps belonging to the requested year;
6. raise immediately if any row outside that year would reach a constructed
   Bar, profile, event, ledger, summary or statistic.

**Applied state:** no staged 2019-only dataset exists, so rule 4 applies. The
container `nq2018.zip` hashes to
`910fcd9faf31ea1a9a485398e6771e9e44eb3314f0ebbff84ed40b6bf2545203`, matching the
accepted 2019 dataset hash.

Every ingestion records: source archive name, parsed years encountered, rows
admitted, rows excluded as an earlier year, rows excluded as a later year, rows
skipped as non-outright, admitted-dataset sha256 and producing code SHA.

Verified on the real archive for 2019:

```text
archive                     nq2018.zip
parsed_years                [2018, 2019]
rows_admitted               430,528     (matches the accepted checkpoint)
rows_excluded_earlier_year  481,125     (2018, never parsed into a Bar)
rows_excluded_later_year    0
rows_skipped_non_outright   30,906      (calendar spreads)
2018 rows admitted          0
years in admitted bars      [2019]
```

The access log distinguishes **container access** — traversing an archive that
happens to hold other years — from **empirical-year access**, which is the set
of admitted rows. No structural or outcome statistic is computed or reported for
2018 at any point.
