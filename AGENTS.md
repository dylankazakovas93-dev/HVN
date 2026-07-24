# Agent Instructions

This repository is in Stage 1B: NQ instrument amendment and independent
numerical/code audit.

Hard prohibitions:

- Do not access, parse, summarize, or calculate from 2020, 2022, or 2024
  market-data rows.
- Do not compute forward returns, MFE, MAE, win rate, profit factor, Sharpe,
  net profit, trades, stops, targets, or entries.
- Do not optimize profile, node, residence, or departure definitions using
  later behavior.
- Do not call the proxies exact or true exchange volume-at-price profiles.
- Do not claim NQ profile results transfer automatically to MNQ execution.
- Do not generate or regenerate charts, SVG, PNG, PDF, candlestick, or visual
  profile artifacts. Historical synthetic SVG files may remain.
- Do not begin later stages automatically.

Maintain `source_bar_close_time <= profile_freeze_time <
eligible_interaction_time`. Use completed bars, `America/New_York`, NQ tick
size 0.25, immutable frozen profiles, stable ordering, explicit exclusions, and
preserved source row IDs.

Authoritative profile and signal market: NQ. Eventual execution market: MNQ,
not yet tested.

Run `pytest` before claiming correctness. Record every engineering/sample run in
`RUN_REGISTRY.csv` and every data access in
`research/hvn/PARTITION_ACCESS_LOG.csv`.
