# Stage 1B NQ Data Contract Audit

Detailed machine-readable evidence:
`outputs/stage_01b/nq_archive_audit.json`.

## Common findings

- Metadata instrument identifier: `NQ.FUT`.
- Dataset/schema: `GLBX.MDP3`, `ohlcv-1m`.
- CSV fields:
  `ts_event,rtype,publisher_id,instrument_id,open,high,low,close,volume,symbol`.
- Compression: ZIP container; market member is Zstandard-compressed CSV.
- Timestamp text: ISO-8601 nanosecond representation with `Z` suffix (UTC).
- Timestamp convention used: Databento OHLCV interval start; completed-bar
  availability is one minute later.
- Series status: parent-symbol extract containing individual NQ contracts and
  calendar spreads. It is not a documented continuous series.
- Vendor roll methodology: `UNKNOWN`.
- Scheduled missing-bar count: `UNKNOWN` without an authoritative
  session/holiday/contract-listing calendar. Observed greater-than-one-minute
  intervals are reported without repair or a claim that each is erroneous.
- No data issue was repaired.

## Archive results

| Archive | SHA-256 | Permitted section | Raw rows | Outright NQ | Spreads | Duplicate symbol/timestamps | Nonpositive volume | Invalid OHLC |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `nq2021.zip` | `0336cfac5fe804a4c756ff9372a0bad314e526c389e5dd8da3774883a29b2f62` | 2021-01-03 23:00Z – 2021-12-31 21:59Z | 507,113 | 454,877 | 52,236 | 0 | 0 | 0 |
| `nq2023.zip` | `c982860543d8db5d18d9cbe751d9655f8e46bf76ae5513b7fd7a9dcd7b740773` | 2023-01-02 23:00Z – 2023-12-29 21:59Z | 507,299 | 456,312 | 50,987 | 0 | 0 | 0 |
| `nq2025.zip` | `b4fcf58ff5db70d2a8d45d605ce5a2742ab003a1cf694ef2721a04562b6608e2` | 2025-01-01 23:00Z – 2026-06-07 23:59Z | 741,444 | 656,207 | 85,237 | 0 | 0 | 0 |

Each archive contains:

```text
condition.json
metadata.json
glbx-mdp3-<coverage>.ohlcv-1m.csv.zst
manifest.json
```

The 2021/2023 scanners stopped when the next raw line's year prefix exceeded
the permitted year; no 2022 or 2024 CSV fields were parsed.

## Duplicates, gaps, and discontinuities

Multiple rows at one timestamp are expected because the parent extract contains
distinct instruments. Repeated timestamps across distinct instruments were
153,671 (2021), 153,892 (2023), and 236,771 (2025/partial-2026). Duplicate
`(timestamp, symbol)` observations were zero in all three permitted sections.

Observed greater-than-one-minute within-contract intervals were 38,115, 38,756,
and 59,394. These include inactive periods, weekends, holidays, and contracts
far from maturity; they are not silently classified as missing bars.

The preregistered discontinuity diagnostic was an absolute same-contract
close-to-next-open change of at least 100 points when elapsed time was at most
two minutes. Counts were 0, 2, and 28. The overall maximum adjacent change can
be larger across long inactive gaps and is reported separately in JSON. No row
was removed or adjusted.

## Real audit sample

The numerical profile sample uses only `nq2025.zip`, 2025-01-01 through
2025-01-08 23:00Z. For each source window, the contract is frozen using greatest
outright-contract volume in the preceding 72 calendar hours, with symbol order
as tie-break. All 16 profiles selected `NQH5`. This is a causal audit-sample
rule, not a vendor roll claim.

The sample dates 2025-01-06 and 2025-01-07 are fixed source dates selected
without later interaction behavior. Source counts were 390 prior-RTH bars, 930
full-overnight bars, 570 midnight bars, and 60 opening-hour bars per date.
