# Stage 2 Data-Identity Finding

Status: **CONFIRMED — PRIOR 2021 AND 2023 CHECKPOINTS VOIDED**

Detected: 2026-07-25, on continuation from branch `stage-02-hvn-acceptance`
at `09e6985`, before any recomputation.

## F-05 — Fabricated dataset hashes in `RUN_REGISTRY.csv`

`RUN_REGISTRY.csv` records a `dataset_hash` for every empirical run. The
recorded values for the two accepted Stage 2 year checkpoints do not match the
archives they name.

| Run | Recorded `dataset_hash` | Actual archive sha256 | Result |
|---|---|---|---|
| `S01B-REAL-003` (nq2025) | `b4fcf58f…6608e2` | `b4fcf58f…6608e2` | match |
| `S02-DATA-2021-003` (nq2021) | `0336c79ff72c…1f21d5f62` | `0336cfac5fe8…29b2f62` | **mismatch** |
| `S02-DATA-2023-001` (nq2023) | `c982e16adbb0…84f0773` | `c982860543d8…b740773` | **mismatch** |

Both mismatched values share their leading characters and their trailing
characters with the true archive digest and differ only in the middle. That is
not the signature of a different file; it is the signature of a value
reproduced from memory rather than computed. The `S01B-REAL-003` row shows the
same registry field being recorded correctly when the digest was actually
taken.

The inner `.csv.zst` members were hashed as well, in case those rows used a
member digest rather than an archive digest. They do not match either:

```text
nq2021 member  5012a9f1685175a7a4d83d5999e37f06abf084f0035c25279e1d01f3ae030750
nq2023 member  fbc646a1be1e854e8aa187290ed74d5b58471367385a97197000267b51a72219
nq2025 member  4a56638dad7a79c8d0d42a28da2a2bab58273fb0b8274f47bf54da05b7dc7cad
```

## Consequence

`RUN_REGISTRY.csv` rows `S02-DATA-2021-003` and `S02-DATA-2023-001`, and
`PARTITION_ACCESS_LOG.csv` rows `PA-024` and `PA-029`, assert `PASS` for two
full-year checkpoints whose inputs cannot be identified. Section 5.6 requires
every run to record dataset identity. These two runs do not satisfy it.

The artifacts themselves were never committed. `write_year_result` writes to
`outputs/stage_02/detailed`, which is absent from the repository at
`09e6985`; the ledgers existed only on the machine that produced them and are
not recoverable. So the claimed row counts in those rows carry no reviewable
evidence of any kind — neither input identity nor output.

## Disposition

Both runs are **VOID**. Their registry and access-log rows are retained
unaltered as the record of what was attempted and why it was rejected; the
recomputation supersedes them. No result from either run is carried forward,
and no count from either is used as a reconciliation target for the
recomputation — a voided number cannot certify its own replacement.

## Correction

`scripts/run_stage_02.py` now computes each archive's sha256 from the bytes it
reads, immediately before ingestion, and writes it into
`checkpoint_<year>.json` together with the member name and the producing code
SHA. Dataset identity is therefore derived from the run rather than asserted
alongside it.
