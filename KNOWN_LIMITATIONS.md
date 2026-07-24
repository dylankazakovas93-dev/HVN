# Known Limitations

- One-minute OHLCV cannot reconstruct transaction-level volume at price. The
  uniform bar-volume allocation is a proxy; TPO is a range-occupancy proxy.
- The supplied archives are NQ, not MNQ, and contain calendar spreads. They
  cannot be used as authoritative MNQ development inputs.
- No empirical MNQ session audit pack has been generated.
- Holiday, early-close, and causal roll-selection rules require authoritative
  MNQ source documentation and are not guessed.
- Bar-volume allocation assumes uniform distribution across every intersected
  bin and contains no intrabar sequencing.
- Float/binary rounding is deliberately avoided, but CSV consumers may display
  decimal values differently.
- Synthetic charts validate mechanics only. They provide no predictive or
  economic evidence.
- Stage 1 includes no return labels, revisit logic, residence calculation,
  controls, MFE/MAE, trades, costs, or validation.
