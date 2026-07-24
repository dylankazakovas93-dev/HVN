# Decisions

## D-001 — Source timestamp semantics

Databento `ohlcv-1m` `ts_event` denotes the interval start. The ingestion
adapter adds one minute and stores the result as `Bar.close_time`; only that
completed-bar time is used for causality.

## D-002 — Instrument guard

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
