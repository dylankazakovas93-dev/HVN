# Generation 3 Statistics Specification

Status: **LOCKED BEFORE ANY FORWARD OUTCOME WAS INSPECTED**

## 1. Predefined strength bands

Frozen before any outcome is read. Reported separately; the strongest-performing
band is never renamed a strategy.

```text
peak activity percentile   90.0-95.0 | 95.0-97.5 | 97.5-99.0 | 99.0-100.0
local activity prominence  1.10-1.20 | 1.20-1.35 | >=1.35
zone activity density      1.35-1.50 | 1.50-2.00 | >=2.00
zone TPO density           1.00-1.25 | 1.25-1.50 | >=1.50
value-area location        INSIDE_VALUE | VALUE_EDGE | OUTSIDE_VALUE
touch class                WICK_ONLY_SAME_SIDE | CLOSE_INSIDE | CROSS_THROUGH
```

## 2. Reporting requirements

Continuous positive metrics: treated mean, control mean, treated/control ratio,
absolute mean difference, median, interquartile range, 95% confidence interval.

Probabilities: treated probability, control probability, risk ratio,
percentage-point difference, 95% confidence interval.

Counts: raw configuration rows, unique physical nodes, unique economic
episodes, effective matched episodes.

Every principal table reports treated N, control N, unique episodes, treated
value, control value, ratio, absolute difference, 95% CI and full-year sign
count. Low sample sizes are never hidden behind pooled rows.

## 3. Primary uncertainty procedure

```text
deterministic session-date block bootstrap
10,000 resamples
seed 20260727
```

Entire economic episodes are preserved within blocks. **IID row bootstrap is
not primary inference.** Where feasible a two-way session-pair clustered
sensitivity analysis is added for cross-session matched pairs.

P-values are secondary only. Statistical significance is never presented
without effect size and sample size.

## 4. Dose-response

For each primary outcome, test whether increasing node strength produces a
monotonic response across the ordered bands. Primary outcomes:

```text
inside_close_share_30
post_touch_activity_concentration_ratio_30
normalized residence R_T_30
probability of at least one rotation within 30 minutes
same-side rejection probability within 60 minutes
opposite-side traversal probability within 60 minutes
```

Per band: sample size, treated mean or probability, control value,
treated/control ratio, absolute difference, 95% CI, year-by-year direction.

A stricter future detector is justified only by a coherent, broadly monotonic,
year-consistent response. **One isolated positive band is not sufficient.**

## 5. Year consistency

Reported separately for 2019, 2021, 2023, 2025 and partial 2026. Primary
full-year consistency uses only the four complete years.

Per primary metric: pooled effect, each full-year effect, partial-2026 effect,
number of full years with the expected sign, leave-one-full-year-out results,
and largest year contribution. Any result where one full year contributes more
than 50% of the pooled effect is flagged.

A large pooled sample does not compensate for inconsistent years.

## 6. Concentration robustness

Primary results are repeated after removing: the largest 1% of economic
episodes by absolute effect; the five largest-effect episodes per full year;
each full year in turn; each relationship in turn; each profile family in turn.
Reported as whether sign and practical magnitude survive.
