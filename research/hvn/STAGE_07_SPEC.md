# Stage 7 — tiered levels on one-second data, measured as a race

Frozen before any outcome was computed. Nothing below may be changed once the
in-sample run starts; a change means a new stage, not an amendment to this one.

## Why this stage exists

Stage 6 was supposed to answer "does the reversal result survive accurate
volume". It could not, for two independent reasons, both found afterwards.

**One.** Of nine level sources, only the trailing composite read the one-second
file. The hourly VP, both developing profiles, the prior RTH profile and all
four VWAPs were built from one-minute bars with volume smeared uniformly across
each bar's range — the exact construction Stage 6 was meant to replace. The
comparison was never made.

**Two.** The outcome was width-biased. `REVERSED` meant "the close is past the
near edge of the band", `BROKE_THROUGH` meant "the close is past the far edge".
Price taps the near edge, so a reversal is a few ticks and a break must cross
the whole band. Reversal rate therefore tracked band width, not level quality:

    band 0.0-0.7 ATR wide    53.65% "reversed"
    band 2.0-3.1 ATR wide    74.82% "reversed"

Band width rises with the number of stacked levels, which is the axis under
test, so the bias pointed straight at the result being looked for. The absolute
reversal rates from Stages 5 and 6 are void. Only the within-stratum
stacked-minus-single differences from those stages mean anything, and those were
flat.

## Inputs

One-second OHLCV, GLBX.MDP3, front month only, collapsed to **half-hour
buckets** (`scripts/build_buckets.py`). Thirty minutes rather than an hour
because the cash session opens at 09:30; an hourly grid would silently redefine
two of the five profile windows.

Each bucket holds `tick -> volume`, `tick -> seconds`, a bar count, and the
three volume-weighted price moments. Every profile window and every anchored
VWAP in this stage is an exact sum of buckets. **All nine sources read them.**

## Levels

The same nine sources and the same kinds as Stage 4-6:

    P1 rolling composite     P6 VWAP globex
    P2 single hour           P7 VWAP cash
    P3 globex developing     P8 VWAP prior RTH
    P4 cash developing       P9 VWAP rolling
    P5 prior RTH

Kinds: high node, low node inside/outside value, value edge, sigma edge, POC,
time-at-price extreme, VWAP band (sigma and percentage).

## Tiers

Three frozen definitions, in `src/hvn/tiers.py`. Every gate is an interpretable
quantity — a percentile of smoothed activity, a multiple of the profile mean, a
share of traded ticks, a band multiple — not a fitted constant.

**Calibrated on frequency alone**, by `scripts/calibrate_tiers.py`, which is
structurally unable to compute an outcome. Measured over 8 sessions × ~14
anchors before freezing:

| tier | levels/anchor | clusters/anchor | clusters within 2 ATR | anchors with none near |
|---|---|---|---|---|
| loose | 142 | 33 | 3 | 13.7% |
| medium | 87 | 26 | 3 | 19.1% |
| strict | 20 | 9 | 0 | 58.9% |

Strict is the intended object: on most anchors there is no strict level near
price at all.

**Known non-monotonicity.** Node counts are not strictly decreasing across
tiers. A looser percentile admits longer contiguous runs, and runs wider than
1.5 ATR are dropped rather than truncated, so a loose tier can emit *fewer*
low nodes than a strict one. Total level counts are monotone; per-kind counts
are not. Recorded rather than engineered around, because truncating over-wide
runs would invent level boundaries that no detector found.

## Clustering

Complete linkage, tolerance = the **gap** between intervals, `MAX_CLUSTER_WIDTH
= 3.0 ATR`. Unchanged from Stage 4.

**Tolerance is fixed at 1.00 ATR.** Earlier stages swept three values, tripling
the cell count for an axis nobody asked about.

## Interaction

Nearest cluster above the prevailing price and nearest below. Tap = 3
consecutive one-minute bars within 0.5 ATR of the band, searched over 60 bars.

## Outcome — the race

At the moment the tap completes, take the **touch price** (that bar's close) as
the reference and place two brackets:

    favourable   `d` ATR back the way price came
    adverse      `d` ATR onward through the level

for `d` in **1, 3, 5**. Whichever is touched first wins, over at most 240
one-minute bars.

The reference is the touch price and never the band. An edge reference or a
midpoint reference both reward width — the midpoint one puts the 1 ATR
favourable bracket *behind* price on a 3 ATR band, scoring at bar zero.

Four outcomes: `FAVOURABLE`, `ADVERSE`, `AMBIGUOUS` (one bar covers both
brackets; OHLC does not order them, so neither is claimed), `CENSORED`.
Ambiguous and censored events are reported beside every rate and excluded from
it.

## ATR

5-minute Wilder, period 14, causal. Single timeframe; the 1-minute/5-minute
axis of earlier stages is gone.

## Statistic

**Nine pre-declared numbers**: for each tier × each distance, the
favourable-first share of stacked barriers (≥2 level kinds) minus that of
single-kind barriers, pooled across width strata weighted by the single-kind
arm's counts.

Everything else in the aggregator output is exploratory and labelled so. Stage 6
produced 109 cells and invited a hunt through them; nine numbers cannot be
hunted.

Guards carried over: first-touch reduction (one barrier per price region per
session per tier), width stratification, year agreement counted only over years
carrying data in both arms.

## Partitions

In-sample: 2010, 2011, 2012, 2019, 2021, 2023, 2025. Out-of-sample: 2013-2018,
2020, 2022, 2024 — run once, after in-sample is closed, with no intervening
change to this document. Holdout: 2026, opened once at project end.

## What would falsify the confluence hypothesis

All nine headline numbers within ±1pp of zero, or inconsistent in sign across
tiers with fewer than 5 of 7 years agreeing. Under that outcome, agreement
between level types carries no information about which levels hold, and the
question is closed.
