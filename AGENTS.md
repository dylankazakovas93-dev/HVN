# Agent Instructions

This repository is in Stage 2: the preregistered NQ HVN acceptance and
rotation study on development years only. Stage 1B is frozen and passed.

Hard prohibitions:

- Do not access, parse, summarize, or calculate from 2020, 2022, or 2024
  market-data rows.
- Do not compute forward returns, MFE, MAE, win rate, profit factor, Sharpe,
  net profit, trades, stops, targets, or entries.
- Do not optimize profile, node, event, control, metric, matching, gate,
  residence, or departure definitions using later behavior.
- Do not call the proxies exact or true exchange volume-at-price profiles.
- Do not claim NQ profile results transfer automatically to MNQ execution.
- Do not generate or regenerate charts, SVG, PNG, PDF, candlestick, or visual
  profile artifacts. Historical synthetic SVG files may remain.
- Do not begin later stages automatically.
- Do not access 2018.
- Do not pool incompatible relationship lanes into one headline result.
- Do not use post-touch outcomes for control construction or matching.

Maintain `source_bar_close_time <= profile_freeze_time <
eligible_interaction_time`. Use completed bars, `America/New_York`, NQ tick
size 0.25, immutable frozen profiles, stable ordering, explicit exclusions, and
preserved source row IDs.

Authoritative profile and signal market: NQ. Eventual execution market: MNQ,
not yet tested.

Follow the locked `research/hvn/STAGE_02_*.md` specifications. Run `pytest`
before claiming correctness. Record every engineering/sample run in
`RUN_REGISTRY.csv` and every data access in
`research/hvn/PARTITION_ACCESS_LOG.csv`.
