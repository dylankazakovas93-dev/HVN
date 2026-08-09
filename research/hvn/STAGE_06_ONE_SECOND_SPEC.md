# Stage 6 — One-second data: split, architecture, and the frozen reversal test

Frozen before the 1-second dataset arrives. The reversal test below is written
now, in full, precisely so it cannot be adjusted after the new numbers are seen.

## Why this stage exists

Every volume figure produced so far is an estimate. A 1-minute bar spanning
twenty ticks has its volume spread **uniformly** across all twenty, because
OHLCV cannot say where inside the bar it traded. Nodes, POC, value edges and TPO
counts all inherit that smearing.

One-second bars mostly touch one to three ticks, so the allocation error nearly
vanishes and the profile becomes close to a measurement rather than a guess.
TPO improves in the same move: bar-visits per tick become near-literal
seconds-at-price.

What does **not** change: the data is still OHLCV, so there is still no
aggressor side. The displacement proxy stays exactly as it is. Gamma exposure
remains out of scope.

## Partition assignment

Sixteen years make a real out-of-sample test possible for the first time. The
constraint is that **2019, 2021, 2023 and 2025 are burned**: they have been
examined repeatedly across Stages 2–5 and can never serve as out-of-sample
again. They are quarantined into the development set by force, and the set is
topped up from the early end.

| set | years | approx share |
|-----|-------|--------------|
| **IS** — development | 2010, 2011, 2012, 2019, 2021, 2023, 2025 | ~41% |
| **OOS** — tested once per frozen spec | 2013, 2014, 2015, 2016, 2017, 2018, 2020, 2022, 2024 | ~53% |
| **SEALED** — opened once, at the end of the project | 2026 | ~6% |

The forbidden-year rule from Stages 2–5 (2018, 2020, 2022, 2024 never opened) is
**lifted for this stage by explicit decision**, and those years are assigned to
OOS. That is the best available use for them: they are the only large blocks of
data this project has never looked at.

## Boundary buffer, not a percentage embargo

The longest outcome window in this project is **120 minutes**. Leakage across a
split boundary is therefore bounded by two hours. A **one trading day** buffer
either side of every boundary is already an order of magnitude more separation
than the label horizon needs.

A percentage-of-dataset embargo — the 10% convention — is imported from work
where labels span weeks or months. Applying it here would discard well over a
year of data to guard against a two-hour overlap. It is not used.

The sealed holdout is a separate device and serves a different purpose: it
guards against the analyst, not against leakage. It is opened once, ever.

## Architecture: session histograms

Sixteen years of 1-second bars is roughly **25M rows per year, ~400M total**.
The Stage 3–5 engine loads a year of bars into memory as `Bar` objects and walks
~8,000 of them per anchor. At 1-second resolution that becomes ~1.6M bars per
anchor and does not fit in memory or in any acceptable runtime.

A volume profile is **additive over sessions**, and that is the whole solution:

1. Stream each session's 1-second bars **once**. Collapse to a compact
   `tick -> (volume, seconds)` histogram — a few thousand entries, not millions
   of rows. Persist one file per session per contract.
2. Every profile downstream is a **sum of histograms**, never a walk over bars.
   The cost of building a 20-session composite becomes independent of bar count,
   which makes 1-second data cheaper to profile than the 1-minute data is today.
3. Outcome measurement still walks bars, but only the forward window of a tapped
   event.

## Rebuild cadence

| object | cadence | reason |
|--------|---------|--------|
| composite (rolling 20 sessions) | **daily** | it only changes when a session closes; rebuilding hourly recomputed the same profile 23 extra times a day |
| hourly VP | hourly | it is a new profile every hour by definition |
| Globex developing, cash developing | hourly | genuinely developing intraday |
| prior RTH | daily | fixed once the session ends |

Rebuilding the composite daily excludes the developing session from it. That is
a deliberate change and arguably the more honest object: composite levels are
then fixed for the day, which is how a chart reader would use them.

