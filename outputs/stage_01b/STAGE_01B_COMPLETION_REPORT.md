# Stage 1B Completion Report

## Outcome

```text
STAGE_01_PROFILE_FOUNDATION = PASS
```

Stage 1B amended the authoritative profile/signal instrument to NQ and replaced
the historical visual criterion with independent code, oracle, property, and
real-data numerical evidence. No chart, SVG, PNG, PDF, candlestick, or visual
profile artifact was generated or reviewed.

## 1–3. Repository

- Starting SHA:
  `6aec1594745a1e2081f6a433106674c9bf0162db`.
- Branch: `main`.
- Final SHA and push status: reported by final `git rev-parse HEAD`,
  `git ls-remote origin refs/heads/main`, and the handoff response.

## 4–8. Data accessed

| Archive | SHA-256 | Parsed market years |
|---|---|---|
| `nq2021.zip` | `0336cfac5fe804a4c756ff9372a0bad314e526c389e5dd8da3774883a29b2f62` | 2021 |
| `nq2023.zip` | `c982860543d8db5d18d9cbe751d9655f8e46bf76ae5513b7fd7a9dcd7b740773` | 2023 |
| `nq2025.zip` | `b4fcf58ff5db70d2a8d45d605ce5a2742ab003a1cf694ef2721a04562b6608e2` | 2025, partial 2026 |

Metadata identifies `NQ.FUT`. Rows contain individual NQ contract and spread
symbols. Timestamps are UTC `Z` text; the Databento OHLCV convention is interval
start, with completed-bar availability one minute later. The files are
parent-symbol extracts, not a documented continuous series. Vendor roll
methodology is `UNKNOWN`.

No 2020, 2022, or 2024 CSV fields were parsed. `nq2018.zip` and `nq2020.zip`
were not opened, listed, hashed, or otherwise accessed in Stage 1B.

## 9. Files inspected

All permanent controls and Stage 1 evidence; every production module under
`src/hvn/`; all tests; archive metadata/manifests/member names; and permitted
market sections documented in `research/hvn/PARTITION_ACCESS_LOG.csv`.
Historical SVG files were not opened.

## 10. Files changed

- Instrument/control contracts: root README/AGENTS/architecture/decisions/
  limitations/status/progress files and all affected `research/hvn/` contracts.
- Production: NQ ingestion/model guard, one-contract enforcement, complete zero
  bins, actual source-range midpoint, exact Decimal/Fraction conservation, and
  typed empty-ledger schemas.
- Verification: independent oracle, findings/code/data audit reports,
  property/metamorphic and regression tests, archive audit and real
  reconciliation scripts.
- Evidence: five compact JSON/CSV artifacts under `outputs/stage_01b/`.
- Historical synthetic visual artifacts were unchanged.

## 11. Specification-to-code audit

Thirty material contracts were independently reconciled. Findings:

| ID | Severity | Finding | Result |
|---|---|---|---|
| F-01 | HIGH | mixed contract symbols were not rejected | RESOLVED |
| F-02 | HIGH | zero-weight interior bins were omitted | RESOLVED |
| F-03 | MEDIUM | plateau used bin-envelope rather than source midpoint | RESOLVED |
| F-04 | LOW | empty ledgers omitted headers | RESOLVED |
| F-05 | MEDIUM | real uniform totals retained sub-1e-33 aggregation residual | RESOLVED |

No unresolved critical or high finding remains. Timestamp interval semantics and
vendor roll methodology remain informational ambiguities, explicitly recorded.

## 12. Independent fixtures

All 6/6 passed with zero oracle and production differences:

1. uniform single/multi-bin conservation;
2. exact-boundary high exclusion;
3. POC weighted-mean tie-break;
4. POC midpoint/lower fallback;
5. flat plateau/baseline/prominence/node;
6. overlapping-node merge.

## 13–15. Real NQ reconciliation

Sixteen profiles passed: four families × two fixed source dates × two
allocation methods. All selected `NQH5` using only volume in the 72 hours before
source start.

- Uniform source volume: **1,598,303**
- Uniform allocated volume: **1,598,303**
- Uniform difference: **0**
- TPO expected intersections: **57,260**
- TPO actual intersections: **57,260**
- Every production bin matched the independent calculator exactly.
- POC, peak, qualifying-candidate, and final-HVN records were serialized for
  numerical reconciliation.

## 16–18. Tests and determinism

- Property seed: `20250724`.
- Properties cover input reorder, outside/post-freeze additions, bar splitting,
  volume scaling, whole-bin price translation, pre-open partition blocking,
  random Decimal conservation, independent TPO totals, and byte reruns.
- Full suite: **65 passed**.
- Sixteen of sixteen post-freeze before/after ledger hashes matched.
- All five compact Stage 1B artifacts were byte-identical on repeated
  generation.

## 19. Known limitations

- One-minute OHLCV supports proxy profiles, not transaction volume-at-price.
- NQ evidence does not establish MNQ volume equivalence or MNQ execution.
- Parent archives include individual contracts and spreads; roll method is
  unknown.
- Scheduled missing-bar classification needs an authoritative calendar.
- No predictive, interaction, control, return, MFE/MAE, or trading analysis was
  performed.

## 20. Gate

All 17 revised criteria pass. Evidence is in
`research/hvn/STAGE_01_GATE.md`.

## 21. Next authorized action

```text
Design and execute Stage 2:
HVN versus matched non-HVN acceptance study.
```

Stage 2 was not begun.
