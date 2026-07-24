# Revised Stage 01 Gate

```text
STAGE_01_PROFILE_FOUNDATION = PASS
```

Stage 1B replaces the historical visual-audit criterion with independent code
inspection, hand-calculated oracle fixtures, and real NQ numerical
reconciliation. Existing historical SVG files are not gate evidence.

| # | Stage 1B criterion | Status | Evidence |
|---:|---|---|---|
| 1 | NQ-authoritative amendment fully documented | PASS | README, D-007, charter, data/profile/HVN contracts |
| 2 | Supplied data confirmed as NQ | PASS | `reviews/STAGE_01B_DATA_AUDIT.md`; metadata `NQ.FUT`; NQ row symbols |
| 3 | No unresolved critical/high code-audit finding | PASS | `reviews/STAGE_01B_CODE_AUDIT.md`; F-01/F-02 resolved |
| 4 | Independent oracle fixtures exactly match production | PASS | 6/6; `outputs/stage_01b/oracle_reconciliation.json` |
| 5 | Real NQ uniform profiles conserve volume | PASS | 1,598,303 source = 1,598,303 allocated; difference 0 |
| 6 | Real NQ TPO totals match independent counts | PASS | 57,260 expected = 57,260 actual |
| 7 | POC and HVN outputs reconcile numerically | PASS | all production bins independently equal; oracle O03–O06 |
| 8 | Four profile families work on real NQ | PASS | 4 profiles per family; 16 total |
| 9 | Both allocation methods work on real NQ | PASS | 8 uniform + 8 TPO |
| 10 | All ATR bin ratios exercised | PASS | 0.05 ×2, 0.10 ×12, 0.20 ×2 |
| 11 | All prominence thresholds exercised | PASS | 1.5 ×1, 2.0 ×14, 2.5 ×1 |
| 12 | Post-freeze mutation tests pass | PASS | before/after ledger SHA-256 equal for 16/16 profiles |
| 13 | Property and metamorphic tests pass | PASS | deterministic seed 20250724; `tests/test_properties.py` |
| 14 | Full test suite passes | PASS | 65 tests; final command in run registry |
| 15 | Repeated outputs are byte-identical | PASS | all five Stage 1B output artifacts hash-identical on rerun |
| 16 | No 2020/2022/2024 data accessed | PASS | partition access log; parsed years 2021/2023/2025/2026 only |
| 17 | All work committed and pushed | PASS | final `main` equals `origin/main` |

## Continuing limitations

- NQ one-minute OHLCV provides proxy profiles, not exact transaction
  volume-at-price.
- Parent extracts include individual contracts and spreads; vendor roll
  methodology is `UNKNOWN`.
- NQ results do not establish MNQ volume equivalence or MNQ executability.
- Scheduled missing-bar classification remains unavailable without an
  authoritative session/contract calendar.

## Next authorized action

```text
Design and execute Stage 2:
HVN versus matched non-HVN acceptance study.
```

Stage 2 was not begun here.
