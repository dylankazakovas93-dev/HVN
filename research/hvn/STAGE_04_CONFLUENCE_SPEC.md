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

P1 is carried over as built. Stage 1 profile construction is not altered.

## Level types

Within each source, at each hourly evaluation:

| id | level | definition |
|----|-------|------------|
| L1 | low node, outside value | bottom decile of smoothed activity over traded ticks, outside the value area |
| L2 | low node, inside value | same, but inside the value area — the case Stage 3 could not isolate |
| L3 | value edge | VAH and VAL |
| L4 | POC | highest smoothed activity tick |
| L5 | TPO extreme | thin by time rather than volume, see below |

## Value area, both definitions

Computed both ways and tested separately. Neither is selected on result.

- **VA-PCT** — the 70% of volume nearest the POC, expanded tick-pair by
  tick-pair from the POC in the conventional way.
- **VA-SIGMA** — bands at 1, 2, 3 and 4 standard deviations of the
  volume-weighted price distribution about its volume-weighted mean.

## TPO extreme thresholds

Three, predeclared:

- **T1** single print: TPO count == 1
- **T2** TPO count <= 2
- **T3** bottom 10% of TPO count among traded ticks in the source

## Confluence

Two levels from **different sources** are confluent when their price intervals
overlap after each is widened by ±0.25 ATR. Confluence degree `k` is the number
of **distinct sources** contributing, never the number of levels — two levels
from the same source are one vote.

Reported for k = 1, 2, 3, and >= 4. A cell with fewer than 30 first-touch events
in either arm is written but marked unsupported.

## Interaction and outcome

Unchanged from Stage 3 so the results are comparable:

- tap validity: within 0.5 ATR for 3 consecutive bars, beginning within 60 bars
  of the anchor
- **first-touch reduction**: one shelf per session; overlapping price regions
  in the same session are one observation
- excursion recorded continuously over 60 bars, threshold-free

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
   visible rather than implied.
5. Monotonicity in k is stated as pass or fail before any individual cell is
   discussed.

## Partitions

2019, 2021, 2023, 2025. Unchanged.
