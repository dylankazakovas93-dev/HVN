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
