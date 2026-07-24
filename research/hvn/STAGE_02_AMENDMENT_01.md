# Stage 2 Specification Amendment 01

Status: **AUTHORIZED AND LOCKED BEFORE EMPIRICAL ACCESS**

Authorized: 2026-07-24  
Detected: 2026-07-24, after milestone `a966f74`  
Applies to: Stage 2 matching, inference, and G01–G08

## Defect

The original locked primary design simultaneously required:

```text
touch-time difference <= 60 minutes
```

and:

```text
no overlapping forward 120-minute window between the treated event
and selected control event
```

within the same interaction session. Two 120-minute half-open windows are
disjoint only when their start times differ by at least 120 minutes. No pair
could satisfy both restrictions. This is a preregistration defect, not an
empirical result.

The contradiction was detected before matching code, Stage 2 market-data
access, or empirical results. At detection, local and remote branch state was
`a966f74a3b5d27efe656f81887988514016bfa0c`, all 98 tests passed, the Stage 2
output directory did not exist, and the partition log contained no Stage 2
access.

## Amendment

```text
PRIMARY MATCHING = CROSS-SESSION MATCHING
SECONDARY MATCHING = SAME-SESSION DESCRIPTIVE MATCHING
```

Primary matching is deterministic greedy 1:1 matching across different
interaction-session dates. A treated and control event share relationship,
allocation method, bin ratio, prominence threshold, year, approach side, zone
width in bins, and control family. Their session dates must differ.

Primary calipers are interaction-window minute difference at most 60,
absolute 15-minute pre-touch displacement difference at most `0.75 ATR`,
interaction-open-distance difference at most `1.00 ATR`, and ATR-at-touch
proportional difference at most `0.20`.

```text
D =
1.0 * absolute interaction-window minute difference / 60
+ 1.0 * absolute pre-touch displacement difference in ATR
+ 1.0 * absolute pre-touch path-efficiency difference
+ 0.5 * absolute interaction-open-distance difference in ATR
+ 0.5 * absolute POC-distance difference in ATR
+ 1.0 * absolute ATR-at-touch proportional difference
```

Treated ordering is year, interaction-session date, touch time, profile ID,
node ID, then event ID. The final control tie-break is control event ID.
Controls are not reused within relationship/method/ratio/prominence/year/family.
Matching is independent for C01 and C02. No post-touch outcome is used. No
pairwise forward-window overlap test is required because dates differ.
Complete 15/30/60/120-minute labels remain mandatory.

Same-session matching is descriptive only. It requires the same source
profile, session, relationship, method, ratio, prominence, width, and approach
side, with interaction-window minute difference at most 60. It uses the
original distance without the ATR term. Forward-window overlap is permitted
and recorded separately at 15, 30, 60, and 120 minutes. Zones may not overlap
or touch, controls are not reused, and definition duplicates in one economic
episode are not paired. Same-session results cannot enter G01–G08.

## Inference and interpretation

Primary matched pairs receive stable IDs. The primary bootstrap resamples
complete session-pair blocks and preserves definition rows in their economic
episodes. A two-way treated-session/control-session sensitivity is also run
when valid; otherwise residual cross-pair session dependence is reported.

All G01–G08 evidence is calculated only from cross-session primary pairs.
Inadequate primary counts produce `UNDERPOWERED`; frozen calipers are not
relaxed.

Primary contrasts avoid same-path contamination but may retain unmeasured
cross-session regime differences. Matching covariates, year/configuration
strata, balance diagnostics, and session-block sensitivity mitigate but cannot
eliminate that limitation. Same-session estimates are correlated descriptive
corroboration, not counterfactual evidence.

