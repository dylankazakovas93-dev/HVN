# Stage 2 Generation 3 — Atomic HVN Specification

Status: **LOCKED BEFORE EMPIRICAL ACCESS**

Authorized: 2026-07-25 by Dylan
Generation: `STAGE_02_GENERATION_3_ATOMIC_HVN`
Branch: `stage-02-atomic-hvn`, from `6bb9f18`

```text
BROAD_MULTI_BIN_HVN_STUDY = INCONCLUSIVE / UNDERPOWERED
```

Generations 1 and 2 are preserved unchanged in `outputs/stage_02/` and
`outputs/stage_02_generation_2/`. This is a new hypothesis generation, not a
bug fix and not a reinterpretation of those results.

## 1. Why a new generation

The Generation 1/2 HVN definition expanded a qualifying peak through every
contiguous bin holding at least 50% of peak weight, then merged touching
zones. The resulting acceptance areas were sometimes several ATR wide, so
"price stayed inside the HVN" could be satisfied by a broad region rather than
by a concentrated peak.

Generation 3 tests a narrower object: an **atomic HVN** is one locally
prominent peak bin, or one contiguous plateau of exactly equal-weight adjacent
peak bins.

## 2. Atomic HVN definition

The locked Stage 1 local-peak rules are reused unchanged, via
`hvn.peak_candidates()`:

- adjacent bins outside the peak or plateau must have lower weight;
- the local baseline is the median of non-plateau bins within +/- 0.50 frozen ATR;
- at least two baseline bins are required;
- prominence thresholds are 1.5, 2.0 and 2.5, and equality qualifies;
- deterministic plateau representative selection is unchanged.

A qualifying atomic HVN is a `PeakCandidate` with `qualifies = True`. Its zone
is exactly the bin span `[start_bin_index, end_bin_index]`:

```text
atomic_low  = bins[start_bin_index].bin_low
atomic_high = bins[end_bin_index].bin_high
```

For Generation 3:

- no expansion through neighbouring bins at 50% of peak weight;
- no merging of nearby or touching atomic peaks;
- every qualifying local peak is preserved as a separate atomic feature;
- the representative peak price is retained;
- `is_poc` records whether the atomic peak contains the global profile POC;
- `broad_node_id` retains the mapping to the Generation 1/2 broad node, for
  historical comparison only, never as an input to any Generation 3 metric.

Profile bin construction is unchanged. Bin ratios remain 0.05, 0.10 and 0.20
ATR; no 0.30 or 0.50 ATR bins are added in this generation. Proxies remain
`UNIFORM_BAR_VOLUME` and `TPO_RANGE_OCCUPANCY`.

## 3. Relationships

R01 prior RTH to following ETH; R02 prior RTH to following RTH; R03 full
overnight to current RTH; R04 midnight-to-open to current RTH; R05
opening-hour to later RTH. All five stay separate. R02 continues to separate
`RTH_FIRST_OVERALL` from `RTH_AFTER_ETH_TOUCH`. Incompatible relationships are
never pooled into one headline result.

## 4. Partitions

Authorized development years: 2019, 2021, 2023, 2025, partial 2026.
Forbidden partitions: 2020, 2022, 2024, and 2018 rows.

Partial 2026 is roughly half a year and is reported separately in every
year-stability summary. It never counts as a complete development year.

### 4.1 Archive naming, and the 2018 constraint

2019 market rows are supplied inside `nq2018.zip`, whose member spans
2018-01-01 to 2019-12-30. The authorization lists 2019 as an authorized
development year and 2018 as forbidden. These are reconciled the same way
D-014 already reconciles them: **archive filenames do not partition data**.

`nq2021.zip` likewise contains forbidden 2022 rows and is legitimately read for
2021. The guard that matters is the year-prefix check in `hvn.io`, which stops
before any row outside the requested year is parsed. Generation 3 therefore
reads 2019 rows from `nq2018.zip` and parses **no 2018 row**. Every access is
recorded in `PARTITION_ACCESS_LOG.csv` with the parsed year.

## 5. Why Stage 1 profiles must be rebuilt

The saved Generation 1/2 ledgers cannot supply atomic peaks:

- `profiles_<year>.csv.gz` holds profile metadata only, with no bin weights;
- `opportunities_<year>.csv.gz` holds the **broad** node geometry
  (`hvn_low`, `hvn_high`, `peak_weight`, `local_baseline`, `prominence_ratio`),
  which is the post-expansion, post-merge object this generation must not use.

Neither preserves per-bin weight, so the peak bin and its equal-weight plateau
cannot be recovered. Stage 1 profile construction is therefore rerun from the
authorized development archives, using `engine.construct_profile()` unchanged.
No Stage 1 calculation is altered. Nothing in Generation 1 or Generation 2 is
overwritten.

## 6. First touch

Atomic zones use half-open price boundaries `[atomic_low, atomic_high)`. A bar
touches the zone when at least one valid NQ price tick in its inclusive
high-low range lies inside the zone. The first eligible interaction with each
frozen atomic HVN is the event.

Approach classification: `START_INSIDE`, `APPROACH_FROM_BELOW`,
`APPROACH_FROM_ABOVE`. Touch classification: `WICK_ONLY_SAME_SIDE`,
`CLOSE_INSIDE`, `CROSS_THROUGH`.

The event becomes available only at the touch bar close. All forward
measurement starts with the next completed one-minute bar.

## 7. Proximity

ATR is frozen at first touch for all proximity and departure normalization.

For every forward completed close:

