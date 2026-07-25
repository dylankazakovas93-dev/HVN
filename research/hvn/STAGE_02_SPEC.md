# Stage 2 HVN Acceptance Study

Status: **LOCKED BEFORE EMPIRICAL RESULTS**

Amended before empirical access by `STAGE_02_SPECIFICATION_AMENDMENT_01`.
Cross-session matching is primary; same-session matching is descriptive
secondary. The amendment artifact preserves the original contradiction.

Lock date: 2026-07-24  
Required starting SHA: `697779c958f817a251b52721f1c82011c402e407`  
Branch: `stage-02-hvn-acceptance`

## Question and hypothesis

Stage 2 asks whether NQ behaves with more acceptance and rotation after its
first later interaction with a frozen historical HVN than after interaction
with a comparable non-HVN zone.

The preregistered hypothesis is that HVN interactions have greater forward
inside-close share, range overlap, midpoint rotation, residence, and re-entry,
and lower close-path efficiency, than matched non-HVN interactions. This is a
structural acceptance study, not a directional or trading study.

## Authority and boundaries

NQ is the authoritative profile and signal market. MNQ portability is
untested. The two Stage 1 methods remain proxies:

1. `uniform_bar_volume`;
2. `tpo_range_occupancy`.

Neither is exact transaction-level volume at price. Stage 1 profile, ATR, bin,
POC, prominence, node-boundary, merge, and freeze definitions are unchanged.

Authorized work is frozen profile construction, frozen HVN extraction,
first-interaction detection, causal pre-touch features, non-HVN controls,
acceptance metrics, deterministic matching, development-sample inference,
episode deduplication, and robustness diagnostics.

Trades, entries, stops, targets, directional rules, signed-forward-return
selection, MFE, MAE, performance statistics, validation, holdout, MNQ
execution, charts, and Stage 3 are forbidden.

## Partitions

Development years are `2019`, `2021`, `2023`, `2025`, and partial `2026`.
Only supplied development years are used. An absent named development year is
reported as absent and is not replaced.

Years `2020`, `2022`, and `2024` may not be opened, listed, hashed, inspected,
parsed, summarized, or otherwise accessed. Year `2018` is also inaccessible.
Mixed-year archives are read only through a guarded stream that checks the raw
four-character year prefix before parsing any field and stops before a later,
unauthorized year. Every material access is logged before and after the run.

## Complete definition grid

Every applicable relationship is evaluated across:

- four profile families;
- two allocation methods;
- ATR bin ratios `0.05`, `0.10`, and `0.20`;
- prominence thresholds `1.5`, `2.0`, and `2.5`.

The relationship determines the applicable family, producing five distinct
research lanes. All cells remain registered. No cell is selected because of
its result, and correlated definition events are not treated as independent.

## Relationship lanes

### R01 — prior RTH to following ETH

The source is the previous trading RTH, 09:30–16:00 ET. The eligible window is
18:00 ET on that calendar date through 09:30 ET on the next trading date.

### R02 — prior RTH to following RTH

The source is the previous trading RTH, 09:30–16:00 ET. The eligible window is
the next trading RTH, 09:30–16:00 ET. Each node is classified as
`RTH_FIRST_OVERALL` or `RTH_AFTER_ETH_TOUCH`; both are reported separately
even when a pooled diagnostic is shown.

### R03 — full overnight to current RTH

The source is 18:00 ET on the previous date through 09:30 ET on the current
trading date. The eligible window is current RTH, 09:30–16:00 ET.

### R04 — midnight profile to current RTH

The source is 00:00–09:30 ET on the current trading date. The eligible window
is current RTH, 09:30–16:00 ET.

### R05 — opening hour to later RTH

The source is 09:30–10:30 ET on the current trading date. The eligible window
is 10:30–16:00 ET on the same date.

Relationships are not pooled into one headline result and advance
independently.

## Trading-date and session convention

No authoritative holiday calendar is supplied. A trading date is therefore a
New York date with eligible outright-NQ bars covering the relevant session.
The “next trading date” is the earliest later such date present in the
authorized data. A session is eligible only when its required source window
and interaction window can be identified from completed bars. Scheduled
closures are not imputed. Missing required minutes cause an explicit
opportunity, feature, or horizon exclusion rather than a fabricated bar.

