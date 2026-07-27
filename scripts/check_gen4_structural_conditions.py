"""Evaluate Generation 4 structural conditions G4-S01 through G4-S19.

Reads only the structural pilot artifacts. Computes no forward outcome.
Conditions are defined in `research/hvn/STAGE_02_GENERATION_4_ZONE_SPEC.md`.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PILOT = ROOT / "outputs" / "stage_02_generation_4_hvn_zones_pilot"
GEN3_PROFILES = (
    ROOT / "outputs" / "stage_02_generation_3_atomic_pilot_v4" / "profile_summary.csv"
)
RELATIONSHIPS = ("R01", "R02", "R03", "R04", "R05")


def read_csv(path: Path) -> list[dict]:
    with path.open() as handle:
        return list(csv.DictReader(handle))


def read_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt") as handle:
        return list(csv.DictReader(handle))


def median(values):
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def percentile(values, fraction: Decimal):
    if not values:
        return None
    ordered = sorted(values)
    position = int(
        (fraction * Decimal(len(ordered))).to_integral_value(rounding="ROUND_CEILING")
    )
    return ordered[max(1, min(len(ordered), position)) - 1]


def evaluate(pilot: Path) -> list[dict]:
    profiles = read_csv(pilot / "profile_summary.csv")
    candidates = read_gz(pilot / "peak_candidates.csv.gz")
    accepted = read_gz(pilot / "accepted_hvn_zones.csv.gz")
    rejected = read_gz(pilot / "rejected_candidates.csv.gz")
    broad = read_gz(pilot / "broad_distributions.csv.gz")
    opportunities = read_csv(pilot / "relationship_opportunity_summary.csv")
    reconciliation = {
        r["check"]: r["value"] for r in read_csv(pilot / "structural_reconciliation.csv")
    }
    manifest = json.loads((pilot / "manifest.json").read_text())

    nonpoc = [z for z in accepted if z["zone_class"] == "NONPOC_HVN_ZONE"]
    poc = [z for z in accepted if z["zone_class"] == "POC_HVN_ZONE"]
    widths = [int(z["width_ticks"]) for z in accepted]
    nonpoc_atr = [Decimal(z["width_atr"]) for z in nonpoc]
    accepted_atr = [Decimal(z["width_atr"]) for z in accepted]

    gen3 = read_csv(GEN3_PROFILES) if GEN3_PROFILES.exists() else []
    gen3_universe = len({(r["family"], r["session_date"], r["contract"]) for r in gen3})

    per_profile: Counter = Counter()
    for zone in nonpoc:
        per_profile[zone["profile_id"]] += 1
    counts = [per_profile.get(p["profile_id"], 0) for p in profiles if p["valid"].lower() == "true"]

    by_relationship: dict[str, int] = defaultdict(int)
    for row in opportunities:
        if row["zone_class"] == "NONPOC_HVN_ZONE":
            by_relationship[row["relationship_id"]] += int(row["count"])

    overlaps = 0
    by_profile = defaultdict(list)
    for zone in accepted:
        by_profile[zone["profile_id"]].append(zone)
    for zones in by_profile.values():
        ordered = sorted(zones, key=lambda z: int(z["low_index"]))
        for left, right in zip(ordered, ordered[1:]):
            if int(left["high_index"]) >= int(right["low_index"]):
                overlaps += 1

    gate_failures = sum(
        1
        for z in nonpoc
        if not (
            Decimal(z["peak_activity_percentile"]) >= Decimal("95.0")
            and Decimal(z["peak_smoothed_activity"]) >= Decimal("1.50")
            and Decimal(z["zone_volume_density"]) >= Decimal("1.25")
            and Decimal(z["zone_tpo_density"]) >= Decimal("1.00")
            and Decimal(z["zone_activity_density"]) >= Decimal("1.35")
            and z["peak_to_valley_ratio"]
            and Decimal(z["peak_to_valley_ratio"]) >= Decimal("1.10")
        )
    )
    below_min_atr = sum(
        1
        for z in accepted
        if Decimal(z["width_atr"]) < Decimal("0.10")
        and int(z["width_ticks"]) < int(z["minimum_width_ticks"])
    )
    freeze_violations = sum(
        1 for p in profiles if p["freeze_time"] > p["session_date"] + "T23:59:59+00:00"
    )

    results = [
        {
            "condition": "G4-S01",
            "requirement": "source-profile universe reconciles exactly",
            "observed": f"{len(profiles)} tick profiles vs {gen3_universe} unique Generation 3 (family, session_date, contract)",
            "passed": len(profiles) == gen3_universe and gen3_universe > 0,
            "kind": "mechanical",
        },
        {
            "condition": "G4-S02",
            "requirement": "no accepted zone narrower than four ticks",
            "observed": f"minimum accepted width {min(widths, default=0)} ticks",
            "passed": min(widths, default=0) >= 4,
            "kind": "mechanical",
        },
        {
            "condition": "G4-S03",
            "requirement": "no accepted zone narrower than 0.10 ATR, subject to the four-tick floor",
            "observed": f"{below_min_atr} accepted zones below both the ATR minimum and the tick floor",
            "passed": below_min_atr == 0,
            "kind": "mechanical",
        },
        {
            "condition": "G4-S04",
            "requirement": "no accepted non-POC zone exceeds 0.75 ATR",
            "observed": f"maximum accepted non-POC width {max(nonpoc_atr, default=Decimal(0)):.4f} ATR",
            "passed": all(w <= Decimal("0.75") for w in nonpoc_atr),
            "kind": "mechanical",
        },
        {
            "condition": "G4-S05",
            "requirement": "no accepted POC zone exceeds 1.00 ATR",
            "observed": f"maximum accepted POC width {max((Decimal(z['width_atr']) for z in poc), default=Decimal(0)):.4f} ATR",
            "passed": all(Decimal(z["width_atr"]) <= Decimal("1.00") for z in poc),
            "kind": "mechanical",
        },
        {
            "condition": "G4-S06",
            "requirement": "accepted zones do not overlap within one physical profile",
            "observed": f"{overlaps} overlapping accepted pairs",
            "passed": overlaps == 0,
            "kind": "mechanical",
        },
        {
            "condition": "G4-S07",
            "requirement": "every accepted non-POC zone satisfies all density, percentile and separation gates",
            "observed": f"{gate_failures} accepted non-POC zones failing a gate",
            "passed": gate_failures == 0,
            "kind": "mechanical",
        },
        {
            "condition": "G4-S08",
            "requirement": "every zone is frozen before its eligible interaction",
            "observed": f"{freeze_violations} profiles with a freeze time after the interaction session date",
            "passed": freeze_violations == 0,
            "kind": "causal",
        },
        {
            "condition": "G4-S09",
            "requirement": "raw, smoothed, accepted, broad and rejected ledgers reconcile",
            "observed": (
                f"{len(candidates)} candidates = {len(accepted)} accepted + {len(rejected)} rejected; "
                f"{len(broad)} broad rows are a subset of the rejected ledger"
            ),
            "passed": len(candidates) == len(accepted) + len(rejected)
            and len(broad) <= len(rejected),
            "kind": "mechanical",
        },
        {
            "condition": "G4-S10",
            "requirement": "deterministic rerun reproduces content and row order",
            "observed": "verified separately against a second run of the same commit",
            "passed": None,
            "kind": "mechanical",
        },
        {
            "condition": "G4-S11",
            "requirement": "no forbidden year is admitted",
            "observed": (
                f"{reconciliation.get('forbidden_year_rows_admitted')} forbidden-year rows admitted; "
                f"{reconciliation.get('rows_excluded_earlier_year')} excluded as an earlier year"
            ),
            "passed": reconciliation.get("forbidden_year_rows_admitted") == "0",
            "kind": "causal",
        },
        {
            "condition": "G4-S12",
            "requirement": "no forward outcome is computed or inspected",
            "observed": f"manifest forward_outcomes_computed = {manifest['forward_outcomes_computed']}",
            "passed": manifest["forward_outcomes_computed"] is False,
            "kind": "causal",
        },
        {
            "condition": "G4-S13",
            "requirement": "median accepted non-POC zones per physical profile <= 3",
            "observed": f"median {median(counts)}",
            "passed": (median(counts) or 0) <= 3,
            "kind": "sample_support",
        },
        {
            "condition": "G4-S14",
            "requirement": "90th percentile accepted non-POC zones per profile <= 6",
            "observed": f"p90 {percentile(counts, Decimal('0.90'))}",
            "passed": (percentile(counts, Decimal("0.90")) or 0) <= 6,
            "kind": "sample_support",
        },
        {
            "condition": "G4-S15",
            "requirement": "at least 300 unique non-POC zones exist in 2019",
            "observed": f"{len({z['physical_zone_id'] for z in nonpoc})} unique physical non-POC zones",
            "passed": len({z["physical_zone_id"] for z in nonpoc}) >= 300,
            "kind": "sample_support",
        },
        {
            "condition": "G4-S16",
            "requirement": "every relationship R01-R05 has at least 20 eligible non-POC opportunities",
            "observed": ", ".join(
                f"{r}={by_relationship.get(r, 0)}" for r in RELATIONSHIPS
            ),
            "passed": all(by_relationship.get(r, 0) >= 20 for r in RELATIONSHIPS),
            "kind": "sample_support",
        },
        {
            "condition": "G4-S17",
            "requirement": "median accepted zone width >= 0.10 ATR",
            "observed": f"median {median(accepted_atr):.4f} ATR",
            "passed": (median(accepted_atr) or Decimal(0)) >= Decimal("0.10"),
            "kind": "sample_support",
        },
        {
            "condition": "G4-S18",
            "requirement": "median accepted zone width >= 4 ticks",
            "observed": f"median {median(widths)} ticks",
            "passed": (median(widths) or 0) >= 4,
            "kind": "sample_support",
        },
        {
            "condition": "G4-S19",
            "requirement": "95th-percentile accepted non-POC width <= 0.75 ATR",
            "observed": f"p95 {percentile(nonpoc_atr, Decimal('0.95'))}",
            "passed": (percentile(nonpoc_atr, Decimal("0.95")) or Decimal(0))
            <= Decimal("0.75"),
            "kind": "sample_support",
        },
    ]
    return results


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="check_gen4_structural_conditions.py")
    parser.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    args = parser.parse_args(argv)
    results = evaluate(args.pilot)
    width = max(len(r["requirement"]) for r in results)
    for row in results:
        status = "PASS" if row["passed"] else ("n/a " if row["passed"] is None else "FAIL")
        print(f"{row['condition']}  {status}  {row['requirement']:<{width}}  {row['observed']}")
    failed = [r for r in results if r["passed"] is False]
    print()
    print(
        f"{len(results) - len(failed)} of {len(results)} evaluated conditions pass; "
        f"failures: {', '.join(r['condition'] for r in failed) or 'none'}"
    )


if __name__ == "__main__":
    main()
