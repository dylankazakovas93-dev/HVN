# Generation 3 — 2019 Pilot Finding

Status: **PILOT FAILS ACCEPTANCE — DEFINITION DECISION REQUIRED**

Detected: 2026-07-25, on the 2019 pilot audit, at `8aa2b50`.
No outcome metric was inspected before this finding was raised.

## F-08 — The locked prominence rule selects sparse tails and rejects dense peaks

The 2019 pilot ran clean: 430,528 bars, **6,852 profiles** — exactly the
Generation 1 2019 profile count, confirming `construct_profile()` is unchanged
— 6,019 atomic opportunities and 2,730 atomic events. Only 2019 rows were
parsed. But the atomic population it produced is not the object the generation
set out to study.

### Symptom 1 — "atomic" zones are frequently wide

| width | count | share |
|---|---|---|
| 1 bin | 1,938 | 32% |
| 2-3 bins | 1,194 | 20% |
| >= 10 bins | 923 | 15% |

The widest is **51 bins**, and the widest zone spans **6.10 ATR**. A 51-bin
plateau is the opposite of "an abnormally concentrated local profile peak".

### Symptom 2 — the POC is almost never inside a qualifying atomic peak

Only **25 of 6,019** qualifying peaks (0.4%) contain the profile POC. The POC
is the global maximum-weight bin; if concentrated peaks were being selected, it
would be among them far more often.

### Mechanism

Both symptoms have one cause. Prominence is purely **relative** to a local
baseline, with no absolute mass floor.

Wide plateaus are not zero-baseline artifacts — none has infinite prominence.
They are sparse-tail structure:

| class | count | median prominence | median peak weight |
|---|---|---|---|
| 1 bin | 1,938 | 1.60 | **78.9** |
| >= 10 bins | 923 | 2.00 | **3.0** |

A ten-bin run each holding weight 3, bounded by bins of weight 2, has
prominence 2.0 and qualifies. It carries negligible activity.

Meanwhile, genuine dense peaks fail. Reconciling a real rebuilt profile
(`39f78407347ad3f7c87c`, TPO, ratio 0.05, ATR 1.503, bin size 0.25, 259 bins):

```text
POC bin 25702, weight 67, local baseline 62, prominence 1.081 -> REJECTED
48 peak candidates, 0 qualifying at threshold 1.5
```

In a dense region the +/- 0.50 ATR baseline is drawn from bins nearly as heavy
as the peak, so the ratio approaches 1. In an empty region the baseline is
near zero, so a trivial bump clears any threshold.

The selection is therefore **inverted**: it favours low-activity tail structure
and discards the high-activity structure the hypothesis is about.

### Why this appears now and not in Generations 1 and 2

`peak_candidates()` is unchanged locked Stage 1 code that passed the Stage 1B
audit, and Generations 1 and 2 used the same rule. There, every qualifying peak
was then expanded through all contiguous bins holding at least 50% of peak
weight and merged with touching zones, which reshaped the zones and masked the
selection problem. Generation 3 deliberately removes that expansion, so the raw
selection is visible for the first time.

This is a property of the locked rule interacting with the atomic definition,
not a defect introduced by Generation 3 code.

## Why this is not being fixed unilaterally

Every available remedy redefines what an atomic HVN *is*:

1. an absolute mass floor, for example requiring the peak to sit above a
   percentile of the profile's own bin-weight distribution;
2. a plateau width cap in bins or in ATR;
3. a different local-baseline radius, so dense regions are compared against a
   wider neighbourhood;
4. accepting the population as-is and reporting one-bin peaks separately from
   plateaus, changing nothing.

Each is an irreversible research-design choice and belongs to Dylan, not to the
implementation agent.

**No outcome metric — proximity, residence, departure or excursion — has been
inspected.** The pilot's outcome ledgers were written but deliberately not
opened, so whichever definition is chosen is still uncontaminated by results.
That property is lost the moment those tables are read, so the decision should
be made before any further analysis.

## Pilot disposition

The 2019 pilot is **not accepted**. Its ledgers are retained as the record of
what the locked definition produces, and its registry row records the stop. The
remaining four development partitions are **not** authorized to run: repeating
a definition known to select the wrong objects would waste the compute and
produce evidence nobody should use.

Confirmed clean during the pilot, and unaffected by this finding:

- only 2019 rows parsed; event ledgers contain the single year value `2019`;
  no 2018, 2020, 2022 or 2024 row reached the parser;
- dataset sha256 `910fcd9faf31ea1a...` computed from the ingested bytes;
- profile construction reproduces the Generation 1 count exactly (6,852);
- Generation 1 and Generation 2 outputs byte-unchanged;
- 180 tests pass;
- row counts reconcile: 7,902 events x 5 horizons = 39,510 proximity rows;
  x 4 bands = 31,608 residence rows; x 4 departure definitions = 31,608.
