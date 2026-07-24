# Stage 2 Advancement Gate

Status: **LOCKED — NOT YET EVALUATED**

Each relationship R01–R05 is evaluated independently using primary
within-session matches. A relationship advances only if G01–G08 all pass.
`UNDERPOWERED` is distinct from `FAIL`.

## G01 — sample support

Pass requires at least 100 pooled matched pairs and at least 20 matched pairs
in at least three supplied development years. If the thresholds are missed,
G01 is `UNDERPOWERED`, not a negative-effect failure.

## G02 — primary pooled effect

For at least one control family, the pooled mean paired difference in
`inside_close_share_30` must be positive and its deterministic session-block
95% confidence interval must be strictly above zero.

## G03 — cross-year consistency

The primary mean paired effect must be positive in at least three supplied
development years. No year’s absolute contribution share, as defined in
`STAGE_02_STATISTICS_SPEC.md`, may exceed 50%.

## G04 — grid stability

For at least one allocation method and the control family satisfying G02, at
least six of the nine pooled ratio/prominence cells must be positive and the
median of all nine cell effects must be positive.

## G05 — secondary structural corroboration

At least two of mean-overlap share, midpoint crossings, lower path efficiency,
continuous residence, re-entry probability, and clean-exit time must meet the
locked corroboration rule, with no major contradictory metric.

## G06 — concentration robustness

The primary pooled effect must remain positive after each leave-one-year-out
calculation, after removing the largest 1% of absolute pair differences, and
after removing the five largest absolute economic episodes per year.

## G07 — match validity

Pass requires zero control reuse, no post-treatment matching feature, and no
major unresolved post-match covariate imbalance. Any absolute SMD above `0.20`
must be resolved or explicitly make this gate fail.

## G08 — no hidden pooled-only result

The relationship must not pass only by pooling incompatible interaction
classes, allocation methods, or duplicated parameter definitions. At minimum,
the supporting approach/touch strata, allocation method, grid neighborhood,
and episode-aware result must have coherent expected signs.

## Relationship and overall states

Every gate is recorded as `PASS`, `FAIL`, `BLOCKED`, or `UNDERPOWERED`, with
counts and evidence paths. A critical causal, data, matching, contract, or
implementation defect makes affected gates `BLOCKED` and the overall study
`INVALID`.

Overall verdicts are:

- `HVN_ACCEPTANCE_EFFECT = SUPPORTED`: at least one economically coherent
  relationship passes G01–G08 with no unresolved critical/high defect.
- `HVN_ACCEPTANCE_EFFECT = PARTIALLY_SUPPORTED`: a structural difference is
  present but is limited by relationship, method, touch class, control family,
  or one or more full advancement gates.
- `HVN_ACCEPTANCE_EFFECT = NOT_SUPPORTED`: samples are adequate but HVNs do
  not consistently differ from controls.
- `HVN_ACCEPTANCE_EFFECT = UNDERPOWERED`: no relationship has adequate
  matchable observations for a defensible conclusion.
- `HVN_ACCEPTANCE_EFFECT = INVALID`: a critical defect prevents
  interpretation.

Verdict ordering is: `INVALID` if a critical defect affects interpretation;
otherwise `SUPPORTED` if any relationship passes all gates; otherwise
`PARTIALLY_SUPPORTED` only when preregistered structural evidence with an
expected-sign session-block interval exists but full gates are not met;
otherwise `NOT_SUPPORTED` when at least one relationship passes G01 but lacks
such evidence; otherwise `UNDERPOWERED`.

No additional threshold search may upgrade a partial or underpowered result.
The exact next authorized action after reporting is to stop. Stage 3,
departure, MFE/MAE, grading, strategy, validation, holdout, and execution work
remain unauthorized.
