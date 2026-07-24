# Stage 1B Findings Register

This register was created during independent code inspection and before the
listed defects were corrected. It preserves the audit chronology required by
Stage 1B.

## F-01 — Multiple contract symbols are not rejected

- Severity: **HIGH**
- Status when recorded: OPEN; current status: RESOLVED
- Files: `src/hvn/atr.py`, `src/hvn/engine.py`
- Finding: ATR and profile construction sort all supplied bars but do not
  require one unique contract symbol. Distinct contracts at different
  timestamps can therefore be combined, and ATR true range can cross contract
  price levels.
- Consequence: a caller could construct a mechanically invalid profile or ATR
  without an exception. The existing duplicate-symbol/timestamp test does not
  cover multiple symbols at different timestamps.
- Required correction: require exactly one symbol in ATR and profile inputs;
  add regression tests; make causal NQ contract selection an explicit upstream
  operation.

## F-02 — Empty bins inside the profile range are omitted

- Severity: **HIGH**
- Status when recorded: OPEN; current status: RESOLVED
- File: `src/hvn/engine.py`
- Finding: the `weights` dictionary contains only bins intersected by at least
  one source bar. Bins between the minimum and maximum observed bin index that
  receive no allocation are absent rather than present with zero weight.
- Consequence: local median baselines, zero-baseline treatment, peak adjacency,
  node expansion, bin count, and cumulative ledgers can differ after a price
  gap. Existing tests manually construct zero bins but do not test production
  construction across an untouched price interval.
- Required correction: materialize every grid bin from the minimum through
  maximum observed index with a zero default; add a regression fixture.

## F-03 — Plateau range-midpoint tie-break uses bin envelope

- Severity: **MEDIUM**
- Status when recorded: OPEN; current status: RESOLVED
- Files: `src/hvn/hvn.py`, `src/hvn/models.py`
- Finding: POC uses the actual source low/high midpoint, while plateau
  representative selection uses the outer profile-bin envelope midpoint. The
  HVN specification says to use the same proximity hierarchy as POC.
- Consequence: a plateau representative can differ when the actual source range
  is not symmetric inside the outer bins.
- Required correction: freeze actual source range low/high in `FrozenProfile`
  and use its midpoint for both POC and plateau representative selection; add a
  regression test.

## F-04 — Empty record ledgers omit their schema

- Severity: **LOW**
- Status when recorded: OPEN; current status: RESOLVED
- File: `src/hvn/ledger.py`
- Finding: an empty candidate or node collection writes a zero-byte file.
- Consequence: downstream reconciliation cannot distinguish a valid empty
  result from an interrupted write without external context.
- Required correction: allow callers to provide the record type/schema and emit
  a header even when no records qualify. This is not a profile-math defect.

## Informational observations

- The merged-node representative's `node_weight_share` tie stage is necessarily
  identical for all constituent candidates after merge. It does not change the
  result; subsequent prominence/POC/price tie-breaks remain deterministic.
- `Decimal` operations are deterministic, but the implementation uses a
  deliberate 40-digit allocation context and the default context elsewhere.
  Real-data reconciliation must confirm serialized equality and conservation.
- Historical synthetic SVG files predate Stage 1B. They may remain, but Stage
  1B will not execute, review, regenerate, or use the visual generator as gate
  evidence.

## F-05 — Aggregate Decimal residual survives per-bar reconciliation

- Severity: **MEDIUM**
- Status when recorded: OPEN; current status: RESOLVED
- File: `src/hvn/engine.py`
- Finding: the first real NQ reconciliation showed uniform-profile
  `allocated_total_volume - source_total_volume` differences between `1e-34`
  and `5e-34`. Every independently recomputed bin matched production and the
  differences were inside the original tolerance. They arise while repeatedly
  aggregating per-bar repeating-decimal allocations into bins.
- Consequence: serialized real ledgers do not show exact zero conservation even
  though every bar's final-bin residual reconciles at the allocation context.
  Stage 1B requires exact conservation evidence.
- Prior test gap: integer/simple synthetic fixtures happened to sum exactly and
  asserted no adversarial repeating-decimal aggregate.
- Required correction: after all per-bar allocations, apply the deterministic
  aggregate residual to the highest profile bin, then assert exact equality.
  Mirror this independently in the reference calculator and add a regression
  assertion from the real reconciliation.
