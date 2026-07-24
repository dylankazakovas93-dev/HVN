# Profile Specification

## Frozen bin size

Use the most recent completed Wilder ATR(24) available at or before source
start. Ratios are 0.05, 0.10, and 0.20. For raw size `ATR × ratio`:

`max(0.25, round_half_up(raw / 0.25) × 0.25)`.

The raw and rounded values are ledger fields and cannot change during formation.
Insufficient ATR warm-up rejects the profile.

NQ and MNQ both use a 0.25-point minimum tick, but this profile is constructed
from NQ only. MNQ execution has not been tested.

## Grid and bar intersection

Grid origin is 0.00. Bins are `[bin_low, bin_high)`. Low maps with floor.
For a nonzero range, the highest intersected index is `ceil(high / size) - 1`,
so a high exactly on a boundary does not create a bin above the traded high. A
zero-range bar maps to exactly `floor(price / size)`.

Every bin from the minimum through maximum observed profile index is
materialized. Unintersected interior bins have zero weight and participate in
local-baseline and adjacency calculations.

## Proxies

Uniform bar-volume allocation divides a bar's full volume equally across all
intersected bins. Allocated total must equal authoritative source-bar volume
within decimal tolerance. TPO adds one unit to every intersected bin and never
uses volume as a weight.

## POC

POC maximizes proxy weight. Ties resolve by closest center to proxy-weighted
mean price, then closest center to profile range midpoint, then lower price.
All operations use exact decimals and price-ascending stable output.

This is not an exact exchange volume-at-price profile.
