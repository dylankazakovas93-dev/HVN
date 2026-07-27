# Generation 4 Structural Pilot — 2019

Mode: **structural only**. No forward outcome was computed, loaded, written or
inspected at any point. Verdict: **NOT ACCEPTED — sample-support conditions
G4-S15 and G4-S16 fail.** The pilot is preserved and reported. The zone
definition was not adjusted, and no further detector generation was invented.

## 1. Provenance

```text
partition                 2019 (development)
archive                   nq2018.zip
member                    glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst
dataset sha256            910fcd9faf31ea1a9a485398e6771e9e44eb3314f0ebbff84ed40b6bf2545203
producing code sha        72e6777d760308a8b761fa05fa8dc2be7bb649b0
specification             research/hvn/STAGE_02_GENERATION_4_ZONE_SPEC.md
reproduction              PYTHONPATH=src python3 scripts/run_gen4_structural_pilot.py \
                            --year 2019 --data-root <data-root> --structural-only
```

Ingestion audit for the mixed-year container:

```text
parsed years                [2018, 2019]
rows admitted               430,528
rows excluded earlier year  481,125   (2018, never parsed into a Bar)
rows excluded later year     0
rows skipped non-outright    30,906   (calendar spreads)
forbidden-year rows admitted 0
```

The partition is defined by parsed timestamps, not by the archive filename. The
admitted row count matches the accepted 2019 checkpoint exactly.

## 2. Population

```text
bars admitted                    430,528
tick profiles constructed            895
tick profiles valid                  895
peak candidates                   14,780
accepted zones                       129
  accepted POC zones                 123
  accepted non-POC zones               6
POC broad distributions              762
non-POC broad distributions          198
rejected candidates               14,651
unique physical zones                129
unique physical non-POC zones          6
relationship opportunities           174
  POC opportunities                  165
  non-POC opportunities                9
volume value areas                   895
TPO value areas                      895
```

Rejections by first-failure reason:

```text
PEAK_PERCENTILE_TOO_LOW         12,427
WIDTH_EXCEEDS_MAXIMUM (POC)        762
OVERLAPS_VOLUME_POC                729
PEAK_TO_VALLEY_TOO_LOW             330
WIDTH_EXCEEDS_MAXIMUM (non-POC)    198
NO_VALID_BASIN_SEPARATION          170
BASIN_TOO_NARROW                    29
PEAK_ACTIVITY_TOO_LOW                3
ZONE_VOLUME_DENSITY_TOO_LOW          2
ZONE_ACTIVITY_DENSITY_TOO_LOW        1
```

## 3. Structural conditions

Mechanical and causal conditions G4-S01 through G4-S12 all pass.

```text
G4-S01 PASS  895 tick profiles vs 895 unique Generation 3
             (family, session_date, contract) source profiles
G4-S02 PASS  minimum accepted width 5 ticks
G4-S03 PASS  0 accepted zones below both the ATR minimum and the tick floor
G4-S04 PASS  maximum accepted non-POC width 0.7129 ATR
G4-S05 PASS  maximum accepted POC width 0.9992 ATR
G4-S06 PASS  0 overlapping accepted pairs
G4-S07 PASS  0 accepted non-POC zones failing a density, percentile or
             separation gate
G4-S08 PASS  0 profiles frozen after their interaction session
G4-S09 PASS  14,780 candidates = 129 accepted + 14,651 rejected;
             960 broad rows are a subset of the rejected ledger
G4-S10 PASS  all 17 artifacts byte-identical on an independent rerun
G4-S11 PASS  0 forbidden-year rows admitted
G4-S12 PASS  manifest forward_outcomes_computed = false
```

Sample-support conditions:

```text
G4-S13 PASS  median accepted non-POC zones per valid profile = 0
G4-S14 PASS  90th percentile accepted non-POC zones per profile = 0
G4-S15 FAIL  6 unique physical non-POC zones against a required 300
G4-S16 FAIL  non-POC opportunities R01=3 R02=3 R03=2 R04=0 R05=1
             against a required 20 each
G4-S17 PASS  median accepted zone width 0.8343 ATR
G4-S18 PASS  median accepted zone width 11 ticks
G4-S19 PASS  95th-percentile accepted non-POC width 0.7129 ATR
```

G4-S13 and G4-S14 pass only because the accepted non-POC population is
essentially empty. They are ceilings on over-detection and carry no positive
information here; they are reported as passing but should not be read as
evidence that the population is healthy.

## 4. Diagnosis: the width band collapses at this project's ATR scale

The failure is not a sample accident and not an implementation defect. It
follows from the interaction between two frozen width rules and the magnitude
of the project's frozen profile ATR.

The frozen ATR is a Wilder ATR over **one-minute** bars, so in 2019 it is small
in absolute points:

```text
frozen profile ATR   p10 0.941   median 1.924   p90 3.643   points
```

The two width rules are:

```text
minimum_zone_width_ticks = max(4, ceil(0.10 x ATR / 0.25))
maximum_zone_width_ticks = floor(0.75 x ATR / 0.25)     [clamped up to the minimum]
```

At a median ATR of 1.924 points, `0.10 ATR` is 0.77 ticks, so the **four-tick
absolute floor binds in every profile**. Four ticks is 1.00 point, which at that
ATR is a minimum width of **0.52 ATR** — against a maximum of 0.75 ATR. The
median admissible band is therefore **2 ticks wide**.

In 197 of 895 profiles the 0.75 ATR ceiling is below the four-tick floor
outright, so the clamp forces maximum equal to minimum and only exactly-four-tick
zones can exist.

The observable consequences follow directly:

- 762 of 895 POC candidates (85%) exceed their width ceiling and become
  `POC_BROAD_DISTRIBUTION`;
- 198 non-POC candidates likewise become `BROAD_ACTIVITY_DISTRIBUTION`;
- the POC zone, being wide, then vetoes 729 further non-POC candidates through
  `OVERLAPS_VOLUME_POC`;
- six non-POC zones survive in the entire year.

The specification was written for a width band expressed in ATR. It implicitly
assumes `0.10 ATR` exceeds four ticks, which requires an ATR above 10 points —
roughly a daily ATR, not the one-minute ATR this project freezes. At the actual
scale the minimum and maximum rules very nearly collide, and G4-S03 and G4-S04
are jointly satisfiable only inside a two-tick window.

## 5. Status

This is a genuine specification contradiction rather than a sample-support
shortfall alone, so the pilot is preserved and reported and the run stops here.
The definition was **not** retuned: no threshold was searched, moved or relaxed
after the counts were seen, and no Generation 5 detector was created. The
automatic outcome continuation is **not** triggered, because it is conditional
on all Generation 4 structural conditions passing.

No forward outcome exists for Generation 4. Generation 3 remains preserved and
retains its own classification.

## 6. One defect was found and corrected before this run

The POC width ceiling was initially clamped upward to the minimum zone width,
mirroring the non-POC rule. The POC rule is stated literally as
`minimum width <= POC zone width <= 1.00 ATR`, so when the four-tick floor
already exceeds 1.00 ATR the rule is unsatisfiable and the POC is a broad
distribution. The clamp admitted POC zones up to 1.80 ATR wide and failed
G4-S05. It was corrected in `72e6777` with a regression fixture, and the pilot
was rerun from scratch. That was a mechanical defect in the implementation, not
a change to any locked threshold.
