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

## Generation 3 Amendment 01

- The volume profile is an allocation of one-minute OHLCV bar volume across the
  bins each bar's range intersects. It is not transaction-level volume at price
  and must never be described as such. The TPO construction is an independent
  time-at-price proxy over completed bars, not a tick-level measure.
- All thresholds are relative to the single completed source profile. A node
  qualifying in a quiet overnight profile and one qualifying in a busy RTH
  profile are comparable in session-relative terms only; their raw traded
  volumes may differ by a large factor.
- The 70% value areas use a rough contiguous expansion, not the classical
  70%-of-TPO-count construction, and the final added bin may overshoot 70%.
- Value-area location is an annotation in this amendment. If a later generation
  makes it an eligibility filter, that is a new research generation.
- Percentile ranks use a frozen convention in which ties share the lowest
  percentile of their group. Under heavy tying, for example integer TPO counts
  in sparse profiles, a large fraction of bins can share one percentile value.
- The 1-5 bin width limit is a definitional choice, not an empirical one.
  Broad plateaus are preserved and reported, never truncated, but they are
  excluded from atomic interaction events, so the study says nothing about them.

## Generation 3 Amendment 02

- The composite activity score is the geometric mean of two proxies. It
  inherits both proxies' limitations: uniform volume allocation across a bar's
  range, and TPO counted over completed one-minute bars rather than ticks.
- Non-POC eligibility no longer involves any prominence or percentile
  condition. A qualifying non-POC node may sit immediately beside equally
  active prices; that is intended, and it means node isolation must be read
  from the recorded prominence annotations rather than assumed.
- POC and non-POC nodes are qualified by different rules and are never pooled.
  Any comparison between them is a comparison of two differently defined
  populations.
- Sample-support conditions S21-S23 are checked on 2019 alone. Passing them
  there does not guarantee adequate non-POC counts in every later partition.
