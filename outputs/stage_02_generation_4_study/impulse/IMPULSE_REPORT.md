# Directional impulse away from HVN zones — continuation or reversion?

**Does an abnormal directional volume surge leaving an HVN zone predict
continuation?**

**No.** The consistent cells are fewer than chance alone would produce.

Producing code `82e24c2`. Four full development years, 12,566 first-touch events
carrying a computed impulse, treated beside both control arms.

## 1. The formulas, as implemented

```text
DirectionalDisplacement_d = sum(max(0, d*(C_t - C_t-1))) / ATR
DirectionalVolume_d       = sum(V_t * 1[d*(C_t - C_t-1) > 0]) / seasonal expected volume
Efficiency_d              = |C_now - C_start| / sum(|C_t - C_t-1|)
```

Impulse window: 15 completed bars after the touch bar. Direction: the side
carrying the larger summed close-to-close movement over that window. Outcome:
continuation or reversion 15, 30 and 60 bars **after the impulse window closes**,
so nothing used to classify an event overlaps the outcome it predicts.

**The seasonal volume baseline works.** Median volume at the same minute of day
over the 20 trailing sessions strictly prior. Coverage is 98.2% to 99.3% of
events across every arm, so the volume buckets are populated by a real
comparison, not by a fallback.

## 2. Unconditional continuation — the number to beat

| population | arm | 15b | 30b | 60b |
|---|---|---|---|---|
| non-POC | treated | 50.29% | 49.05% | 49.85% |
| non-POC | C02 | 48.46% | 51.19% | 53.31% |
| POC | treated | 51.58% | 50.90% | 52.01% |
| POC | C02 | 50.79% | 49.39% | 50.23% |

A coin flip, in every arm, at every horizon.

## 3. Conditioning on the impulse

At 30 bars, against the activity-matched control:

**By directional volume**

| population | volume | n | treated | control | diff | years |
|---|---|---|---|---|---|---|
| non-POC | below normal | 729 | 48.70% | 49.77% | −1.07 | 3/4 |
| non-POC | elevated | 112 | 47.32% | 53.91% | −6.59 | 4/4 |
| non-POC | extreme | 218 | 48.17% | 53.37% | −5.20 | 2/4 |
| POC | below normal | 1809 | 49.47% | 48.40% | +1.07 | 3/4 |
| POC | extreme | 500 | 54.20% | 51.34% | +2.86 | 3/4 |

**By efficiency**

| population | efficiency | n | treated | control | diff | years |
|---|---|---|---|---|---|---|
| non-POC | medium | 395 | 47.59% | 51.09% | −3.50 | 3/4 |
| non-POC | high | 77 | 42.86% | 57.33% | −14.47 | 4/4 |
| POC | medium | 966 | 51.35% | 48.61% | +2.74 | 4/4 |
| POC | high | 229 | 54.15% | 56.77% | −2.62 | 3/4 |

**By dwell** — every cell within 2 points of its control except two small ones.

Non-POC differences run negative and POC positive almost throughout. That
opposition looks like structure. Section 5 explains why it is not evidence.

## 4. The displacement bucket is degenerate

```text
non-POC   lt_0.5: 1    0.5-1.0: 14   1.0-1.5: 27   gt_1.5: 1,322
POC       lt_0.5: 0    0.5-1.0: 14   1.0-1.5: 35   gt_1.5: 3,076
```

**97% of events fall in one bucket.** Fifteen bars of summed directional movement
against a one-minute ATR near 2 points essentially always exceeds 1.5 ATR. The
bucket edges were written for a scale this project does not have — the same
mismatch that broke the width rules and the 3/5 ATR thresholds.

Displacement therefore contributes nothing to any result above. Any joint cell
reading `gt_1.5` is really a volume-by-efficiency cell.

## 5. Why the consistent cells are not a finding

Across volume × displacement × efficiency, **135 cells** were tested against the
primary control at three horizons. Applying the pre-declared filter — the sign
agrees in at least 3 of 4 years, and both arms carry at least 30 events —
**38 cells pass**.

For a cell with no real effect, each year's sign matches the pooled sign with
probability one half, so:

```text
P(at least 3 of 4 years agree | no effect) = 5/16 = 0.3125
expected passing cells from noise alone    = 135 x 0.3125 = 42.2
observed passing cells                     = 38
```

