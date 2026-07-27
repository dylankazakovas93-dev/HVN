# Generation 4 Verdict Gate

Status: **LOCKED BEFORE ANY GENERATION 4 FORWARD OUTCOME WAS INSPECTED**

Generation 4 is the **final authorized structural definition** for this
development study. If Generation 4 does not support the mechanism, the
authorized action is to report that plainly and stop — not to invent a
Generation 5 detector.

## Structural gate (precedes the outcome gate)

The 2019 structural pilot must satisfy every condition G4-S01 through G4-S19 in
`STAGE_02_GENERATION_4_ZONE_SPEC.md`. Mechanical and causal conditions
(G4-S01–G4-S12) are hard failures: only a demonstrated implementation defect
may be fixed, and the pilot rerun. Sample-support conditions (G4-S13–G4-S19)
that fail are preserved and reported; the definition is **not** adjusted to
force them.

The zone definition is frozen permanently at structural-pilot acceptance.

## Co-primary hypotheses

```text
H1 — HVN ZONE PRICE ACCEPTANCE
After a first causal touch, HVN zones produce greater 30-minute
inside-close share than activity-matched ordinary zones.

H2 — HVN ZONE ACTIVITY CONCENTRATION
After a first causal touch, HVN zones produce a greater 30-minute composite
volume-TPO concentration ratio inside the complete HVN zone than
activity-matched ordinary zones.
```

Primary control family: `C02_ACTIVITY_MATCHED`. C01 is supporting evidence.
Primary horizon: 30 minutes. POC and non-POC zones are evaluated separately;
the co-primary gate is assessed on **non-POC HVN zones**, with POC zones
reported alongside as a distinct population.

The mechanism is **not** declared supported because one of many secondary
metrics happens to be favourable.

## Verdicts

`SUPPORTED` requires **all** of:

1. H1 and H2 both show the expected sign against C02;
2. both co-primary 95% session-block confidence intervals exclude the null —
   zero for absolute differences, one for ratios;
3. the expected sign appears in at least three of the four full years for each
   hypothesis;
4. leave-one-year-out retains the expected pooled sign;
5. no single year contributes more than 50% of the pooled effect;
6. matching quality is acceptable and no primary lane is `UNDERPOWERED`;
7. episode-level sample size is sufficient;
8. at least two secondary structure metrics corroborate the mechanism;
9. results do not depend on the largest episodes;
10. the effect is not confined to a single zone-width stratum in a way that
    identifies it as a width artefact rather than a zone-geometry effect.

`PARTIALLY_SUPPORTED` applies when one co-primary passes robustly and the other
does not; or evidence is clearly heterogeneous by a predefined structural
category with coherent year consistency; or dose-response is convincing while
the broad population effect is diluted.

`NOT_SUPPORTED` applies when neither co-primary shows robust evidence; or
stronger zones show no coherent dose-response; or pooled effects disappear
across years or robustness checks.

`UNDERPOWERED` applies when matching or episode counts cannot evaluate the
hypotheses.

`INVALID` applies to causal, data-integrity, partition, implementation or
irreproducibility failures.

## Cross-generation discipline

Generation 3 measured a one-tick object and Generation 4 measures a multi-tick
region. A Generation 4 verdict may not be justified by comparison to
Generation 3 numbers, and Generation 3 may not be retroactively described as
evidence about HVN zones.

## Reporting discipline

The final report opens with the research question and reports the verdict
plainly. A negative or inconclusive result is a valid research outcome.
Promotional framing is forbidden. No strategy, entry, stop, target or
profitability figure is produced at any point, and no chart is generated. The
next authorized action after the verdict is to stop — not to begin validation,
holdout testing or strategy work.
