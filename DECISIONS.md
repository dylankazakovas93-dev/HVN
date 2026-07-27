# Decisions

## D-001 — Source timestamp semantics

Databento `ohlcv-1m` `ts_event` denotes the interval start. The ingestion
adapter adds one minute and stores the result as `Bar.close_time`; only that
completed-bar time is used for causality.

## D-002 — Original Stage 1 instrument guard (historical)

The authoritative instrument is MNQ. Outright symbols must begin with `MNQ` and
must not contain `-`. NQ and calendar spreads are rejected. The supplied
archives are therefore unsuitable for empirical Stage 1 MNQ audits.

## D-003 — Exact arithmetic

Price, volume, ATR, bin membership, weights, and tie-breaking use
`decimal.Decimal`. The global grid origin is 0.00 and MNQ tick size is 0.25.

## D-004 — Local baseline sufficiency

At least two non-plateau bins are mechanically required for a local median
baseline. Fewer bins yield a recorded `insufficient_local_baseline_bins`
rejection. This prevents a one-observation "surrounding" baseline and was
declared before empirical MNQ behavior was viewed.

## D-005 — Zero baseline

A positive peak over a zero median baseline has infinite prominence and
qualifies at any finite Stage 1 threshold. The case is explicitly labeled
`zero_baseline_positive_peak`; division by zero is never attempted.

## D-006 — Holiday and roll responsibility

The generic engine consumes an explicitly selected source window and already
selected outright MNQ bars. Holiday calendars, early closes, and causal
front-contract selection are upstream responsibilities and remain blocked
pending authoritative MNQ data documentation. No silent roll stitching occurs.

## D-007 — Stage 1B authoritative-instrument amendment

Effective 2026-07-24:

```text
AUTHORITATIVE PROFILE MARKET = NQ
AUTHORITATIVE SIGNAL MARKET = NQ
EVENTUAL EXECUTION MARKET = MNQ, NOT YET TESTED
```

This supersedes D-002 and the MNQ portions of D-006 for new work without
erasing the historical decision. NQ and MNQ volume distributions are not
assumed identical. No MNQ execution or NQ-to-MNQ portability test has occurred.
Only outright NQ contracts may enter one profile. Calendar spreads are excluded
and recorded.

## D-008 — Causal audit-sample contract selection

For a real-data profile, choose the outright NQ contract with greatest
aggregate volume in a fixed 72-hour lookback ending at profile source start.
Ties resolve by symbol. Selection therefore uses no source-window or
post-freeze information. This is an audit-sample rule, not a claim about the
vendor's roll methodology, which remains `UNKNOWN`.

## D-009 — Stage 1B conformance corrections

Independent inspection recorded F-01 through F-04 in
`reviews/STAGE_01B_FINDINGS.md` before correction. The engine now rejects mixed
contract symbols, materializes zero-weight bins across the full profile range,
and uses actual source-range midpoint for plateau tie-breaking. These are
conformance fixes, not changes to the research hypothesis.

## D-010 — Stage 2 cross-session primary matching amendment

Before any Stage 2 empirical access, the original same-session primary rules
were found to require both touch-time difference at most 60 minutes and
nonoverlapping 120-minute forward windows, which is impossible. Authorized
`STAGE_02_SPECIFICATION_AMENDMENT_01` makes different-session matching primary
and same-session matching descriptive secondary. All Stage 2 gates use only
cross-session pairs. The original defect and its non-empirical detection are
preserved in `research/hvn/STAGE_02_AMENDMENT_01.md`.

## D-011 — Voided 2021/2023 checkpoints and derived dataset identity

The `dataset_hash` values recorded for the accepted 2021 and 2023 Stage 2
checkpoints do not match the archives they name, while a control row for the
same field on nq2025 matches exactly. Evidence and reasoning are in
`reviews/STAGE_02_DATA_IDENTITY_FINDING.md` as F-05. Neither checkpoint's
ledgers were ever committed, so no artifact exists to re-identify.

