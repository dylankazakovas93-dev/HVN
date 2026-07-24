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
