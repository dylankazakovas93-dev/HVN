# Stage 2 Statistical Specification

Status: **LOCKED BEFORE EMPIRICAL RESULTS**

Amended before empirical access by `STAGE_02_SPECIFICATION_AMENDMENT_01`.

## Estimands

All comparisons are paired treated minus matched control. Expected signs are:

| Metric | Expected sign |
|---|---:|
| inside-close share | positive |
| range-overlap share | positive |
| midpoint crossings | positive |
| path efficiency | negative |
| first inside-close probability | positive |
| continuous residence | positive |
| re-entry probability | positive |
| clean-exit time | positive |

The primary estimand is the mean paired difference in
`inside_close_share_30` from primary cross-session matches. C01 and C02 are
separate estimands. Secondary same-session results are descriptive sensitivity
evidence and do not enter advancement gates.

## Required reporting cells

For each relationship, control family, allocation method, bin ratio,
prominence threshold, and year, report:

```text
opportunities, touched nodes, treated events, control events, matched pairs,
match rate, mean paired difference, median paired difference, sample standard
deviation, IQR, expected-sign pair proportion, session-block 95% interval
```

Empty cells remain present with zero counts and null estimates. Pooled
development results aggregate authorized years only and retain sessions as
blocks. Binary outcomes use the mean paired indicator difference.

The median is the ordinary middle value or mean of two middle values. Quartiles
and IQR use exact type-7 interpolation. Sample standard deviation uses `n-1`
and is null for fewer than two pairs.

## Session-pair block bootstrap

The deterministic seed is `20260724` and the resample count is `10,000`.
The primary block is the stable
`(treated_interaction_session_date, control_interaction_session_date)` pair
within the reporting lane. A replicate draws the observed number of distinct
session-pair blocks with replacement and includes all matched pairs and all
definition-level rows in their economic episodes, including multiplicity. The
replicate statistic is pair-weighted, not a mean of block means.

A two-way sensitivity separately resamples treated-session and control-session
dependence. If a valid two-way clustered bootstrap is unavailable, only the
documented session-pair block bootstrap is authoritative and residual
cross-pair session dependence is a stated limitation.

Randomness uses a documented stable PRNG and stable sorted block order.
Intervals are the type-7 2.5th and 97.5th percentiles of valid replicate means.
No IID minute or event bootstrap is primary evidence. A confidence interval
alone cannot establish advancement.

## Grid stability

Within each relationship, allocation method, control family, and year (and
pooled development), the full ratio-by-prominence `3 x 3` grid reports:

- expected-sign cell count;
- median, minimum, and maximum primary effect;
- event counts per cell;
- horizontal/vertical adjacent pairs sharing the expected sign;
- largest cell contribution relative to the sum of absolute cell effects.

Stable neighborhood support requires at least six of nine positive primary
effects and a positive median across all nine. Missing/underpowered cells do
not count as positive and make the nine-cell median null if a cell estimate is
unavailable. One isolated cell is flagged when the largest absolute cell
effect exceeds 50% of the sum of absolute cell effects or it is the only
positive cell. The nine cells are a robustness neighborhood, not independent
tests.

## Year and concentration diagnostics

Every year is reported separately, including an explicit absent-year record.
Diagnostics include pooled development, every leave-one-year-out set, removal
of the largest 1% of absolute primary pair differences, removal of the five
largest absolute economic episodes per year, relationship, touch class, R02
prior-ETH-touch stratum, method, and separate `START_INSIDE` descriptions.

For `n` pairs, the largest-1% diagnostic removes
`ceil(0.01 * n)` pairs, sorted by descending absolute paired difference and
then pair ID. Episode contribution is the sum of member paired primary
differences after assigning each pair to the treated event’s economic episode;
the top five per year are sorted by descending absolute contribution and then
episode ID.

Year contribution is:

```text
contribution_y = sum(primary paired differences in year y)
absolute contribution share_y =
abs(contribution_y) / sum_y(abs(contribution_y))
```

This defines the G03 50% test. If the denominator is zero, contribution shares
are undefined and G03 cannot pass. A pooled mean is always recomputed from the
remaining pairs in each diagnostic.

## Structural corroboration

The six G05 candidates are mean overlap share, midpoint crossings, path
efficiency, continuous residence, re-entry, and clean-exit time. A metric
supports the interpretation when its primary cross-session pooled mean paired
difference has the expected sign and its session-block 95% interval does not
cross zero. A major contradiction is the opposite sign with an interval
excluding zero. Residence/exit comparisons use pairs for which both treated
and control outcomes are observed; binary re-entry uses paired observable
indicators. At least two supports and no major contradiction are required.

## Duplication and inference

Configuration cells use their own definition events. No combined p-value is
computed. Any pooled cross-configuration description is episode-weighted:
first compute the mean definition-level paired difference within each economic
episode, then average episode means so each episode has weight one. Such a
description cannot replace relationship/configuration gate evidence.

## Reproducibility

All results are derived directly from the saved match and forward ledgers.
Stable sorts precede aggregation. Decimal inputs remain exact through paired
differences; documented numerical conversion may be used only inside bootstrap
mean/quantile calculations and is verified against deterministic fixtures.
A byte-identical complete rerun is required.

## Amendment 02 — width reporting and the log-width term

`width_balance.csv` reports, per relationship and control family: mean treated
and control ATR-normalized width, mean absolute width difference, mean,
minimum and maximum width ratio, mean absolute log width ratio, pre-match and
post-match width standardized mean difference, whether the post-match absolute
width SMD is at most 0.20, and the width-caliper rejection count.
`matching_eligibility_funnel.csv` reports treated and control counts, matched
pairs, and each unmatched reason.

The log-width distance term uses `Decimal.ln()` under the ambient context
precision. Unlike the other distance components it is correctly rounded rather
than exact; ordering ties are broken by control event id, so matching remains
deterministic. All other statistical procedures, bootstrap construction and
episode weighting are unchanged.
