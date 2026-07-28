# Generation 4 Amendment 02 — Interaction and displacement metrics

Status: **LOCKED BEFORE ANY GENERATION 4 FORWARD OUTCOME WAS INSPECTED**

Authorized by the principal. Adds a displacement-and-continuation family to the
Generation 4 outcome specification, promotes POC zones to a co-equal reported
population, and adds interaction-session stratification. Nothing in
`STAGE_02_GENERATION_4_OUTCOME_SPEC.md` is removed; this amendment is additive
except where stated.

No Generation 4 forward outcome existed when this was written. None was
computed, loaded or opened.

## 1. Sample-support gates

The principal has ruled on the 2019 structural pilot
(`outputs/stage_02_generation_4_hvn_zones_pilot_a01/`, code `3a2fc20`):

```text
G4-S15  248 unique non-POC zones against a threshold of 300   -> WAIVED
G4-S16  R04 at 16 non-POC opportunities against a threshold of 20 -> WAIVED for R04
```

The waiver is recorded as a principal decision, not as a passing result. The
stated grounds: the 300 threshold was set without reference to the detector's
actual yield, and a high-quality HVN appearing several times a day is
implausible on its face, so roughly one per trading day is the expected order of
magnitude rather than a shortfall. Study power comes from five partitions
(~1,200 non-POC and ~4,400 POC zones), not from 2019 alone.

**No detector constant was changed to obtain this.** The waiver moves a
study-power gate, not a threshold inside the zone definition. Every report must
state that G4-S15 and G4-S16 were waived by decision and show the observed
counts beside the original thresholds.

R04 remains labelled `UNDERPOWERED` in every table in which it appears.

## 2. POC zones are a co-equal population

POC zones are analysed and reported in full, with the same metric set, the same
controls and the same stratification as non-POC zones. POC and non-POC results
are never pooled into a single headline figure.

The 2019 pilot yields 891 POC zones against 248 non-POC, so the POC population
is the larger of the two and is not a secondary check.

## 3. Interaction sessions

Every event carries an interaction-session label, assigned from the touch time
in America/New_York:

```text
ETH_EVENING     18:00 - 00:00
ETH_OVERNIGHT   00:00 - 09:30
RTH_OPEN        09:30 - 10:30
RTH_MORNING     10:30 - 12:00
RTH_MIDDAY      12:00 - 14:00
RTH_AFTERNOON   14:00 - 16:00
```

Every primary table is produced **both** per anchor (profile family and
relationship) split by interaction session, **and** per anchor combined across
sessions. Neither view replaces the other. A session cell with fewer than 30
matched episodes is labelled `UNDERPOWERED` and its numbers are shown but not
interpreted.

## 4. Touch population

Reported before any conditional metric:

```text
zones frozen
zones never touched
zones touched at least once
first touches
re-touches  (second and subsequent touches, counted separately)
touches per touched zone: mean, median, p90, maximum
minutes from interaction open to first touch
```

The untouched count is mandatory in every touch table. All conditional metrics
below are computed on **first touches**; re-touches are reported as a separate
population and never pooled into the first-touch figures.

## 5. Displacement metrics (new)

Distances are measured from the **nearest zone edge**, in units of
`ATR_1m_at_touch`. Measurement begins at the **first completed bar after the
touch bar closes**; the touch bar itself never contributes.

```text
D01  bars_to_3atr    completed bars until price first reaches 3 ATR from the
                     zone edge, using bar high and low
D02  bars_to_5atr    the same at 5 ATR
D03  direction_at_3atr, direction_at_5atr
                     UP or DOWN, the side on which the threshold was reached
```

`D01` and `D02` are reported as a **discrete distribution**, exactly as
requested: the share of events reaching the threshold on bar 1, bar 2, bar 3 and
so on, then bucketed 6-10, 11-20, 21-60, 61-120, plus an explicit
`never_reached` share. Shares sum to 100%. Median and p90 bar counts accompany
the distribution.

## 6. Envelope residence (new)

```text
D04  For first touches whose touch-bar close lies within 1 ATR of the zone:
     minutes until price first leaves a +/- 3 ATR envelope centred on the zone.
     Reported as mean, median, p25, p75, p90 and a never-left share.
```

The 1 ATR condition is evaluated on the touch bar's close, which is known at the
touch-bar close and is therefore causal.

## 7. Continuation (new)

```text
D05  Of events that reached 3 ATR, the share whose price is still further from
     the zone, on the same side, 15, 30 and 60 minutes after the crossing bar.
D06  The same for events that reached 5 ATR.
D07  Reversal share: the share that returned inside the zone after reaching the
     threshold, and minutes to that return.
```

`D05` and `D06` are reported **split by approach side** (`APPROACH_FROM_BELOW`,
`APPROACH_FROM_ABOVE`). Pooling the two sides averages opposing directions
toward 50% and is forbidden as a headline figure.

## 8. Censoring

An event whose forward window is cut short by the end of its interaction session
is **censored, not dropped**. Every displacement, envelope and continuation
table reports:

```text
events evaluated
events censored before the threshold could be reached
censored share
```

Silently dropping censored events biases every result toward fast movers. The
`never_reached` share must be reported separately from the censored share; they
are different facts.

## 9. Controls

Every metric in sections 4 through 7 is reported for treated zones **and** for
their width-matched controls, side by side, with the treated/control ratio and
the absolute difference. A displacement or continuation figure without its
control is not a result and must not be presented as one.

`C02_ACTIVITY_MATCHED` remains the primary control family. Control zones are
drawn to the same width distribution as the treated zones, as required by
`STAGE_02_GENERATION_4_CONTROL_SPEC.md`, so that a wider zone cannot manufacture
an apparent effect.

## 10. Framing

These are descriptive market-structure measurements. They are displacement,
traverse time, residence and continuation shares. They are **not** entries,
stops, targets, profits, losses, MFE or MAE, and no execution assumption exists
anywhere in this study. That constraint is unchanged.