Both runs are void. Their original registry and access-log rows are retained
unchanged as the record of the attempt; the recomputation supersedes them, and
their claimed row counts are not used as reconciliation targets. Dataset
identity is now computed by the runner from the bytes ingested rather than
recorded by hand.

## D-012 — 2019 restored to the Stage 2 development partition

`PARTITIONS.json` declares development years 2019, 2021, 2023, 2025 and partial
2026. The Stage 2 runner defined sources for 2021, 2023, 2025 and 2026 only, so
2019 was never registered or run. 2019 is supplied by the nq2018 archive, whose
member spans 2018-01-01 to 2019-12-30 and is read under the same year-prefix
guard. The Stage 2 recomputation covers all five declared partitions. This
restores the locked partition rather than changing it.

## D-013 — Streaming ledger writer after the 2025 out-of-memory kill

The 2025 checkpoint was killed by the kernel out-of-memory killer at 15.99 GB
resident during its write phase (`dmesg`: `Out of memory: Killed process 7874`).
`write_deterministic_gzip_csv` materialized the whole ledger four times over —
the normalized rows, the CSV payload, its UTF-8 encoding, and the compressed
buffer — while every other ledger's rows were still live.

The writer now streams normalized rows to the compressor in 50,000-row batches.
`GzipFile.flush()` is never called, because it emits a `Z_SYNC_FLUSH` marker
that changes the compressed bytes; an earlier `TextIOWrapper` version was
rejected for exactly that reason. Output is byte-identical to the previous
in-memory path, verified against it for unsorted and sorted writes and at
0, 1, 49,999, 50,000 and 50,001 rows.

No research definition, caliper, metric or ordering is affected. Row
normalization and sort order are unchanged; only the number of simultaneous
copies in memory changed.

## D-014 — Corrected forbidden-partition guard test

`test_validation_holdout_and_2018_archives_have_no_stage02_access` asserted
that no Stage 2 access row names `nq2018`. That premise is wrong. Archive
names do not partition the data: `nq2021.zip` carries forbidden 2022 rows and
is legitimately read for 2021, while `nq2018.zip` carries 2018 and the declared
development year 2019 and is legitimately read for 2019. The old assertion
would have blocked a declared development partition while permitting an
archive that genuinely contains forbidden rows.

The replacement asserts the invariant that matters: no Stage 2 access row may
record 2020, 2022 or 2024 in its parsed-years column, and no row may name
nq2020.zip, which is wholly a frozen validation partition. This is a stricter
guard on real leakage and a correction of a false one.

## D-015 — Stage 2 matching Amendment 02 and generation increment

Generation 1 primary matching produced 42 cross-session pairs and returned
`UNDERPOWERED` for every gate and relationship. Exact `zone_width_bins`
equality fragmented 3,235 treated events into 3,092 strata. An eligibility-only
diagnosis, computed without consulting any outcome metric, identified that
stratum as the binding constraint.

Authorized: exact `zone_width_bins` equality is replaced by an ATR-normalized
width caliper `0.67 <= W_C/W_T <= 1.50`, a `1.0 * abs(log(W_T/W_C))` distance
term, and post-match width balance reporting. Year, approach side, relationship,
allocation method, bin ratio, prominence threshold and control family remain
exact strata. All Amendment 01 calipers are retained.

This is a new matching generation under section 13, not a bug fix. Generation 1
artifacts are preserved unchanged in `outputs/stage_02/`; Generation 2 is
written to `outputs/stage_02_generation_2/`. Details in
`research/hvn/STAGE_02_AMENDMENT_02.md`.

`STAGE_02_GENERATION_1_MATCHING = UNDERPOWERED` labels the matching design, not
the HVN hypothesis.

## D-016 — 2019 partition restored to Stage 2 aggregation