All comparisons use `America/New_York`. Source start is inclusive, source end
is exclusive, and freeze equals exclusive source end. A bar is available at
its close. Stable ordering is `(close_time, source_row_id)`.

## Contract continuity

Only outright NQ contracts accepted by the Stage 1 contract are eligible.
Spreads and simultaneous mixed-contract construction are forbidden. For each
source window, the contract is selected causally as the outright symbol with
greatest volume in `[source_start - 72 hours, source_start)`, with ascending
symbol as the final tie-break.

The same symbol must supply the source profile, node, interaction bar, all
pre-touch features, and all forward bars. If the causal selected symbol changes
between profile formation and interaction, the opportunity is ineligible with
`CONTRACT_TRANSITION`. No adjustment or synthetic roll conversion is allowed.

## Authoritative records

The opportunity ledger has one row for every frozen HVN that could potentially
interact, including untouched and excluded nodes. Its minimum fields are:

```text
opportunity_id, profile_id, node_id, relationship_id, allocation_method,
bin_ratio, prominence_threshold, source_contract, source_session_date,
source_start, source_end, profile_freeze_time, interaction_start,
interaction_end, hvn_low, hvn_high, hvn_center, hvn_width_points,
hvn_width_bins, hvn_width_atr, peak_weight, local_baseline,
prominence_ratio, node_weight, node_weight_share, poc_distance_points,
poc_distance_atr, eligible, exclusion_reason, touched, first_touch_bar_id,
first_touch_time, touch_class, approach_side, touched_during_prior_eth,
data_year, config_hash, code_sha
```

The ledger is authoritative for total, eligible, touched, untouched, excluded,
and roll-adjacent node counts and for interaction rates.

The authoritative forward ledger contains one row per event, zone type,
configuration, relationship, and forward horizon. All summaries are computed
from saved authoritative ledgers, never from a separate calculation path.

## Identity and reproducibility

Configuration hashes cover the relationship, family, method, ratio,
prominence, event, control, metric, matching, and statistics specifications.
IDs are content-derived or created from stable sorted ordinals. Decimal and
integer-tick arithmetic is used; binary floating point is not used for market
boundary logic. CSV uses UTF-8, LF line endings, fixed columns, stable row
ordering, and canonical decimal formatting. Compressed detailed ledgers use
deterministic gzip metadata. Every output records the code SHA and input
partition.

Long runs checkpoint by year, relationship, method, bin ratio, and prominence
threshold. Completed checkpoints are immutable inputs to deterministic
aggregation; failed and rerun checkpoints remain in the run registry.

## Locked clarifications

- The occupied frozen-profile grid is the entire materialized Stage 1
  min-through-max bin grid, including zero-weight bins.
- Type-7 linear interpolation on the ordered full bin-weight distribution
  defines the 25th and 75th percentiles, using exact Decimal arithmetic.
- “Within 5 minutes” for episode clustering is an absolute touch-time
  difference of at most five minutes.
- Primary pairs use different interaction-session dates, so their forward
  windows are temporally distinct without a pairwise overlap test. Secondary
  same-session overlap is measured and reported, not rejected.
- All empirical redesigns after this lock belong to a new research generation.
  A genuine implementation defect may be corrected only with a documented
  finding, failing regression fixture, minimal fix, and affected reruns.

## Amendment 02 — superseding primary matching stratum

Effective for `STAGE_02_GENERATION_2_MATCHING`, exact `zone_width_bins`
equality is removed from the primary cross-session stratum. Treated and control
events must still share exactly `relationship_id`, `allocation_method`,
`bin_ratio`, `prominence_threshold`, `data_year`, `approach_side` and
`control_family`, and must come from different interaction-session dates.

Zone width is instead controlled as an ATR-normalized quantity by the caliper
`0.67 <= W_C/W_T <= 1.50`, by the `1.0 * abs(log(W_T/W_C))` matching-distance
term, and by pre- and post-match balance reporting in `width_balance.csv`.
Events with invalid, missing, zero or nonpositive ATR-normalized width are
rejected before matching. All Amendment 01 calipers are retained unchanged.

Generation 1 remains the authoritative result of the previous locked rule. See
`STAGE_02_AMENDMENT_02.md`.