**Fewer cells survived than chance predicts.** The 38 "consistent" cells are not
merely unproven — they are exactly the residue a null produces at this cell
count. Picking the best of them (non-POC / normal volume / high efficiency,
−22.29 pp at 15 bars, n=32) would be selecting a coin-flip run.

That is the whole result. It does not depend on any judgement about effect size.

## 6. What was ruled out, precisely

- Abnormal directional volume leaving an HVN zone does not predict continuation,
  at 15, 30 or 60 bars, in either population, against either control.
- High path efficiency does not predict continuation either.
- Dwell before the impulse does not predict continuation.
- No combination of the three does, beyond the chance rate.

## 7. What is not ruled out

- **Displacement was never actually tested.** Its buckets collapsed to one value.
  A rescaled version — buckets set from the observed distribution rather than
  assumed — remains untested.
- Aggressor side is still invisible. Displacement and efficiency compensate for
  that as far as OHLCV allows; they do not replace it.
- No confidence intervals or clustered inference were computed. Given the chance
  arithmetic above they would not change the reading, and they have not been run.
- The impulse window is fixed at 15 bars. Shorter or longer windows are untested.

## 8. Status

This is a negative result on a pre-declared bucket scheme, with the failure mode
identified precisely rather than left as "no signal". Every cell is written to
`by_volume_displacement_efficiency.csv`, winners and losers, alongside the
marginal tables and the seasonal coverage check.

No strategy, entry, stop, target or profitability figure was produced.

---

# Addendum — displacement re-tested on calibrated buckets

The frozen buckets put 97% of events in one cell, so displacement was never
tested. Re-cut into quartiles taken from the **control** arm's own distribution,
which carries no treatment and so cannot be shaped by the treated result. The
raw value was already in the ledgers, so this is a re-cut, not a re-run.

## Cuts

```text
non-POC   control n=1,247   quartile cuts at 5.42 / 9.63 / 16.30 ATR
POC       control n=2,242   quartile cuts at 6.41 / 12.02 / 23.36 ATR
```

The buckets now span a real range: median displacement runs from 3.17 to 23.30
ATR (non-POC) and 3.92 to 32.23 ATR (POC). A tenfold difference in impulse size
between the smallest and largest quartile.

## Continuation is flat across that range

Treated arm, by quartile:

| population | horizon | Q1 | Q2 | Q3 | Q4 | spread | monotonic |
|---|---|---|---|---|---|---|---|
| non-POC | 15b | 51.9% | 50.7% | 49.4% | 49.1% | 2.8 pp | yes |
| non-POC | 30b | 48.1% | 51.3% | 50.0% | 46.7% | 4.6 pp | no |
| non-POC | 60b | 48.5% | 52.6% | 50.6% | 47.6% | 5.0 pp | no |
| POC | 15b | 48.7% | 53.2% | 52.0% | 52.5% | 4.5 pp | no |
| POC | 30b | 51.0% | 52.1% | 49.5% | 50.9% | 2.5 pp | no |
| POC | 60b | 50.9% | 51.8% | 51.3% | 54.1% | 3.2 pp | no |

**A tenfold change in impulse size moves continuation by under five points, and
not monotonically in five of six rows.** The one monotonic row runs the wrong
way for a continuation story: larger impulses continue slightly *less*.

## Why the raw pass count looked encouraging, and why it is not

Sixteen of twenty-four cells met the consistency filter against 7.5 expected
from noise. Two things account for that, and neither is displacement.

**The cells are not independent.** The three horizons on a given quartile are
the same events over overlapping windows. There are 8 independent quartile
cells, not 24, so the noise expectation is 2.5. **Only 1 of 8 quartile cells is
consistent at all three horizons** — below chance.

**The surviving differences are a population-level offset.** Non-POC treated
continues 1.30 pp less than its control on average and POC 1.39 pp more, with
8 of 12 and 9 of 12 cells sharing their population's sign. That offset sits at
the same level in every quartile. It is a property of the two populations, not
information carried by displacement.

## Conclusion

Displacement carries no information about whether price continues or reverts
after leaving an HVN zone. All three impulse terms have now been tested on
buckets that actually discriminate, and all three are flat.
