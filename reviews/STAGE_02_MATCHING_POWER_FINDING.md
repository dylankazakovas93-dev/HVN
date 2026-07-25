# Stage 2 Matching-Power Finding

Status: **BLOCKED — REQUIRES AN AUTHORIZED SPECIFICATION AMENDMENT**

Detected: 2026-07-25, on the first aggregation run over all five completed
development partitions, at `3da695c`.

## F-07 — Primary matching is structurally underpowered

The first authorized aggregation produced **42 primary cross-session pairs**
from 3,235 treated events with complete covariates and 532,653 control events.
Every gate G01–G08 returned `UNDERPOWERED` for every relationship R01–R05.
Per-relationship match rates run from 0.2% to 2.1%, and the largest number of
unique primary episodes behind any relationship is ten.

This is not an implementation defect. Amendment 01 requires that a treated and
a control event "share relationship, allocation method, bin ratio, prominence
threshold, year, approach side, zone width in bins, and control family". The
matcher enforces exactly that. The locked design is what produces the result.

## Cause

Exact-equality strata fragment the sample faster than the sample grows. The
3,235 treated events fall into 3,092 distinct strata — about 1.05 treated
events per stratum. Controls occupy 5,675 strata, and only 1,658 strata contain
both a treated and a control event.

Disposition of every treated event, in order of elimination:

| Outcome | Treated events |
|---|---|
| No control anywhere in its stratum | 1,452 |
| Stratum has controls, all same-session | 1,273 |
| Reached caliper evaluation | ~510 |
| At least one control passes all four calipers | 35 |

Two thirds of treated events are eliminated before any caliper is evaluated.
The calipers are not the binding constraint; the strata are.

## Which stratum term is responsible

Counting only how many treated events retain at least one eligible
cross-session control. These are eligibility counts, deliberately not outcome
metrics, so that the choice below is not made against results:

| Stratum definition | Treated with >= 1 eligible control |
|---|---|
| LOCKED: zone width in bins + year | 35 |
| drop zone width in bins, keep year | 1,100 |
| keep zone width in bins, drop year | 101 |
| drop both | 1,727 |

`zone_width_bins` is responsible. It is an integer zone width, so requiring
exact equality partitions events into as many strata as there are widths, and
it interacts multiplicatively with the other six terms. Dropping it alone
restores roughly a thirty-fold increase in eligible treated events.

## Why this is not a bug fix

Amendment 01 resolved a logical impossibility: the original same-session rules
could not produce any pair at all. The amended cross-session design is
satisfiable, but in practice yields 42 pairs, which cannot support G01-G08.
The two defects are the same class — a preregistered matching rule that cannot
deliver the sample its own gates require — and the second was not visible until
real partitions existed.

Changing a stratum term after observing that the locked one is underpowered is
a material specification change under section 13. It requires explicit
authorization, a recorded generation increment, and an entry in the trial
registry. It must not be applied as a correction by the implementation agent.

## Recorded state

The underpowered aggregation is retained in full as the authoritative result of
the locked specification: `gate_results.csv`, `match_quality.csv`,
`paired_primary_results.csv`, `year_results.csv`, `concentration_results.csv`
and the accompanying manifest. No gate was reinterpreted, and no caliper or
stratum was altered to obtain a different outcome.

Secondary same-session matching produced 2,370 pairs. It is descriptive under
Amendment 01 and cannot substitute for the primary design.
