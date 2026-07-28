# Generation 4 HVN Zone Study — Development Result

**Do causally frozen, smoothed NQ HVN zones measurably affect price acceptance,
rotation or activity after their first return?**

On the evidence below: **no.** Across five development partitions, HVN zones
behave like width-matched ordinary zones on every metric measured. The largest
consistent difference is a 1.27 percentage-point touch-rate edge for POC zones.

## 1. Scope and provenance

```text
full development years      2019, 2021, 2023, 2025
supporting                  partial 2026
zone definition             STAGE_02_GENERATION_4_ZONE_SPEC + AMENDMENT_01
metrics                     AMENDMENT_02
producing code sha          15037c4
forbidden-year rows         0 in every partition
```

| partition | bars | profiles | intervals | first touches | re-touches |
|---|---|---|---|---|---|
| 2019 | 430,528 | 895 | 3,890 | 2,602 | 21,009 |
| 2021 | 454,877 | 963 | 4,908 | 3,383 | 25,803 |
| 2023 | 456,312 | 949 | 4,859 | 3,228 | 26,423 |
| 2025 | 456,913 | 961 | 4,871 | 3,366 | 27,677 |
| partial 2026 | 199,294 | 420 | 2,102 | 1,403 | 10,710 |

```text
unique physical zones        5,822
intervals (treated+control) 20,630
first touches               13,982   (12,579 in the four full years)
```

Sample-support gates G4-S15 and G4-S16 were **waived by principal decision**,
not passed. 2019 produced 248 unique non-POC zones against a threshold of 300,
and R04 reached 16 opportunities against 20. R04 is labelled `UNDERPOWERED`
wherever it appears.

## 2. Touch propensity — are HVN zones visited more often?

Pooled over the four full years, against the primary control
`C02_ACTIVITY_MATCHED`:

| population | treated | control | difference | ratio | full years favouring |
|---|---|---|---|---|---|
| non-POC | 61.25% | 61.78% | **-0.53 pp** | 0.991 | 1 of 4 |
| POC | 71.98% | 70.71% | **+1.27 pp** | 1.018 | **4 of 4** |

Against `C01_NEUTRAL`: non-POC +0.40 pp (3 of 4 years), POC +0.34 pp (2 of 4).

The POC touch-rate edge is the **only** directionally consistent result in this
study. It is also small: 1.27 percentage points on a 71% base, a 1.8% relative
difference. A non-POC HVN is touched slightly *less* often than its
activity-matched control.

## 3. Displacement — bars to travel 3 and 5 ATR from the zone edge

| threshold | population | reached (T / C) | median bars (T / C) | full years treated faster |
|---|---|---|---|---|
| 3 ATR | non-POC | 99.50% / 99.36% | 3 / 3 | 1 of 4 |
| 3 ATR | POC | 99.62% / 99.73% | 2 / 2 | 1 of 4 |
| 5 ATR | non-POC | 97.56% / 97.20% | 9 / 9 | 0 of 4 |
| 5 ATR | POC | 98.58% / 98.26% | 6 / 5 | 0 of 4 |

Identical medians, identical reach rates. Treated is faster in at most one year
of four at either threshold.

**These two thresholds are saturated and cannot discriminate.** 99% of events
reach 3 ATR and 98% reach 5 ATR. The frozen ATR is a one-minute ATR with a
median near 1.9 points, so 3 ATR is about 6 points and 5 ATR about 10 — distances
NQ covers many times over in a single session. The question the metric actually
answers is "did price move six points at some point today", and the answer is
almost always yes.

A related artefact: 22-35% of events reach 3 ATR on the **first forward bar**.
That is usually not an explosive departure. It is a brief wick touch after which
price simply remains where it already was, several points away. Both effects
apply identically to treated and control zones, so they do not bias the
comparison — but they do mean the displacement family, as specified, has little
power to detect a difference that exists.

## 4. Envelope residence — minutes inside ±3 ATR

For first touches whose touch bar closed within 1 ATR of the zone:

