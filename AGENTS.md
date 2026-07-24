# Agent Instructions

This repository is in Stage 1: profile construction and HVN extraction only.

Hard prohibitions:

- Do not access, parse, summarize, or calculate from 2020, 2022, or 2024
  market-data rows.
- Do not compute forward returns, MFE, MAE, win rate, profit factor, Sharpe,
  net profit, trades, stops, targets, or entries.
- Do not optimize profile, node, residence, or departure definitions using
  later behavior.
- Do not call the proxies exact or true exchange volume-at-price profiles.
- Do not substitute NQ for MNQ.
- Do not begin later stages automatically.

Maintain `source_bar_close_time <= profile_freeze_time <
eligible_interaction_time`. Use completed bars, `America/New_York`, MNQ tick
size 0.25, immutable frozen profiles, stable ordering, explicit exclusions, and
preserved source row IDs.

Run `pytest` before claiming correctness. Record every engineering/sample run in
`RUN_REGISTRY.csv` and every data access in
`research/hvn/PARTITION_ACCESS_LOG.csv`.
