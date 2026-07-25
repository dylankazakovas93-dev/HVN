# Stage 2 Generation 3 — Evidence Classification

Status: **LOCKED BEFORE EMPIRICAL ACCESS**

Each relationship and each main mechanism receives one classification. Negative
findings are valid results. No classification may suppress the descriptive
all-event tables, which stand on their own.

Mechanisms classified separately:

```text
M1 PROXIMITY   price remains unusually close to an atomic HVN after touching it
M2 ROTATION    price rotates around the atomic peak more than around ordinary bins
M3 RESIDENCE   how long price remains near the atomic peak
M4 DEPARTURE   how quickly and how far price moves after confirmed departure
M5 RESIDENCE_DEPARTURE_LINK  whether departure behaviour varies with prior residence
```

## SUPPORTED

All of:

- at least 50 unique economic episodes pooled;
- at least 10 unique episodes in at least three **complete** development years
  (2019, 2021, 2023, 2025; partial 2026 never counts toward this);
- the expected direction in at least three complete years;
- broadly similar results across nearby bin ratios and prominence thresholds;
- no material implementation or control-balance defect;
- the effect survives removal of the largest 1% and of the five largest
  episodes per year.

## SUGGESTIVE

An economically coherent pattern that lacks the independent episodes or the
year consistency required for `SUPPORTED`, where nearby settings do not
strongly contradict it.

## NOT_SUPPORTED

An adequate independent sample, with the effect near zero or contrary across
most years and settings.

## UNSTABLE

Sign or magnitude changes repeatedly across years or nearby definitions.

## UNDERPOWERED

Too few unique episodes to judge.

## INVALID

An implementation, causality, data or control defect prevents interpretation.

## Reporting rules

Expected directions are declared before results are viewed:

- M1: closes within +/- 0.25 ATR are a **higher** share around atomic peaks
  than around matched ordinary bins;
- M2: peak-centre crossings and side changes are **higher** around atomic peaks;
- M3: residence in the +/- 0.25 ATR band is **longer** around atomic peaks;
- M4: no direction is declared; departure speed and extent are descriptive;
- M5: no direction is declared; the residence/departure relationship is the
  open question.

Comparisons are reported with and without matching. Where the two disagree,
both are shown and the disagreement is stated rather than resolved by
preferring the friendlier one.
