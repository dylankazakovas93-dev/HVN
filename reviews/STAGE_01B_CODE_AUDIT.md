# Stage 1B Independent Code Audit

Audit date: 2026-07-24  
Starting SHA: `6aec1594745a1e2081f6a433106674c9bf0162db`  
Scope: Stage 1 profile/HVN construction only

The auditor inspected every production module and every test directly. Test
success was treated as evidence, not proof. Expected arithmetic was separately
implemented under `reviews/reference_stage_01b/` without importing production
profile or HVN constructors.

## Reconciliation matrix

| audit_id | Written requirement | Implementation | Test/evidence | Independent interpretation | Status | Consequence / correction |
|---|---|---|---|---|---|---|
| A01 | Use completed bars only | `models.py:22-44`; `io.py:16-79` | `test_source_start_included_source_end_excluded_and_post_freeze_ignored` | Databento interval-start timestamp is converted to close availability by +1 minute. | PASS | None |
| A02 | Source start inclusive; source end exclusive | `engine.py:95-101` | boundary test; 16 real profiles | Selection is on interval start and additionally requires close no later than freeze. | PASS | None |
| A03 | Freeze equals source end and no post-freeze mutation | `models.py:54-71`; `engine.py:95-101` | property test; all 16 before/after hashes equal | A bar beginning at freeze is excluded. | PASS | None |
| A04 | ATR uses information available by source start | `atr.py:8-46`; `engine.py:91-94` | ATR completed-bar test; real reconciliation timestamps | `<= source_start` admits the completed bar ending exactly at source start, which is then available. | PASS | None |
| A05 | One causal contract per ATR/profile | `atr.py:12-21`; `engine.py:106-115` | mixed-contract regression tests | Starting code could mix contracts; F-01 was recorded and fixed. | PASS | Mixed-symbol input now raises. |
| A06 | DST and New York session behavior | `sessions.py:8-31` | spring/autumn DST and family tests | IANA `America/New_York` offsets and UTC elapsed times are correct. | PASS | None |
| A07 | ETH crosses midnight | `sessions.py:23-26` | `test_eth_crosses_midnight`; real 930-bar sessions | Prior-date 18:00 through current-date 09:30 is constructed explicitly. | PASS | None |
| A08 | Stable source ordering and duplicate handling | `engine.py:95-111`; `atr.py:12-21` | reorder property; duplicate tests; archive audit | Sort key is close time then source row ID; duplicate symbol/timestamp and row ID reject. | PASS | None |
| A09 | Wilder ATR(24) | `atr.py:20-37` | 24-bar hand fixture; real ATR ledger fields | Seed is arithmetic mean of first 24 true ranges; later values use Wilder recurrence. | PASS | None |
| A10 | Raw size = ATR × ratio; ratios locked | `engine.py:28-31,89-94` | rounding parametrization; real 0.05/0.10/0.20 cases | Only the three preregistered ratios are accepted. | PASS | None |
| A11 | Round-half-up to 0.25 with minimum tick | `engine.py:28-31` | half-tick fixtures; oracle O01/O02 | Explicit Decimal `ROUND_HALF_UP`, not banker rounding. | PASS | None |
| A12 | Bin grid origin 0 and `[low, high)` | `engine.py:22-43` | six boundary fixtures; oracle O02 | Floor low and `ceil(high/size)-1` implement exact boundary-high exclusion. Zero range maps once. | PASS | None |
| A13 | Materialize full profile range | `engine.py:131-132` | untraded-bin regression; oracle O01 | Starting code omitted interior zeros; F-02 was recorded and fixed. | PASS | Baseline/adjacency now sees zero bins. |
| A14 | Uniform `volume/N` and per-bar conservation | `engine.py:117-131` | conservation tests; oracle O01; all real bins | A 1e-50 Decimal allocation quantum is used; each bar's last bin receives its exact residual. | PASS | Deterministic representational precision is explicit. |
| A15 | Exact aggregate profile conservation | `engine.py:133-145` | random property; 1,598,303/1,598,303 real units | Exact `Fraction` reconciliation applies the aggregate residual to highest bin. F-05 was recorded before correction. | PASS | Every real ledger reports zero difference. |
| A16 | TPO adds one per bar/bin, not volume | `engine.py:126-130` | TPO unit test; random oracle; real reconciliation | Volume is never read in the TPO branch. | PASS | 57,260 expected and actual. |
| A17 | POC hierarchy | `engine.py:60-76,153-160` | separate unique/mean/midpoint/lower tests; oracle O03/O04 | Lexicographic key implements all four stages in order. | PASS | None |
| A18 | Plateau grouping and representative | `hvn.py:9-45` | plateau tests; oracle O05 | Full equal run is one candidate; representative uses proxy mean, actual source midpoint, then lower. F-03 fixed. | PASS | None |
| A19 | Edge-bin peak behavior | `hvn.py:39-42` | independent inspection; oracle edge bins | Missing neighbor is negative infinity, matching locked “missing edge lower” convention. | PASS | None |
| A20 | ±0.50 ATR baseline; plateau excluded; median; minimum two | `hvn.py:46-60` | isolated, plateau, insufficient-baseline tests; O05/O06 | Center-distance comparison is inclusive and candidate plateau indices are excluded. | PASS | None |
| A21 | Zero baseline and prominence equality | `hvn.py:61-68` | zero-baseline/equality tests | Positive peak over zero becomes Infinity; `>=` admits 1.5/2.0/2.5 equality. | PASS | None |
| A22 | Boundary = 50% of peak; equality included | `hvn.py:95-101` | boundary fixture; O05/O06 | Both expansion comparisons use `>=`. | PASS | None |
| A23 | Touch/overlap merge; no double count | `hvn.py:102-115` | overlap/touch tests; oracle O06 | Half-open bin zones merge when next low equals prior high; combined bins are enumerated once. | PASS | None |
| A24 | Node totals, width, share, IDs, representative | `hvn.py:111-145` | node tests; all real ledgers | Totals/width/share/IDs reconcile. Post-merge node-share tie stage is equal for all candidates and therefore informationally redundant; later tie stages remain deterministic. | PASS | No behavioral correction required. |
| A25 | Immutable frozen result and deterministic serialization | `models.py:86-105`; `ledger.py:12-88` | frozen test; byte reruns | Frozen dataclasses and fixed field/order formatting produce stable bytes. Empty ledgers now retain headers after F-04. | PASS | None |
| A26 | Forbidden partitions block before archive open | `partitions.py:5-18`; `io.py:29-40` | filename tests and monkeypatched pre-open property | Explicit forbidden-year path raises before `ZipFile`. Mixed development archives check a raw line's year prefix before parsing fields. | PASS | No forbidden market row was field-parsed. |
| A27 | NQ instrument identity | `io.py:55-78`; `DATA_CONTRACT.md` | archive audit JSON | Metadata says `NQ.FUT`; row symbols are NQ contracts/spreads. Outright loader excludes spreads. | PASS | MNQ execution remains untested. |
| A28 | Timestamp convention discoverable from source | `io.py:24-28`; archive audit | schema/header/sequence inspection | `Z` UTC representation is explicit. “Interval start” is a Databento OHLCV schema convention, not self-described in the CSV body. | AMBIGUOUS | Informational limitation; no critical/high consequence. |
| A29 | Roll methodology | upstream sample rule; D-008 | sample-selection JSON | Parent extract is not continuous. Audit selection is causal and explicit; vendor roll method is undocumented. | AMBIGUOUS | Recorded as `UNKNOWN`; no silent inference. |
| A30 | No visual gate evidence | Stage 1B scripts/tests | repository diff and run registry | Historical SVG code/files remain, but Stage 1B commands emit only JSON/CSV and tests no longer call the visual generator. | PASS | None |