## Levels

Recomputed at true tick resolution from the histograms: high nodes, low nodes,
POC, value area (70% of volume, the standard definition), TPO extremes at the
three predeclared thresholds, and anchored VWAP with both sigma and percentage
bands. Definitions are carried over unchanged from Stage 4 so the results remain
comparable.

## The frozen reversal test

Carried over from Stage 5 **without modification**. Written here in full so that
no part of it can be re-tuned once the new data is in hand.

**Interaction.** A tap is 3 consecutive bars with price within 0.5 ATR of the
band, beginning within 60 minutes of the anchor. One barrier per price region
per session — first touch only, region retired for the remainder of that
session, live again the next.

**Selection.** At each anchor, the nearest cluster above the prevailing price
and the nearest below it. Clusters are complete-linkage; tolerance is the
maximum edge-to-edge gap; cluster width is capped at 3 ATR.

**Outcome, at 10, 30 and 120 minutes.**

- `state` — where the close sits at that horizon: reversed, broke through, or
  still inside the band.
- `favourable` / `adverse` — furthest the move got back the way price came, and
  furthest onward through the level, at any point up to that horizon, measured
  from the band **midpoint** and divided by ATR.

Midpoint, not edges: measuring from edges makes a wide band look reversal-prone
for a purely geometric reason, because arriving from below leaves a short trip
down and a full-width trip up.

**Statistic.** Reversal share among *resolved* outcomes. Events still inside the
band at the horizon are excluded rather than assigned to either side.

**Comparison.** Reversal share by number of distinct level kinds in the cluster
(1, 2, 3, 4+), **within width strata**, never pooled across them.

**Requirements, binding.**

1. Every cell written, including null and negative.
2. Year agreement counted **only over years carrying data in both arms**. A year
   with an empty cell did not disagree. Conflating the two once made a two-year
   result read as "2 of 4" and caused a real effect to be dismissed.
3. Session-clustered bootstrap and a session-level permutation test for any
   headline claim.
4. Cell count and chance rate reported together, every time.

## What the test decides

Stage 5 found stacked levels reverse more: 30 of 30 cells positive, adverse
excursion about 25% lower at 4+ kinds than at 1, holding across four years.

That was built on smeared volume. If it survives accurate profiles it is real.
If it evaporates, it was an artifact of the allocation guess. Both outcomes are
informative and both will be reported.

The IS run happens first. The OOS run happens **once**, against this document,
with no intervening changes. The sealed year is not opened.


---

# Amendment 01 — early years are too sparse to use

Recorded after measuring the dataset, before any Stage 6 outcome was seen.

The partition above assumed 2010-2012 could top the development set up to ~40%.
They cannot. Median traded seconds per session, measured across all 286 row
groups:

| years | median 1s rows/session |
|---|---|
| 2010-2012 | 332 - 473 |
| 2013-2014 | 15,877 - 17,610 |
| 2015-2026 | 20,294 - 52,755 |

A session with a few hundred traded seconds cannot supply the 183 minutes of
forward bars every outcome needs, so those sessions yield nothing at all. This
is a property of the source, not of the front-month filter: the filter retains
99% of rows in the affected row groups (6,175 of 6,178 in a 2010 sample).

## Revised partitions

| set | years | approx share |
|-----|-------|--------------|
| IS | 2019, 2021, 2023, 2025 | ~33% |
| OOS | 2015, 2016, 2017, 2018, 2020, 2022, 2024 | ~58% |
| SEALED | 2026 | ~8% |

2013 and 2014 are excluded as marginal.

The development set is now entirely burned years. That is acceptable here and
arguably preferable: Stage 6 asks whether the Stage 5 result survives accurate
volume, and the sharpest form of that question is the **same years with better
data** — same events, same regimes, only the volume precision differs. Adding
fresh years would confound "the data got finer" with "the market was different".

The out-of-sample set is untouched and remains pristine. The frozen reversal
test is unchanged.