```text
distance_to_atomic_zone_atr =
    0                                             if the close is inside the zone
    gap to the nearest zone boundary / frozen ATR  otherwise

distance_to_peak_center_atr = |close - representative peak price| / frozen ATR
```

Primary proximity band: the atomic zone expanded by 0.25 ATR on each side.
Sensitivity bands: the exact zone, +/- 0.10 ATR, and +/- 0.50 ATR.

Price is not required to close inside the exact atomic bin to count as
remaining near the HVN.

## 8. Horizons

5, 15, 30, 60 and 120 minutes. Horizons must be complete; censoring is
recorded rather than turned into a partial label. Every horizon is reported;
30 minutes is not the sole headline.

## 9. Proximity and rotation metrics

Per event and horizon: mean, median, 75th and 90th percentile close distance
from the atomic zone in ATR; mean distance from the representative peak centre;
share of closes inside the exact zone and within +/- 0.10, 0.25 and 0.50 ATR;
share of candle ranges overlapping each of those four bands; completed-close
crossings of the peak centre; side changes across the peak; close-path
efficiency; and the probability of revisiting each band after leaving it.

**Principal proximity outcome:** share of closes within the +/- 0.25 ATR band.
**Supporting principal outcome:** median close distance from the atomic zone in
ATR. Exact atomic-bin closes are secondary only.

## 10. Residence

Per band: total minutes in band; longest consecutive run; time from first touch
to first exit; re-entry count; time from first exit to first re-entry; share
never entering by close; share never leaving; right-censoring rate.

Primary residence band: atomic zone +/- 0.25 ATR. Raw buckets: B0 0-2, B1 3-5,
B2 6-10, B3 11-20, B4 more than 20 minutes.

The historical normalized statistic is preserved and reported:

```text
R_T = continuous residence minutes * ATR at touch / atomic-zone width
```

It is not used as the sole residence classification, because atomic zones are
deliberately narrow and the ratio can become mechanically large.

## 11. Confirmed departure

Primary: two consecutive completed one-minute closes outside the **same side**
of the +/- 0.25 ATR band, after first interaction. Departure time is the close
of the second confirming bar. Side is `ABOVE` or `BELOW`.

Post-departure measurement begins with the next completed bar. The two
confirmation bars are excluded from excursion measurement.

Sensitivities: one-close departure; two-close from +/- 0.10 ATR; two-close from
+/- 0.50 ATR. The two-close +/- 0.25 ATR definition remains primary.

## 12. Post-departure excursion

At 5, 15, 30, 60 and 120 minutes, in the departure direction: directional
displacement from the departed band boundary in ATR; maximum favourable and
maximum adverse excursion in ATR; maximum distance from the atomic peak;
average directional speed in ATR per minute and points per minute; maximum
rolling five-minute speed; time to reach 0.25, 0.50, 1.00, 1.50 and 2.00 ATR;
probability of reclaiming the +/- 0.25 ATR band; probability of touching the
exact atomic zone again; probability of crossing through the peak and exiting
the opposite side.

Results are separated by residence bucket B0-B4. The central question is
whether more prior residence predicts faster, slower, larger or more persistent
departure. This is not converted into a trading strategy: no entries, stops,
targets or profit factor.

## 13. Ordinary-bin controls

Controls are ordinary profile bins from the same frozen profile.

Primary neutral control: one non-peak profile bin drawn from the middle
25%-75% of the profile-bin weight distribution. For a multi-bin equal-weight
atomic plateau, an ordinary contiguous window of the same width is used when
available.

Secondary mass-matched control: profile weight as close as possible to the
atomic peak without qualifying as a local prominent peak.

A control is excluded when it is part of, or touches, any qualifying atomic
peak or plateau; when it contains the profile POC; or when it extends beyond
the frozen grid. The two families stay separate throughout.

Because most atomic HVNs are expected to be one bin, exact width matching is
acceptable. If plateau controls are too sparse, plateau events are reported
descriptively rather than relaxing width after viewing results.

## 14. Matching

Cross-session nearest-neighbour matching within the same relationship, year,
allocation method, bin ratio, prominence threshold, approach side, atomic width
in bins and control family.

Matching covariates: minute from interaction-window start; ATR at touch;
15-minute pre-touch displacement; 15-minute pre-touch path efficiency; distance
from interaction open; distance from profile POC. No forward metric enters
eligibility or distance.

No hard pass/fail matching gate is created. Reported: treated count, control
count, matched count, unique economic episodes, unmatched reasons, post-match
balance, and results **with and without** matching. Descriptive all-event
atomic tables remain valid even where a matched-control lane is sparse.

## 15. Economic episodes

Definition events are clustered as one physical interaction when they share
contract, relationship and interaction session, with touch times within 5
minutes, peak centres within 0.25 ATR, and the same approach side. Both raw
definition events and unique economic episodes are reported. Parameter
duplicates are never treated as independent.

## 16. Parameter reporting

Results stay visible by relationship, proxy, bin ratio, prominence threshold,
POC versus non-POC peak, one-bin peak versus multi-bin plateau, complete
development year, and partial 2026 separately. No single best configuration is
selected.

A result is **stable** when nearby bin-size and prominence definitions tell
approximately the same story rather than repeatedly changing sign.

## 17. Evidence classification

`SUPPORTED`, `SUGGESTIVE`, `NOT_SUPPORTED`, `UNSTABLE`, `UNDERPOWERED`,
`INVALID`, per `STAGE_02_GENERATION_3_GATE.md`. Negative findings are valid. No
pair-count gate may suppress descriptive output.