## Findings disposition

| Finding | Severity | Disposition | Regression evidence |
|---|---|---|---|
| F-01 mixed contract symbols | HIGH | RESOLVED | ATR/profile mixed-contract tests |
| F-02 omitted zero bins | HIGH | RESOLVED | production untraded-bin test and oracle O01 |
| F-03 plateau midpoint mismatch | MEDIUM | RESOLVED | actual-source-midpoint plateau test |
| F-04 empty ledger schema | LOW | RESOLVED | typed empty-ledger implementation |
| F-05 aggregate Decimal residual | MEDIUM | RESOLVED | exact real conservation and random property |

No unresolved critical or high finding remains.

## Files inspected

Production:

`src/hvn/atr.py`, `sessions.py`, `engine.py`, `hvn.py`, `ledger.py`,
`models.py`, `io.py`, `partitions.py`, `audit.py`, `cli.py`, and `__init__.py`.

Tests:

`tests/conftest.py`, `test_atr_sessions.py`, `test_engine.py`, `test_hvn.py`,
`test_partitions_io.py`, the historical `test_audit.py`, and the Stage 1B
property suite.

Specifications and evidence:

all root control documents, every file under `research/hvn/`, the Stage 1
completion report, run/access registries, and the historical synthetic manifest.
Historical SVG files were not opened or regenerated.
