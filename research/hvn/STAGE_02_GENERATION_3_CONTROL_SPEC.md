# Generation 3 Control and Matching Specification

Status: **LOCKED BEFORE ANY FORWARD OUTCOME WAS INSPECTED**

## 1. Control families

Constructed by the accepted Pilot V4 control code, from frozen structural
information only.

```text
C01_NEUTRAL           does an HVN behave differently from an ordinary
                      neutral profile location?
C02_ACTIVITY_MATCHED  does local-maximum geometry matter after controlling for
                      the general amount of volume and time-at-price?
```

**`C02_ACTIVITY_MATCHED` is the primary control family.** C01 is supporting
evidence.

Controls may not overlap the volume POC, any accepted node, any broad composite
plateau, another selected control in the same lane, or invalid profile space.
Controls are **not** required to be composite local maxima — that is the point
of C02.

Complete control-opportunity ledgers are written, **including untouched
controls**. Retaining only controls that later produce convenient events is
forbidden.

## 2. Cross-session conditional matching

The over-fragmented exact matching of earlier Stage 2 generations is not
repeated. Exact match on **six** keys only:

```text
data_year
relationship
source profile family
control family
approach side
value-area location class
```

Value-area location classes: `INSIDE_VALUE`, `VALUE_EDGE`, `OUTSIDE_VALUE`,
where `VALUE_EDGE` means the node or control overlaps volume VAH or VAL.

Continuous calipers:

```text
touch-time-of-day difference        <= 60 minutes
ATR proportional difference         <= 20%
pre-touch displacement difference   <= 0.75 ATR
interaction-open distance difference<= 1.00 ATR
zone-width ratio                    within [0.67, 1.50]
distance-to-volume-POC difference   <= 1.00 ATR
```

Deterministic greedy 1:1 nearest-neighbour matching, no control reuse within a
lane. The matching distance sums normalized terms for touch time, ATR,
pre-touch displacement, pre-touch path efficiency, interaction-open distance,
zone width and distance to volume POC. **No post-touch outcome enters
eligibility or distance.**

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

Configuration-level nodes are not independent. Events cluster into one economic
episode when all hold:

```text
same contract
same relationship
same interaction session
touch times within 5 minutes
node price intervals overlap by >= 50% of the narrower interval
same approach side
```

Reported: configuration rows, unique physical nodes, touched nodes, unique
economic episodes, matched economic episodes.

**Primary inference operates at, or clusters by, the economic-episode level.**
Selecting the best-performing configuration within an episode is forbidden. All
definition rows are used only for stability analysis.

R01 and R02 share the prior-RTH source profile; events from the same physical
node under different relationships are **distinct** and must not be collapsed
across relationships.
