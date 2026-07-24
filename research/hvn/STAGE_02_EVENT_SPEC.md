# Stage 2 Event and Metric Specification

Status: **LOCKED BEFORE EMPIRICAL RESULTS**

## Price representation and overlap

NQ tick size is `0.25`. Valid market prices and zone boundaries are represented
as integer ticks. A zone is half-open: `[zone_low, zone_high)`.

A completed bar touches a zone exactly when the inclusive integer-tick set
`[bar_low_ticks, bar_high_ticks]` intersects
`[zone_low_ticks, zone_high_ticks - 1]`. A gap from one side to the other with
no valid traded tick in the node is not a touch. An exact lower-boundary trade
touches; an exact exclusive-upper-boundary trade does not.

## First interaction

Only the first eligible completed one-minute overlap in a relationship window
is the definition-level event. The event is confirmed at the touch-bar close:

```text
event_time = touch_bar_close_time
```

The touch bar is used only for classification and descriptors. Every forward
label begins with the next eligible completed bar. No touch-bar outcome enters
a forward metric.

An eligible sequence is the selected source contract only, with unique
minute/symbol rows in stable order. A duplicate, ambiguous contract, expired
window, or contract transition receives an explicit exclusion.

## Interaction classes

Each first interaction is exactly one of:

- `START_INSIDE`: the first eligible interaction-window bar overlaps;
- `APPROACH_FROM_BELOW`: the last completed pre-touch bar is fully below;
- `APPROACH_FROM_ABOVE`: the last completed pre-touch bar is fully above.

An approach requires a pre-touch close strictly below `zone_low` or at/above
`zone_high`, respectively. A discontinuous gap that produces no overlap is not
an event. Primary inference includes only the two approach classes.
`START_INSIDE` is retained and reported separately.

Each approach touch is also exactly one of:

- `WICK_ONLY_SAME_SIDE`: overlap occurs and the close remains on the approach
  side;
- `CLOSE_INSIDE`: close is in `[zone_low, zone_high)`;
- `CROSS_THROUGH`: close is beyond the opposite boundary (at/above
  `zone_high` from below, or below `zone_low` from above).

The categories are exhaustive because the touch close is on the approach side,
inside, or beyond the opposite edge.

For R02, the same integer-tick overlap rule is applied to the intervening ETH.
Any overlap sets `touched_during_prior_eth=true` and classifies the RTH event as
`RTH_AFTER_ETH_TOUCH`; otherwise it is `RTH_FIRST_OVERALL`.

## Causal pre-touch features

Every HVN and control event records:

```text
touch_time
minute_from_interaction_start
minute_of_RTH_or_ETH
approach_side
touch_class
ATR_1m_at_touch
zone_width_points
zone_width_atr
distance_from_interaction_open_to_zone_center_atr
distance_from_pre_touch_close_to_zone_edge_atr
absolute_15m_pre_touch_displacement_atr
signed_15m_pre_touch_displacement_atr
15m_pre_touch_close_path_efficiency
source_profile_range_atr
zone_distance_from_POC_atr
profile_age_minutes
prior_ETH_touch_flag
```

ATR is Wilder ATR(24), computed on the same contract and available no later
than the touch close. “ATR at touch” is the latest completed ATR value at or
before the touch close and must be positive.

The 15-minute history is exactly 15 consecutive completed one-minute bars
ending with the bar immediately before the touch bar. Displacement is last
pre-touch close minus the close immediately preceding that 15-bar path,
divided by ATR; absolute displacement is its absolute value. Pre-touch path
efficiency is absolute displacement in points divided by the sum of absolute
close-to-close moves across the same 15-minute path, and is zero when that sum
is zero. If any required bar or predecessor is absent, all affected 15-minute
features are unavailable; the lookback is never shortened.

Distance from pre-touch close uses the approached edge. Interaction-open
distance and POC distance are absolute center distances. Signed displacement
uses price sign only and is never a forward directional outcome.

## Forward horizons

