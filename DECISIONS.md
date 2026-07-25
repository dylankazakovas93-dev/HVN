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
