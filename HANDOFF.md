# Handoff — read this first

You are picking up a quantitative market-structure study on NQ futures. This
file exists because the conversation that produced the work does not transfer
between sessions. Everything load-bearing is written down here.

## The one live finding

Everything else in this project came back null. This did not:

**Price reverses off a level more often when several *kinds* of level stack at
the same price.** From Stage 5, on 1-minute data, four years (2019/2021/2023/
2025), 58,877 first-touch events:

- 30 of 30 stacked cells positive, sign test p < 0.000001
- effects of +3 to +7pp, several with 4/4 year agreement
- adverse excursion ~25% lower at 4+ kinds than at 1 kind, favourable excursion
  roughly unchanged — so the mechanism is *price penetrating less far*, not
  bouncing harder
- strongest at 10 minutes, decaying by 120 minutes

Not yet done on it: a session-clustered bootstrap for a confidence interval.
Cells are correlated, so "30 of 30" is one effect measured thirty ways, not
thirty confirmations.

## What is being tested now (Stage 6)

Whether that result survives **accurate** volume. Every earlier stage allocated a
bar's volume *uniformly* across every tick its range touched — a guess. One
second bars usually touch one to three ticks, so the guess mostly disappears.

If the reversal effect survives, it is real. If it evaporates, it was an
artifact of the allocation. Both outcomes are worth reporting.

The test definition is frozen in `research/hvn/STAGE_06_ONE_SECOND_SPEC.md`.
**Do not re-tune it after seeing the new numbers.** That is the entire point of
having frozen it before the data arrived.

## State of play

| step | status |
|------|--------|
| Contract mapping validated, 2010–2026 | done, all 17 years pass |
| Session histogram cache (IS years) | done, 1,654 sessions, committed as an archive |
| Levels from histograms | done, verified on real data |
| **Reversal runner + IS execution** | **not built — this is the next task** |

## Data access

The raw file is a 1.9 GB Parquet in Google Drive, 142,750,604 rows, 2010-07-07
to 2026-08-06. It is read over HTTP byte ranges — never downloaded.

```python
from hvn.range_reader import HTTPRangeReader
import pyarrow.parquet as pq
pq.ParquetFile(HTTPRangeReader(url))     # PyArrow prunes to the row groups it needs
```

Drive serves large files behind a scan interstitial; `scripts/scan_contracts.py`
carries its confirm token in `resolved_url`.

**Contracts.** The file has no symbology — `instrument_id` is a bare number and
calendar spreads sit alongside outrights. The front month is inferred as the
highest-volume instrument quoting at outright price levels, and that inference is
*validated*, not assumed: `src/hvn/contract_selection.py` runs five checks and
all 17 years pass (4 switches a year, 89–91 day tenure, dominance ≥ 0.998).
Evidence in `outputs/stage_06_contract_validation/`.

Two things that will bite anyone who reimplements this:

- **Spreads are not negative.** In June 2023 the NQM3/NQU3 spread quoted +184.70,
  exactly the difference between two outrights at 14,922.75 and 15,106.75. Filter
  spreads by price *magnitude*, not sign.
- **Dominance must be measured against outright volume only.** Count spread
  volume in the denominator and a clean front month looks thin on roll days.

## Caches

`scripts/bootstrap.sh` restores the repo and verifies both caches. Run it first.

The histogram cache is committed as `outputs/stage_06_cache/histograms.tar.gz`
(16 MB) and `HistogramStore` unpacks it automatically when the expanded
directory is missing or **incomplete**. Completeness is judged against the
archive's member count: a partial cache once loaded 5 slices of 286 and reported
a thirtieth of the data while looking perfectly healthy.

Rebuilding from source instead takes about eight minutes:

```bash
PYTHONPATH=src python3 scripts/build_histograms.py --start 0 --end 286
```

## Methodology rules that were learned the hard way

Each of these corrected a real, published-to-the-user wrong answer.

1. **Complete linkage, never single linkage.** Single-linkage clustering chained
   every level on the chart into one blob — barriers 130 ATR wide, and width rose
   with confluence degree, which is the axis under test.
2. **Tolerance is the gap between two levels**, not a margin added to each.
   Widening both made "1 ATR" mean 2 ATR.
3. **Stratify by width.** Excursion measured from band *edges* makes a wide band
   look reversal-prone for geometric reasons. Stage 5 measures from the
   **midpoint** for this reason.
4. **A year with no data did not disagree.** An agreement counter that treated
   missing years as disagreements reported "2/4" for a two-year result and got a
   real effect dismissed. Count only years with data in both arms.
5. **Report the chance rate beside every pass count.** With grids this size a
   null produces passes.
6. **Never tune a threshold after seeing an outcome.**

## Partitions

| set | years |
|-----|-------|
| IS | 2010, 2011, 2012, 2019, 2021, 2023, 2025 |
| OOS | 2013–2018, 2020, 2022, 2024 |
| SEALED | 2026 — opened once, at the very end |

2019/2021/2023/2025 are *burned*: examined repeatedly, so they can never be
out-of-sample again. They are in IS by force. The OOS years are pristine and the
OOS run happens **once**, against the frozen spec.

## Data handling

`nq1sdata`'s AGENTS.md governs the raw file: never modify it, never upload raw
or paid data to GitHub, never load the whole dataset into RAM, never silently
mix contracts, never fill missing bars. The histogram archive is committed here
as a deliberate exception — derived aggregates in a private research repo, so
that a wiped workspace costs seconds instead of a rebuild.

## Environment note

This was developed in a container that discarded the workspace between turns and
capped commands at nine minutes. That is why everything is chunked, resumable,
and committed eagerly. On a normal machine none of that is necessary — the long
runs simply run.