Horizon rows are created for `15`, `30`, `60`, and `120` minutes. The primary
horizon is 30 minutes. A horizon is complete only when exactly `h` consecutive
eligible one-minute bars of the same contract begin immediately after the
touch bar and finish no later than the exclusive interaction end. Partial
horizons have `horizon_complete=false`, null outcome fields, and a specific
censor reason such as `WINDOW_END`, `MISSING_BAR`, or `CONTRACT_TRANSITION`.

The 5-minute first-inside flag may be calculated only when its first five bars
exist; the 15-minute flag only when its first 15 bars exist.

## M01 — inside-close share

For a complete horizon:

```text
inside_close_share_h =
count(close in [zone_low, zone_high)) / h
```

Expected treated-minus-control sign: positive. The primary outcome is
`inside_close_share_30`.

## M02 — range-overlap share

For a nonzero-range bar, inclusive integer tick counts are:

```text
bar_ticks = high_ticks - low_ticks + 1
overlap_ticks =
  max(0, min(high_ticks, zone_high_ticks - 1)
         - max(low_ticks, zone_low_ticks) + 1)
overlap_share_t = overlap_ticks / bar_ticks
```

For a zero-range bar, the share is one when its sole tick is inside and zero
otherwise. `mean_overlap_share_h` is the arithmetic mean across the complete
horizon. Expected sign: positive.

## M03 — midpoint crossings

The midpoint comparison is exact using doubled integers:
`2 * close_ticks` versus `zone_low_ticks + zone_high_ticks`. Equality is
neutral. Neutral closes carry forward the most recent non-neutral side; leading
neutral closes establish no side. A crossing is counted only on a below/above
side change. Repeated midpoint closes add no crossing. Expected sign: positive.

## M04 — close-path efficiency

For horizon `h`:

```text
abs(close_h - touch_close)
/
sum(abs(close_t - close_(t-1)))
```

The denominator starts with touch close to the first forward close. It is zero
only when all moves are zero, in which case efficiency is zero. Expected sign:
negative.

## M05 — first inside close

`first_inside_close_5` and `first_inside_close_15` indicate whether any
completed forward close is inside the half-open zone in the respective complete
prefix. Expected sign: positive.

## M06 and M08 — residence and clean exit

After the first forward inside close, residence counts elapsed one-minute bars
from that inside close through the bar immediately before the first fully
outside bar. Equivalently, clean-exit time is the integer minute difference
between the two bar close times. A fully outside bar has
`bar_high < zone_low` or `bar_low >= zone_high`.

```text
continuous_residence_normalized =
continuous_residence_minutes * ATR_1m_at_touch / zone_width_points
```

No inside close yields status `NO_INSIDE_CLOSE` and null residence, not zero.
If the eligible interaction window ends before a full exit, residence is
right-censored. Exit side is `BELOW` or `ABOVE`; no directional interpretation
is attached. Expected residence and clean-exit signs: positive.

Residence, exit, and re-entry are followed through the remaining eligible
interaction window, capped at 120 minutes after the touch for the authoritative
event fields. Horizon rows repeat the same causally derived event-level values
only when the needed follow-up is observable; censor fields distinguish
unobserved outcomes.

## M07 — re-entry

After the first full-range outside bar following an inside close, re-entry is a
later integer-tick overlap. `reentry_15`, `reentry_30`, and `reentry_60` refer
to occurrence within that many minutes after the full exit, and are null when
the required follow-up is censored. Expected sign: positive.

## Forward metric ledger

The minimum authoritative schema is:

```text
event_id, opportunity_id, zone_type, control_family, profile_id,
relationship_id, session_date, year, contract, allocation_method, bin_ratio,
prominence_threshold, zone_low, zone_high, zone_width_points, zone_width_atr,
touch_time, touch_class, approach_side, forward_horizon, horizon_complete,
censor_reason, inside_close_share, mean_overlap_share, midpoint_crossings,
path_efficiency, first_inside_close_5, first_inside_close_15,
continuous_residence_minutes, continuous_residence_normalized,
residence_censored, first_full_exit_time, first_full_exit_side, reentry_15,
reentry_30, reentry_60, source_row_ids_or_range, config_hash, code_sha
```

Source-row evidence is the stable ordered set, or a lossless first/last/count
range when contiguity is verified.

