# Stage 01 Gate

Overall: **BLOCKED**

The deterministic engine is implemented, but empirical MNQ audit evidence cannot
be produced from the supplied NQ archives.

| # | Criterion | Status | Evidence |
|---:|---|---|---|
| 1 | Generic engine constructs four families | PASS | `src/hvn/engine.py`, session parametrized tests |
| 2 | Both allocation methods | PASS | `AllocationMethod`, conservation/TPO tests |
| 3 | Three ATR ratios | PASS | engine whitelist and rounding tests |
| 4 | ATR/bin size frozen causally | PASS | `atr_before`, immutable profile, warm-up tests |
| 5 | Uniform volume conservation | PASS | conservation test and ledger totals |
| 6 | Exact TPO counts | PASS | TPO hand fixture |
| 7 | Deterministic POC | PASS | POC and byte-equality tests |
| 8 | Deterministic local prominence | PASS | isolated/plateau/equality/zero baseline tests |
| 9 | Deterministic boundaries/merges | PASS | boundary, overlap, and touch tests |
| 10 | Frozen profiles cannot mutate | PASS | frozen dataclass test |
| 11 | DST/session boundaries | PASS | spring, autumn, midnight, family tests |
| 12 | No validation/holdout market rows accessed | PASS | `PARTITION_ACCESS_LOG.csv`; parsed rows list only 2021/2023/2025 |
| 13 | Byte-identical authoritative ledgers | PASS | repeat ledger test; synthetic manifest rerun |
| 14 | Visual artifacts agree with numerical ledgers | BLOCKED | synthetic engineering pack exists; empirical MNQ pack unavailable |
| 15 | All tests pass | PASS | 52 passed; `PYTHONPATH=src pytest` |
| 16 | Exact reproduction commands documented | PASS | `README.md` |
| 17 | Work committed and pushed | PASS | `main` pushed to `origin/main`; see repository log |

No causal, allocation, freeze, session, or partition defect is currently known.
The remaining blocker is authoritative MNQ data, not permission to substitute NQ.