`scripts/aggregate_stage_02.py` declared `YEARS = (2021, 2023, 2025, 2026)`,
excluding the declared development year 2019 whose ledgers were computed and
accepted under `S02-RECOMP-2019-001`. No specification authorizes that
exclusion and D-012 restored 2019 to the partition set, so this is an
implementation defect. Generation 2 aggregates all five declared partitions.
No event-generation recomputation is required.

Generation 1 remains as produced, over four partitions. Generation 1 and
Generation 2 pair counts are therefore not directly comparable.

## D3-005 — Session-normalized atomic node definition (Generation 3 Amendment 01)

Pilot V1's relative-prominence-only detector inverted the selection: dense
peaks were rejected because their neighbours were also heavy, while sparse tail
bumps qualified because theirs were nearly empty. 25 of 6,019 peaks contained
the POC and the widest zone spanned 51 bins and 6.10 ATR. Diagnosed entirely
from structural quantities, with no forward outcome inspected.

Authorized replacement `SESSION_NORMALIZED_ATOMIC_NODES` combines
profile-normalized volume concentration, TPO concentration, retained local
prominence, a hard 1-5 bin width limit, explicit POC treatment with a
prominence exemption, and 70% volume and TPO value areas as annotations.

All normalization occurs inside the single completed frozen source profile, so
overnight and RTH profiles are never compared by raw volume. Thresholds are
frozen in `research/hvn/STAGE_02_GENERATION_3_AMENDMENT_01.md` and were not
searched.

Pilot V1 is preserved and labelled
`GENERATION_3_PILOT_V1 = REJECTED_STRUCTURAL_DEFINITION`. Its forward-outcome
tables remain unread. Pilot V2 writes to
`outputs/stage_02_generation_3_atomic_pilot_v2/`.

## D3-006 — Zero local baseline fails rather than qualifies

V1 treated a zero neighbourhood median as infinite prominence and qualified the
candidate. Under Amendment 01 a zero baseline makes prominence undefined and
the candidate fails the prominence condition. Combined with the session-relative
volume floor, this closes the path by which empty neighbourhoods admitted
trivial bumps.

## D3-007 — POC exempt from local prominence, not from concentration

A profile's maximum-volume price can sit among heavy neighbours, which is
precisely the case V1 rejected. `POC_ATOMIC` is therefore exempt from the
prominence threshold and from the TPO density floor, but must still satisfy the
1-5 bin width limit, valid totals, and a zone volume density ratio of at least
1.50. POC and non-POC nodes remain separate classes everywhere.

## D3-008 — Composite volume/TPO atomic nodes (Generation 3 Amendment 02)

Pilot V2 passed every structural condition but produced 2,681 unique POC nodes
against 43 unique non-POC nodes, with R01 and R02 contributing none. That is a
population-definition problem measured from frozen source-profile structure, not
an outcome finding, and no forward outcome was inspected.

Authorized replacement `COMPOSITE_VOLUME_TPO_ATOMIC_NODES` detects non-POC
candidates from a composite activity profile, the geometric mean of the volume
and TPO density ratios, and qualifies them on zone volume density 1.25, peak
volume density 1.50, zone TPO density 1.00, composite activity 1.35 and width
1-5 bins. Thresholds are fixed and may not be tuned after any outcome.

Pilot V2 is labelled
`GENERATION_3_PILOT_V2 = STRUCTURALLY_VALID_BUT_SUPERSEDED_BEFORE_OUTCOME_ANALYSIS`
and preserved intact. Pilot V3 writes to a separate directory.

## D3-009 — Local prominence becomes descriptive, TPO stays in the detector

V2 required non-POC nodes to clear a local prominence of 1.50 against their
+/- 0.50 ATR neighbourhood, which vetoes a busy price embedded among other busy
prices. Prominence is now recorded for volume, TPO and composite activity as an
annotation and analysis stratum, and may not appear as a rejection reason.

