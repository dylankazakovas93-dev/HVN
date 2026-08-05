# Stage 4 — Confluence of thin levels across profile sources

Frozen before any empirical execution. Every threshold below is predeclared. No
threshold is added, removed or moved after outcomes are seen.

## Motivation

Stage 3 found one weak positive: low-volume nodes on a rolling 20-session
profile show a modest excess in forward excursion, concentrated between 6.5 and
9.0 ATR, at p = 0.007 to 0.044 after session-clustered resampling. That is a
single profile's view of "thin".

The claim tested here is that thinness seen by **several independent profile
constructions at the same price** is a stronger condition than thinness seen by
one. The test is **monotonicity in confluence degree**, not the significance of
any individual cell. A confound would have to strengthen as more unrelated
profiles agree, which is a much harder thing for a confound to do.

## Out of scope, and why

- **Gamma exposure (GEX).** Requires options open interest and dealer
  positioning. No options data exists in this project.
- **VXN-derived levels.** Requires a VXN series. If a dated level list is
  supplied it can be tested as a sixth source; it cannot be derived here.
- **Options flow.** No such data.

Nothing in this document infers any of the above from price and volume.

## Profile sources

Five, each anchored differently so they do not see the same thing.

| id | source | window |
|----|--------|--------|
| P1 | rolling composite | trailing 20 sessions, re-anchored hourly (Stage 3, unchanged) |
| P2 | single hour | one completed hour, standalone |
| P3 | Globex developing | 18:00 ET session open to the current hourly close |
| P4 | cash developing | 09:30 ET to the current hourly close |
| P5 | prior RTH | the previous session's full 09:30–16:00 |
| P6 | anchored VWAP, Globex | volume-weighted average price from 18:00 ET to the current hourly close |
| P7 | anchored VWAP, cash | volume-weighted average price from 09:30 ET to the current hourly close |
| P8 | anchored VWAP, prior RTH | the previous session's full-session VWAP, carried forward as a fixed level |
| P9 | anchored VWAP, rolling | volume-weighted average price over the trailing 20 sessions |

P1 is carried over as built. Stage 1 profile construction is not altered.

VWAP is a separate source class from the profiles: a profile answers "where did
volume sit", a VWAP band answers "how far is price from where volume sat, in
units of its own dispersion". They disagree often enough to be worth counting as
independent votes, which is the whole point of a confluence test.

## Level types

Within each source, at each hourly evaluation:

| id | level | definition |
|----|-------|------------|
| L1 | low node, outside value | bottom decile of smoothed activity over traded ticks, outside the value area |
| L2 | low node, inside value | same, but inside the value area — the case Stage 3 could not isolate |
| L3 | value edge | VAH and VAL |
| L4 | POC | highest smoothed activity tick |
| L5 | TPO extreme | thin by time rather than volume, see below |
| L6 | VWAP band | a band edge on sources P6–P9, both band definitions below |

L1–L5 apply to profile sources P1–P5. L6 applies to VWAP sources P6–P9.

## Value area, both definitions

Computed both ways and tested separately. Neither is selected on result.

- **VA-PCT** — the 70% of volume nearest the POC, expanded tick-pair by
  tick-pair from the POC in the conventional way.
- **VA-SIGMA** — bands at 1, 2, 3 and 4 standard deviations of the
  volume-weighted price distribution about its volume-weighted mean.

## VWAP bands, both definitions

Computed both ways on every VWAP source and tested separately. Neither is
selected on result. Both are causal — the dispersion at an hourly close uses
only bars up to that close.

- **VWAP-SIGMA** — bands at 1, 2, 3 and 4 volume-weighted standard deviations of
  price about the anchored VWAP.
- **VWAP-PCT** — bands at fixed percentage offsets from the anchored VWAP:
  0.25%, 0.50%, 1.00% and 1.50%. Predeclared, chosen to span roughly the same
  ground as the sigma bands on a typical session without being fitted to any.

The two are not redundant. A sigma band widens when the session is volatile; a
percentage band does not. Which of them lines up better with the profile levels
is itself a result worth having, so both are reported side by side and the
comparison is stated before either is compared against the control.

A VWAP band level is the band edge, given a width of ±0.25 ATR so it can join
the confluence test on the same footing as a node interval.

## TPO extreme thresholds

Three, predeclared:

- **T1** single print: TPO count == 1
- **T2** TPO count <= 2
- **T3** bottom 10% of TPO count among traded ticks in the source

## Confluence

Two levels from **different sources** are confluent when their price intervals
overlap after each is widened by a tolerance. Confluence degree `k` is the number
of **distinct sources** contributing, never the number of levels — two levels
from the same source are one vote.

**Tolerance is a tested axis, not a constant.** Levels drawn by different
constructions have no reason to agree to the tick, and a tolerance too tight
would report "no confluence exists" when the real finding is that the levels
cluster loosely. Three values, all predeclared and all reported:

    0.25 ATR    tight
    1.00 ATR    moderate
    2.00 ATR    loose

Wider tolerance mechanically raises k, so confluence degree is only ever
compared **within** a tolerance, never across. A k=3 at 2.00 ATR is not the same
object as a k=3 at 0.25 ATR and the tables never pool them.

## ATR timeframe

ATR is computed on both a 1-minute and a 5-minute bar series, causally in both
cases, and every tolerance and outcome is expressed in each. The 1-minute ATR is
what Stage 3 used; the 5-minute is closer to the scale a level is drawn at. Both
are reported; neither is selected on result.

Reported for k = 1, 2, 3, and >= 4. A cell with fewer than 30 first-touch events
in either arm is written but marked unsupported.

## Interaction and outcome

**Nearest barrier, not every level.** Stage 3 tested every node it found. That
is not how a level is used and it inflates the population with levels price was
never near. Here, at each hourly anchor, only the nearest confluent level
**above** the prevailing price and the nearest **below** it are carried forward.
Two barriers per anchor per configuration, whatever k they happen to carry.

This is deliberately crude, and crude is the point: it needs no threshold, it
cannot be tuned, and it is the same object a chart reader would look at.

Otherwise unchanged from Stage 3 so the results stay comparable:

- tap validity: within 0.5 ATR for 3 consecutive bars, beginning within 60 bars
  of the anchor
- **first-touch reduction**: one barrier per session; overlapping price regions
  in the same session are one observation
- excursion recorded continuously over 60 bars, threshold-free
- rotation at 3 ATR within 5, 20 and 60 minutes

Added: **rotation at three timescales**, 3 ATR reached within 5, 20 and 60
minutes. This separates a fast rotation from a slow drift covering the same
ground, at the horizons named in the request.

## Control

Width-matched neutral bands, as in Stage 3. Confluence degree cannot be matched
in the control by construction, so **no single k cell is a finding on its own**.
The reported test is whether the treated-minus-control difference rises with k.

## Statistical requirements

Binding, not advisory:

1. Every cell is written, including null and negative ones.
2. Four-year sign agreement is reported per cell, with the chance rate
   (5/16 per cell) beside the pass count.
3. Any headline claim requires session-clustered bootstrap and a session-level
   permutation test, as in `scripts/bootstrap_lvn_excursion.py`.
4. The number of cells tested is reported, so the multiple-comparison cost is
   visible rather than implied. With nine sources, six level types, two value
   area definitions, two band definitions and four confluence degrees, this
   stage tests far more cells than any previous one. The chance rate is stated
   in the same table as the pass count, every time, without exception.
5. Monotonicity in k is stated as pass or fail before any individual cell is
   discussed.

## Partitions

2019, 2021, 2023, 2025. Unchanged.
