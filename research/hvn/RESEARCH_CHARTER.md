# Research Charter

## Objective and classification

This is an original Auction Market Theory-inspired hypothesis. Stage 1's sole
objective is to construct auditable frozen MNQ historical profile proxies and
extract locally prominent HVN zones. It does not test whether an HVN changes
later behavior.

The primary method is a **uniform bar-volume allocation proxy**, not exact
exchange volume at price. The secondary method is a **TPO/range-occupancy
proxy**. MNQ one-minute OHLCV lacks transaction-level volume-at-price.

## Stage boundary

Stage 1 does not authorize return labels, MFE/MAE, trades, entries, stops,
targets, performance metrics, profile selection by performance, HVN grade
optimization, validation access, holdout access, controls, or continuously
developing profiles.

## Causal invariant

`source_bar_close_time <= profile_freeze_time < eligible_interaction_time`.
Only completed one-minute bars may contribute. ATR and bin size are frozen at
source start. A profile is immutable after source end/freeze.

## Preserved later research definitions (not implemented)

For a future first revisit into frozen node H:

- raw residence `T` is minutes from first entry through confirmed departure;
- normalized residence `R_T = (T × ATR_1m_at_touch) / HVN_width`;
- inside-close share `R_C = completed closes inside H / bars from touch through
  departure confirmation`;
- mean range-overlap `R_O` averages
  `length(bar_range ∩ H) / bar_range`, with an explicit zero-range rule;
- midpoint crossings count completed directional side changes around
  `(hvn_low + hvn_high) / 2`;
- path efficiency is
  `abs(departure_price - initial_touch_price) /
  sum(abs(one_minute_price_changes))`, with price field frozen later.

Exploratory residence bins are R0 `<1`, R1 `[1,2)`, R2 `[2,4)`, R3 `[4,8)`,
and R4 `>=8`. They are not grades.

A later matched-control study must match non-HVN zones on width, time of day,
profile family, profile age, current-price distance, current volatility,
preceding displacement, and prior consolidation characteristics.
