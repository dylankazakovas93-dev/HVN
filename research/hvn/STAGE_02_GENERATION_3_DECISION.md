# Stage 2 Generation 3 — Decision Record

## D3-001 — New hypothesis generation

Generations 1 and 2 tested broad, 50%-expanded, merged HVN zones and returned
`UNDERPOWERED`. That study is preserved and closed as:

```text
BROAD_MULTI_BIN_HVN_STUDY = INCONCLUSIVE / UNDERPOWERED
```

Generation 3 tests a different object — the atomic peak — and is therefore a
new hypothesis generation, not a reinterpretation. Generation 1 and 2 artifacts
are never modified, and no Generation 3 metric consumes a broad node.

## D3-002 — Atomic zones reuse the locked peak rules

`hvn.peak_candidates()` already yields the atomic object: a qualifying peak bin
or an exactly equal-weight adjacent plateau, before the 50% expansion and
merging performed by `extract_hvns()`. Generation 3 consumes
`peak_candidates()` directly and applies neither expansion nor merging. No
locked Stage 1 peak rule is changed.

## D3-003 — Stage 1 profiles must be rebuilt

The saved profile ledger holds metadata only, and the opportunity ledger holds
post-expansion broad geometry. Neither preserves per-bin weight, so atomic
peaks cannot be recovered from Generation 1/2 artifacts. Stage 1 profile
construction is rerun from the authorized development archives using
`engine.construct_profile()` unchanged, writing only into
`outputs/stage_02_generation_3_atomic/`.

## D3-004 — 2019 is read from an archive named nq2018.zip

The authorization lists 2019 as authorized and 2018 as forbidden, while the
2019 rows are supplied inside `nq2018.zip`. Consistent with D-014, archive
filenames do not partition data: `nq2021.zip` contains forbidden 2022 rows and
is legitimately read for 2021. The operative guard is the year-prefix check in
`hvn.io`, which stops before parsing any row outside the requested year.

Generation 3 reads 2019 rows from `nq2018.zip` and parses no 2018 row. Every
access is logged with its parsed year. Excluding 2019 would contradict the same
authorization that declares it a development year, and would drop a complete
year from a study whose classification depends on complete-year counts.
