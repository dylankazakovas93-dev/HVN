# Known Limitations

- One-minute OHLCV cannot reconstruct transaction-level volume at price. The
  uniform bar-volume allocation is a proxy; TPO is a range-occupancy proxy.
- Authoritative profile and signal evidence is NQ. It does not establish that
  MNQ has identical volume distributions or that NQ findings transfer to MNQ
  execution.
- The supplied NQ parent-symbol archives contain individual futures contracts
  and calendar spreads, not a documented continuous series.
- Holiday, early-close, and vendor roll-selection rules require authoritative
  NQ source documentation and are not guessed. Vendor roll methodology is
  `UNKNOWN`.
- Bar-volume allocation assumes uniform distribution across every intersected
  bin and contains no intrabar sequencing.
- Float/binary rounding is deliberately avoided, but CSV consumers may display
  decimal values differently.
- Historical synthetic charts are retained but are not Stage 1B evidence and
  were not regenerated or reviewed.
- Stage 1 includes no return labels, revisit logic, residence calculation,
  controls, MFE/MAE, trades, costs, or validation.
- Stage 2 primary controls come from different interaction dates. Matching and
  session-pair inference cannot eliminate unmeasured cross-session regimes.
- Same-session Stage 2 comparisons share a market path and may have overlapping
  forward windows. They are descriptive and cannot enter advancement gates.

## Stage 2 Generation 2 matching

- The authorized width caliper is stated both as `0.67 <= W_C/W_T <= 1.50` and
  as `abs(log(W_T/W_C)) <= log(1.50)`. These differ: the log form admits ratios
  down to `0.6667`. The literal ratio bound is implemented because it is the
  stricter of the two. The consequence is a slightly asymmetric caliper in the
  treated/control roles; roles are fixed by the greedy treated-to-control
  direction, so the rule is well defined, but a control admissible for a given
  treated event is not necessarily admissible were the roles reversed.
- The log-width distance term uses `Decimal.ln()` under a fixed context
  precision. Unlike the other distance components it is not exact arithmetic;
  it is correctly rounded and therefore deterministic, but two widths whose log
  ratio differs below the context precision are indistinguishable to the
  ordering. Ties are broken by control event id, so matching remains
  deterministic.
- Generation 1 aggregated four partitions and Generation 2 aggregates five.
  Pair counts, episode counts and gate statuses are not directly comparable
  across the two generations.
- Generation 1's `UNDERPOWERED` verdict describes the Generation 1 matching
  rule. It is not evidence for or against the HVN hypothesis.