| population | control | median (T / C) | mean (T / C) | ratio | full years treated longer |
|---|---|---|---|---|---|
| non-POC | C01 | 5m / 5m | 32.2 / 32.1 | 1.003 | 0 of 4 |
| non-POC | C02 | 5m / 5m | 32.2 / 30.6 | 1.052 | 1 of 4 |
| POC | C01 | 4m / 4m | 26.1 / 26.1 | 1.000 | 2 of 4 |
| POC | C02 | 4m / 4m | 26.1 / 23.5 | 1.111 | 1 of 4 |

Medians are identical to the minute. The mean ratios above one are driven by a
long right tail, and they do not survive year consistency: treated is longer in
at most two of four years in every row.

## 5. Continuation and return

Thirty minutes after crossing 3 ATR, against `C02_ACTIVITY_MATCHED`:

| population | approach | treated continued | control continued | difference |
|---|---|---|---|---|
| non-POC | from below | 51.78% | 52.78% | -1.00 pp |
| non-POC | from above | 45.98% | 45.29% | +0.69 pp |
| POC | from below | 50.38% | 50.87% | -0.49 pp |
| POC | from above | 50.57% | 50.53% | +0.04 pp |

Every cell is within roughly one point of a coin flip, and the differences run
in both directions. The 5 ATR threshold gives the same picture, with the largest
difference being -2.32 pp.

**Return inside the zone after a 3 ATR move: 83-88% of the time.** That is a
striking absolute number and the strongest descriptive fact in the study — but
control zones return at 84-86%. It is a property of one-minute NQ price action
around any narrow price region, not a property of high-volume nodes.

## 6. Anchor and session structure

Splitting each anchor by interaction session reveals large differences in
median bars to 3 ATR — from 1 bar for `R03` at `RTH_OPEN` to 75 bars for `R01`
in `ETH_EVENING`.

This is time-of-day volatility, not zone structure. The control zones move on
exactly the same schedule in every cell. The session split is worth having on
record, and it says nothing about the HVN hypothesis.

`R04` cells outside `RTH_OPEN` carry 10 to 17 events and are marked
`UNDERPOWERED`; their numbers are reported but not interpreted.

## 7. What this study does and does not establish

**Established:** across 5,822 unique physical zones, 12,579 first touches in
four full years, and five metric families, causally frozen smoothed HVN zones
are not distinguishable from width-matched ordinary zones drawn from the same
frozen profiles. The single consistent exception is a 1.27 pp POC touch-rate
edge with 4-of-4 year consistency, which is real but small.

**Not established, and not claimed:** this run does **not** compute the
co-primary hypotheses defined in `STAGE_02_GENERATION_4_GATE.md`. H1
(30-minute inside-close share) and H2 (30-minute composite volume-TPO
concentration ratio) were not measured here; the Amendment 02 displacement
family was measured instead. **No formal `SUPPORTED` / `NOT_SUPPORTED` verdict
against the locked gate can therefore be rendered from this run.** Calling the
mechanism refuted on this evidence would overstate what was computed.

What can be said is narrower and still substantial: on touch propensity,
displacement, envelope residence, continuation and return, there is no effect.

**Also not established:** no bootstrap confidence interval, episode clustering,
dose-response or leave-one-year-out analysis has been run. The year-consistency
counts above are the only robustness evidence so far. Given that nearly every
point estimate sits within a percentage point of its control, formal intervals
are unlikely to change the reading, but they have not been computed and are not
being asserted.

## 8. Known limitations

- The 3 and 5 ATR displacement thresholds saturate (section 3) and have little
  discriminating power as specified.
- The one-minute OHLCV proxy allocates bar volume uniformly across occupied
  ticks. No transaction-level volume-at-price precision is claimed.
- Sample-support gates were waived, not met.
- `R04` is underpowered throughout.
- Partial 2026 is supporting evidence only and enters no year-consistency count.

## 9. Next authorized action

Report the result and stop. No strategy, entry, stop, target or profitability
figure has been produced at any point, and none is authorized. If the
displacement family is to be re-cut at a scale that can discriminate, that is a
new specification decision to be made before any further outcome is opened.