TPO remains in both candidate discovery and qualification. The volume profile
allocates each completed bar's volume uniformly across the bins its range
intersects, so it is a proxy rather than transaction-level volume at price;
time-at-price is the independent corroboration. The geometric mean collapses
toward zero when either input does, so neither can compensate for the other's
absence.

## D3-010 — Final Generation 3 detector (Amendment 03)

Pilot V3 passed every structural condition but accepted 28,489 unique non-POC
nodes, 91.4% of accepted unique nodes, about eight per profile, with a median
local activity prominence near 1.07 and a minimum below 1.00. Nodes weaker than
their own local background were qualifying. Discovered from structural
quantities only; no forward outcome was inspected.

Authorized final definition `GLOBAL_SIGNIFICANCE_AND_LOCAL_DISTINCTNESS` adds
two gates to the Amendment 02 floors: `peak_activity_percentile >= 90.0`
against the active bins of the same completed source profile, and
`local_activity_prominence >= 1.10` on composite activity over the frozen
+/- 0.50 ATR neighbourhood. All Amendment 02 floors are retained unchanged.

The Amendment 01 veto of 1.50 volume prominence stays rejected: 1.10 on
composite activity requires only that a node exceed its background, not that it
be isolated. POC rules, value areas and the profile model are unchanged.

Pilot V3 is preserved and labelled
`GENERATION_3_PILOT_V3 = STRUCTURALLY_VALID_BUT_SUPERSEDED_BEFORE_OUTCOME_ANALYSIS`.
No further detector amendment is authorized after Pilot V4 unless a mechanical
or causal defect is found.

## D3-011 — Percentile and prominence conventions frozen

`peak_activity_percentile` is `100 * |{active bins with strictly lower
activity}| / |{active bins}|`, so ties share the lowest percentile of their
group, matching the convention already used elsewhere. It uses exact Decimal
arithmetic and integer counts, is platform-independent, and uses no future data.
Exactly 90.0 passes.

`local_activity_prominence` divides the candidate's peak composite activity by
the median composite activity of the +/- 0.50 ATR neighbourhood excluding the
candidate's own bins. A missing, empty, zero or nonpositive baseline is invalid
and fails the gate; a zero baseline is never infinite prominence. Exactly 1.10
passes. Volume and TPO prominence remain annotations and cannot veto.

## D-G3-001 — Pre-empirical defect: bin-level TPO occupancy

The first implementation of `post_touch_TPO_concentration_ratio` counted one
TPO per bar that intersected the node, and one per bar that intersected the
reference band. That is a **zone-touch frequency**, not TPO occupancy, and it
inflated the ratio with bar width: a single bar spanning the whole band produced
a node TPO capture share of 1 and a ratio of `band_bins / node_bins` rather
than 1.

The locked activity specification requires bin-level occupancy. Corrected so
each completed post-touch bar adds one TPO to **every bin it occupies**:

```text
T_node = sum of bin-level TPO counts across node bins
T_band = sum of bin-level TPO counts across all reference-band bins
node_TPO_capture_share = T_node / T_band
node_width_share       = node_bin_count / band_bin_count
ratio                  = capture share / width share
```

A bar spanning the complete band now yields exactly 1 at any node width.

The binary counts are retained separately as `bars_touching_node`,
`bars_touching_band` and `node_touch_bar_share`. They are descriptive and are
structurally excluded from the composite metric, which is asserted by test.

**No empirical outcome was generated under the incorrect implementation.** The
defect was found and corrected before the outcome pipeline was wired and before
any partition was run, so no result, ledger, summary or statistic requires
recomputation. Eight regression fixtures cover the band-spanning bar, the
node-only bar, the non-node bar, a hand-built three-bar occupancy matrix,
zero-range bars, the half-open boundary convention, the composite using the
corrected ratio, and the exclusion of binary counts from the composite.

I had previously recorded this behaviour as an inherent property of per-bar TPO
construction. That characterization was wrong.
