# Stage 2 Generation 4 — HVN Zones: Charter

Status: **LOCKED BEFORE ANY GENERATION 4 OUTCOME WAS OBSERVED**

Authorized: 2026-07-27 by Dylan
Generation: `STAGE_02_GENERATION_4_HVN_ZONES`
Branch: `stage-02-atomic-hvn`, from `5e9c963`

## 1. Why Generation 3 does not test the intended object

```text
GENERATION_3_2019_ATOMIC_POINT_RESULT =
COMPUTATIONALLY_VALID_BUT_NOT_A_VALID_TEST_OF_THE_INTENDED_HVN_ZONE_HYPOTHESIS
```

The Generation 3 detector, through Amendment 03, produced genuinely atomic
objects. Measured on the accepted 2019 checkpoint:

- median accepted node width **0.25 points**;
- the overwhelming majority of accepted nodes were **one NQ tick** wide;
- p90 width 0.5 points, maximum 2.25 points.

`inside_close_share` therefore asked how often a future one-minute close landed
on **essentially one exact tick**. Mean inside-close share was 0.016 with a
median of exactly zero, for treated and control alike. That is a near-degenerate
instrument, and a one-tick price point is not the economically meaningful
volume-node region this project set out to test.

## 2. What Generation 3 remains

Generation 3 is **computationally valid for the object it defined**. Its 2019
checkpoint reconciles exactly, sixty events were independently recomputed from
raw one-minute bars with zero mismatches, and all eight ledgers are
byte-identical on rerun. It is preserved unchanged in
`outputs/stage_02_generation_3_final/` alongside Pilots V1-V4.

Its result must **not** be read as evidence that meaningful HVN zones fail. It
is evidence about one-tick price points, which is a different claim.

## 3. What changes and when

Generation 4 replaces atomic price points with causally frozen, **smoothed,
multi-bin** high-volume / high-occupancy zones. The research object changes;
the research questions, horizons, controls, matching, episode clustering,
statistics and reporting requirements are carried over unchanged.

**This structural reset is justified by the geometry of the tested objects, not
by whether the 2019 outcome was favourable or unfavourable.** The 2019 outcome
was in fact unfavourable — H1 ratios of 0.909 and 0.934 against C02, H2 within
1% of parity — and that result is preserved rather than discarded. No
Generation 3 outcome may be used to tune any Generation 4 threshold.

The Generation 4 definition is frozen **before** any Generation 4 outcome is
computed. No threshold may be revised after its forward outcomes are opened.

## 4. The intended research object

```text
An HVN zone is a contiguous multi-price region inside a completed source
profile where both allocated volume and time-at-price are concentrated,
centred on a meaningful local peak and separated from surrounding profile
structure by a detectable shoulder or valley.
```

The model remains a one-minute OHLCV proxy: bar volume allocated uniformly
across occupied ticks, and TPO occupancy counted per occupied tick. This is
**not** transaction-level volume at price and is never described as such.

## 5. Finality

Generation 4 is the **final authorized structural definition** for this
development study. If a structural sample-support condition fails, the
authorized response is to preserve the pilot and report it — not to invent
another detector generation.
