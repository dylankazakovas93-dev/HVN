# Generation 4 Statistics Specification

Status: **LOCKED BEFORE ANY GENERATION 4 FORWARD OUTCOME WAS INSPECTED**

## 1. Predefined strength bands

Frozen before any Generation 4 outcome is read. Reported separately; the
strongest-performing band is never renamed a strategy.

```text
peak smoothed activity percentile  95.0-97.0 | 97.0-98.5 | 98.5-99.5 | 99.5-100.0
peak smoothed activity density     1.50-1.75 | 1.75-2.25 | >=2.25
peak-to-valley ratio               1.10-1.25 | 1.25-1.50 | >=1.50
zone volume density                1.25-1.50 | 1.50-2.00 | >=2.00
zone TPO density                   1.00-1.25 | 1.25-1.50 | >=1.50
zone composite activity density    1.35-1.60 | 1.60-2.00 | >=2.00
zone width in ATR                  0.10-0.20 | 0.20-0.35 | 0.35-0.50 | 0.50-0.75
value-area location                INSIDE_VALUE | VALUE_EDGE | OUTSIDE_VALUE
touch class                        WICK_ONLY_SAME_SIDE | CLOSE_INSIDE | CROSS_THROUGH
zone class                         POC_HVN_ZONE | NONPOC_HVN_ZONE
```

Zone width is a predefined stratum because Generation 4 zones vary in width by
construction; width-conditional results must be inspected before any pooled
width-insensitive claim is made.

## 2. Reporting requirements

Continuous positive metrics: treated mean, control mean, treated/control ratio,
absolute mean difference, median, interquartile range, 95% confidence interval.

Probabilities: treated probability, control probability, risk ratio,
percentage-point difference, 95% confidence interval.

Counts: opportunities, touches, raw configuration rows, unique physical zones,
unique economic episodes, effective matched episodes.

Every principal table reports treated N, control N, unique physical zones,
unique episodes, treated value, control value, ratio, absolute difference,
95% CI and full-year expected-sign count. POC and non-POC are reported
separately. Low sample sizes are never hidden behind pooled rows.

Every ratio is explained in plain English. Raw row dumps and bare p-values are
not an acceptable substitute for interpretation.

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

For each primary outcome, test whether increasing zone strength produces a
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

A coherent, broadly monotonic, year-consistent response is required to call
dose-response supportive. **One isolated positive band is not sufficient.**

Because zone width is itself a strength-adjacent quantity, every dose-response
table over an activity band must also be reported within width strata, so that
a width artefact cannot be reported as an activity effect.

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
each full year in turn; each relationship in turn; each profile family in turn;
each zone-width stratum in turn. Reported as whether sign and practical
magnitude survive.

## 7. Numerical audit

For each accepted development partition: reconcile profile counts, zone counts,
opportunity and event counts, and every metric-ledger multiplier; and
independently recompute at least **20 real events** from source bars.

Across the final study, independently reconcile at least **100 events**
covering all full years, all relationships R01–R05, POC and non-POC,
inside/edge/outside value, approach from above and below, all touch classes,
and both C01 and C02.

Reconciliation is code-level and numerical. No charts are produced.
