# Front-month selection — validation evidence

Dataset: Google Drive `NQ 1s data 2010-2026`, 1,943,304,871 bytes,
142,750,604 rows, 286 row groups, read over HTTP byte ranges.

Scope of this check: row groups 190–213, covering sessions 2023-01-17 to
2023-12-08 (280 sessions). One year only; the full-history check is still to run.

## Selection

Highest-volume instrument per session, among instruments quoting at outright
price levels (>= 50% of the session's highest price, which excludes calendar
spreads regardless of their sign).

| instrument_id | leads from | leads to | tenure |
|---|---|---|---|
| 20631 | 2023-01-17 | 2023-03-12 | truncated by window |
| 3522 | 2023-03-13 | 2023-06-11 | 91 days |
| 2130 | 2023-06-12 | 2023-09-10 | 91 days |
| 260937 | 2023-09-11 | 2023-12-08 | truncated by window |

## Result

`verified: True`, no failed checks.

- median dominance **0.999** of outright volume
- minimum interior tenure **91 days**
- **3** switches, each 4–5 days before the quarterly third Friday
  (2023-03-17, 2023-06-16, 2023-09-15)

Rolling several days ahead of expiry is the real convention for this contract,
and it is not a pattern an incorrect mapping would reproduce.

## Spreads

Observed directly at row group 200 (2023-06-02 to 2023-06-14):

| instrument_id | volume share | last close |
|---|---|---|
| 3522 | 69.1% | 14,922.75 |
| 2130 | 24.3% | 15,106.75 |
| 1584 | 6.6% | 184.70 |

15,106.75 − 14,922.75 = 184.00. Instrument 1584 is the calendar spread between
the two outrights and quotes a **positive** price. A sign test alone therefore
does not exclude spreads; the price-magnitude filter does.

## Status

This remains a labeled **inference**, not a symbology mapping. It is sufficient
to proceed with IS work on 2023-adjacent data; the same check must pass across
2010–2026 before the mapping is used for the full study, and a real definitions
file would supersede it.

---

# Full-history validation (all 286 row groups)

Scanned the complete file: 142,750,604 rows, 4,990 sessions,
2010-07-07 through 2026-08-06.

Every year passes all five checks. No year failed.

| year | sessions | switches | median dominance | min tenure | verdict |
|---|---|---|---|---|---|
| 2010 | 152 | 2 | 0.999 | 91 | OK |
| 2011 | 309 | 4 | 0.999 | 91 | OK |
| 2012 | 311 | 4 | 1.000 | 91 | OK |
| 2013 | 306 | 4 | 1.000 | 91 | OK |
| 2014 | 302 | 4 | 0.999 | 89 | OK |
| 2015 | 312 | 4 | 0.999 | 91 | OK |
| 2016 | 310 | 4 | 0.999 | 91 | OK |
| 2017 | 309 | 4 | 0.998 | 91 | OK |
| 2018 | 312 | 4 | 0.998 | 91 | OK |
| 2019 | 312 | 4 | 0.999 | 91 | OK |
| 2020 | 312 | 4 | 0.999 | 90 | OK |
| 2021 | 311 | 4 | 0.998 | 89 | OK |
| 2022 | 310 | 4 | 0.999 | 91 | OK |
| 2023 | 310 | 4 | 0.999 | 91 | OK |
| 2024 | 313 | 4 | 0.998 | 91 | OK |
| 2025 | 312 | 4 | 0.999 | 90 | OK |
| 2026 | 187 | 2 | 0.998 | 89 | OK |

Four switches per full year, tenure of 89–91 days, and dominance at or above
0.998 in every year including the thinnest early ones. That is the quarterly
H/M/U/Z cycle reproducing itself sixteen years running.

The concern that early years might follow a different ID convention or be too
thin to resolve is not borne out: 2010 and 2011 look like 2025.

## Status

The mapping remains a labeled **inference** rather than vendor symbology, and a
real definitions file would supersede it. It is now validated across the full
history and is sufficient to proceed with the study.
