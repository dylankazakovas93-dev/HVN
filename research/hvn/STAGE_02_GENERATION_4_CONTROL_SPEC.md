# Generation 4 Control and Matching Specification

Status: **LOCKED BEFORE ANY GENERATION 4 FORWARD OUTCOME WAS INSPECTED**

## 1. Control families

Controls are constructed from frozen structural information only, on the same
tick grid and from the same completed source profiles as the treated zones.

```text
C01_NEUTRAL           does an HVN zone behave differently from an ordinary
                      neutral profile region of comparable width?
C02_ACTIVITY_MATCHED  does local-peak zone geometry matter after controlling
                      for the general amount of volume and time-at-price?
```

**`C02_ACTIVITY_MATCHED` is the primary control family.** C01 is supporting
evidence.

A control interval is a contiguous multi-tick region built on the same tick
grid, drawn to the **same width distribution** as the treated zones: each
control is assigned a target width in ticks equal to the width of the treated
zone it is a candidate for, subject to the same absolute floor
(`>= 4 ticks`, `>= 0.10 ATR`) and the same ceiling (`<= 0.75 ATR` for non-POC).
A one-tick control cannot exist.

Controls may not overlap the volume POC, any accepted zone, any recorded broad
activity distribution, another selected control in the same lane, or invalid
profile space.

Controls are **not** required to be smoothed local maxima, and are **not**
required to satisfy the 95th-percentile, peak-to-valley or zone-density gates —
that is precisely what the treated/control contrast is testing. C02 controls
are additionally required to fall inside a bounded band of composite activity
density around their treated counterpart (see §2), so that the comparison
isolates peak geometry rather than the raw amount of activity.

Complete control-opportunity ledgers are written, **including untouched
controls**. Retaining only controls that later produce convenient events is
forbidden.

## 2. Cross-session conditional matching

Exact match on **six** keys only:

```text
data_year
relationship
source profile family
control family
approach side
value-area location class
```

Value-area location classes: `INSIDE_VALUE`, `VALUE_EDGE`, `OUTSIDE_VALUE`,
where `VALUE_EDGE` means the zone or control overlaps volume VAH or VAL.

Continuous calipers:

```text
touch-time-of-day difference          <= 60 minutes
ATR proportional difference           <= 20%
pre-touch displacement difference     <= 0.75 ATR
interaction-open distance difference  <= 1.00 ATR
zone-width ratio                      within [0.67, 1.50]
distance-to-volume-POC difference     <= 1.00 ATR
composite activity density ratio      within [0.80, 1.25]   (C02 only)
```

Deterministic greedy 1:1 nearest-neighbour matching, no control reuse within a
lane. The matching distance sums normalized terms for touch time, ATR,
pre-touch displacement, pre-touch path efficiency, interaction-open distance,
log zone width and distance to volume POC. **No post-touch outcome enters
eligibility or distance.**

POC zones are matched only against POC-eligible lanes and non-POC zones only
against non-POC lanes; the two are never cross-matched.

The full matching funnel and every rejection reason are reported. A lane that
cannot be matched adequately is marked `UNDERPOWERED`. **Calipers are never
loosened after outcomes are viewed.**

## 3. Same-session robustness

A separate descriptive comparison using controls from the same frozen profile
and interaction session. This is **not** the primary causal comparison; forward
windows may overlap. Recorded: percentage of overlapping windows, touch-time
ordering, and whether treated or control occurred first. Inference clusters by
interaction session.

Same-session results may support or contradict the primary comparison but
**cannot rescue a failed primary gate**.

## 4. Economic episodes

Configuration-level zones are not independent. Events cluster into one economic
episode when all hold:

```text
same contract
same relationship
same interaction session
touch times within 5 minutes
zone price intervals overlap by >= 50% of the narrower interval
same approach side
```

Reported: configuration rows, unique physical zones, touched zones, unique
economic episodes, matched economic episodes.

**Primary inference operates at, or clusters by, the economic-episode level.**
Selecting the best-performing configuration within an episode is forbidden.

## 5. Physical-zone deduplication

`physical_zone_id` is derived from contract, source-profile freeze time,
source-profile family, zone price interval and zone class. R01 and R02 may
consume the same source zone under different interaction relationships; those
are **distinct relationship opportunities** and must not be collapsed across
relationships, but they are **one physical zone** and must never be presented
as two.

Every structural and outcome table must distinguish:

```text
unique physical zones
relationship opportunities
touched relationship events
economic interaction episodes
```

Opportunity rows are never presented as unique zones.
