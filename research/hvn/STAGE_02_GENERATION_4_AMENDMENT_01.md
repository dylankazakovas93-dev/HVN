# Generation 4 Amendment 01 — Zone width scale

Status: **LOCKED BEFORE ANY GENERATION 4 FORWARD OUTCOME WAS INSPECTED**

Authorized by the principal after the 2019 structural pilot
(`72e6777`) failed sample-support conditions G4-S15 and G4-S16. No Generation 4
forward outcome existed when this amendment was written, and none was computed,
loaded or opened. The amendment is therefore made blind to outcomes.

## 1. The defect being corrected

The original width rules were expressed in ATR but carried a four-tick absolute
floor:

```text
minimum_zone_width_ticks = max(4, ceil(0.10 x ATR / 0.25))
maximum_zone_width_ticks = floor(0.75 x ATR / 0.25)   [clamped up to the minimum]
```

The project's frozen profile ATR is a Wilder ATR over **one-minute** bars. Its
2019 distribution is p10 0.941, median 1.924, p90 3.643 points. At that scale
`0.10 ATR` is 0.77 ticks, so the four-tick floor binds in every profile and is
itself a median **0.52 ATR** minimum width, against a **0.75 ATR** maximum. The
median admissible band was two ticks, and in 197 of 895 profiles the ceiling
fell below the floor entirely.

The rules implicitly assumed `0.10 ATR > 4 ticks`, which requires an ATR above
10 points — a daily ATR, not the one-minute ATR this project freezes. This is a
scale contradiction in the specification, not an implementation defect.

## 2. The substantive argument

The volume proxy allocates each bar's volume **uniformly** across every tick the
bar occupied. Intra-bar location is not observed; it is assumed. The honest
resolution of the dataset is therefore of the order of one bar's range, which is
approximately one ATR.

A zone materially narrower than a bar's typical range asserts a precision the
data cannot support. That is the same error that made Generation 3's one-tick
nodes untestable. Widening the zone scale is a correction toward the data's real
resolution, not a relaxation to obtain a larger sample.

## 3. Amended constants

```text
minimum_zone_width_ticks       = max(3, ceil(0.40 x ATR / 0.25))
maximum_zone_width_ticks       = floor(1.50 x ATR / 0.25)   [clamped up to the minimum]
maximum_poc_zone_width_ticks   = floor(2.50 x ATR / 0.25)   [never clamped]
minimum_peak_activity_percentile = 90.0
```

Unchanged: the triangular smoothing kernel and its `0.05 ATR` half-width with a
two-tick floor; `peak_smoothed_activity_density >= 1.50`; the local basin rules;
the 70%-of-peak core expansion; `zone_volume_density >= 1.25`;
`zone_tpo_density >= 1.00`; `zone_activity_density >= 1.35`;
`peak_to_valley_ratio >= 1.10`; adjacent-peak resolution; the POC rules; both
value areas; physical-zone deduplication; and the rejection ordering.

At the 2019 median ATR of 1.924 points this gives a band of roughly 3 to 12
ticks, against the previous 4 to 5. A 12-tick zone is about 5% of a typical RTH
profile range, so a zone remains a localized region and does not approximate the
value area.

## 4. Why the percentile gate also moves

12,427 of 14,780 candidates in the pilot were rejected by
`PEAK_PERCENTILE_TOO_LOW` — a peak had to sit in the top 5% of all active ticks
in its own profile. On a median 222-tick profile that is the top eleven ticks,
which mechanically admits at most one or two non-POC zones per profile
regardless of any width rule. The percentile gate, not the width band, was the
binding constraint on population size.

Moving it to the 90th percentile keeps it selective while removing it as the
sole determinant of the population. `peak_smoothed_activity_density >= 1.50` and
the zone density floors are retained unchanged and continue to carry the
significance requirement.

## 5. Amended structural conditions

```text
G4-S02 no accepted zone is narrower than three ticks
G4-S03 no accepted zone is narrower than 0.40 ATR, subject to the
       three-tick absolute floor
G4-S04 no accepted non-POC zone exceeds 1.50 ATR
G4-S05 no accepted POC zone exceeds 2.50 ATR
G4-S17 median accepted zone width >= 0.40 ATR
G4-S18 median accepted zone width >= 3 ticks
G4-S19 95th-percentile accepted non-POC width <= 1.50 ATR
```

G4-S01, G4-S06 through G4-S16 are unchanged.

## 6. Discipline

These values were derived from the resolution of the data and from the
diagnosed scale contradiction. **No value was searched.** The amended definition
is run against 2019 **once**. If it fails a sample-support condition again, the
failure is reported; the constants are not swept until a gate passes.

This amendment supersedes the width and percentile constants in
`STAGE_02_GENERATION_4_ZONE_SPEC.md`. Everything else in that specification
stands. The preceding pilot at `72e6777` is preserved unchanged as the record of
the original definition.
