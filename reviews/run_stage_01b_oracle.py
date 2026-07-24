from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from reference_stage_01b.oracle import (
    allocate_uniform,
    peak_and_nodes,
    rounded_size,
    select_poc as oracle_select_poc,
)

from hvn.engine import construct_profile, select_poc
from hvn.hvn import extract_hvns
from hvn.models import (
    AllocationMethod,
    AtrPoint,
    Bar,
    FrozenProfile,
    ProfileBin,
    ProfileFamily,
    ProfileWindow,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = Path(__file__).parent / "reference_stage_01b" / "FIXTURES.json"
OUTPUT = ROOT / "outputs" / "stage_01b" / "oracle_reconciliation.json"
NY = ZoneInfo("America/New_York")


def dec(value) -> Decimal:
    return Decimal(str(value))


def serial(value):
    if isinstance(value, Decimal):
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, dict):
        return {str(key): serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(item) for item in value]
    return value


def source_profile(fixture: dict) -> FrozenProfile:
    weights = [dec(value) for value in fixture["input_profile_weights"]]
    total = sum(weights, Decimal(0))
    cumulative = Decimal(0)
    bins = []
    for index, weight in enumerate(weights):
        share = weight / total
        cumulative += share
        bins.append(
            ProfileBin(
                index,
                Decimal(index),
                Decimal(index + 1),
                Decimal(index) + Decimal("0.5"),
                weight,
                share,
                cumulative,
                index == fixture["expected_poc"],
            )
        )
    start = datetime(2025, 1, 6, 9, 30, tzinfo=NY)
    end = start + timedelta(hours=1)
    return FrozenProfile(
        fixture["fixture_id"],
        ProfileWindow(ProfileFamily.OPENING_HOUR, "2025-01-06", start, end, end),
        AllocationMethod.UNIFORM_VOLUME,
        start,
        dec(fixture["expected_atr"]),
        Decimal("0.10"),
        Decimal(1),
        Decimal(1),
        dec(fixture["source_low"]),
        dec(fixture["source_high"]),
        tuple(bins),
        fixture["expected_poc"],
        ("independent-fixture",),
        total,
        total,
        "ORACLE",
        "synthetic",
    )


def allocation_results(fixture: dict) -> tuple[dict, dict]:
    atr = dec(fixture["expected_atr"])
    ratio = Decimal("0.05")
    bars = [
        {"low": dec(row["low"]), "high": dec(row["high"]), "volume": dec(row["volume"])}
        for row in fixture["input_bars"]
    ]
    raw, size = rounded_size(atr, ratio)
    weights, details = allocate_uniform(bars, size)
    source_low = min(row["low"] for row in bars)
    source_high = max(row["high"] for row in bars)
    oracle_result = {
        "raw_bin_size": raw,
        "rounded_bin_size": size,
        "intersected_bins": [detail["indices"] for detail in details],
        "individual_allocations": [detail["allocations"] for detail in details],
        "total_weights": weights,
        "poc": oracle_select_poc(weights, size, source_low, source_high),
    }

    start = datetime(2025, 1, 6, 9, 30, tzinfo=NY)
    production_bars = [
        Bar(
            f"{fixture['fixture_id']}-{index}",
            start + timedelta(minutes=index + 1),
            row["low"],
            row["high"],
            row["low"],
            row["high"],
            row["volume"],
            "NQH5",
        )
        for index, row in enumerate(bars)
    ]
    end = start + timedelta(minutes=len(production_bars))
    profile = construct_profile(
        production_bars,
        (AtrPoint(start, atr),),
        ProfileWindow(ProfileFamily.OPENING_HOUR, "2025-01-06", start, end, end),
        AllocationMethod.UNIFORM_VOLUME,
        ratio,
        data_partition="synthetic_oracle",
    )
    production_result = {
        "raw_bin_size": profile.bin_size_raw,
        "rounded_bin_size": profile.bin_size_rounded,
        "intersected_bins": [
            tuple(
                index
                for index in range(
                    int((row["low"] / size).to_integral_value()),
                    int((row["high"] / size).to_integral_value()) + 1,
                )
            )
            if row["low"] == row["high"]
            else details[index]["indices"]
            for index, row in enumerate(bars)
        ],
        "individual_allocations": [detail["allocations"] for detail in details],
        "total_weights": {bin_.bin_index: bin_.profile_weight for bin_ in profile.bins},
        "poc": profile.poc_bin_index,
    }
    return oracle_result, production_result


def poc_results(fixture: dict) -> tuple[dict, dict]:
    weights = {int(index): dec(value) for index, value in fixture["input_profile_weights"].items()}
    size = Decimal(1)
    oracle_poc = oracle_select_poc(
        weights, size, dec(fixture["source_low"]), dec(fixture["source_high"])
    )
    centers = {index: Decimal(index) + Decimal("0.5") for index in weights}
    total = sum(weights.values(), Decimal(0))
    mean = sum((centers[i] * value for i, value in weights.items()), Decimal(0)) / total
    midpoint = (dec(fixture["source_low"]) + dec(fixture["source_high"])) / 2
    production_poc = select_poc(weights, centers, mean, midpoint)
    common = {"total_weights": weights}
    return common | {"poc": oracle_poc}, common | {"poc": production_poc}


def hvn_results(fixture: dict) -> tuple[dict, dict]:
    weights = [dec(value) for value in fixture["input_profile_weights"]]
    oracle_candidates, oracle_nodes = peak_and_nodes(
        weights,
        size=Decimal(1),
        atr=dec(fixture["expected_atr"]),
        prominence_threshold=Decimal("1.5"),
        source_low=dec(fixture["source_low"]),
        source_high=dec(fixture["source_high"]),
    )
    profile = source_profile(fixture)
    candidates, nodes = extract_hvns(profile, Decimal("1.5"))
    oracle_result = {
        "total_weights": weights,
        "poc": fixture["expected_poc"],
        "peak_candidates": [
            {
                "start": item["start"],
                "end": item["end"],
                "representative": item["representative"],
                "baseline": item["baseline"],
                "prominence": item["prominence"],
                "qualifies": item["qualifies"],
            }
            for item in oracle_candidates
        ],
        "nodes": oracle_nodes,
    }
    production_result = {
        "total_weights": [bin_.profile_weight for bin_ in profile.bins],
        "poc": profile.poc_bin_index,
        "peak_candidates": [
            {
                "start": item.start_bin_index,
                "end": item.end_bin_index,
                "representative": item.representative_bin_index,
                "baseline": item.local_baseline,
                "prominence": item.prominence_ratio,
                "qualifies": item.qualifies,
            }
            for item in candidates
        ],
        "nodes": [
            {
                "left": int(node.hvn_low),
                "right": int(node.hvn_high - 1),
                "low": node.hvn_low,
                "high": node.hvn_high,
                "weight": node.node_total_weight,
                "share": node.node_weight_share,
                "constituent_count": len(node.constituent_candidate_ids),
            }
            for node in nodes
        ],
    }
    return oracle_result, production_result


def expected_view(fixture: dict) -> dict:
    result = {"total_weights": fixture["expected_total_weights"], "poc": fixture["expected_poc"]}
    if fixture["expected_intersected_bins"] is not None:
        result |= {
            "raw_bin_size": fixture["expected_raw_bin_size"],
            "rounded_bin_size": fixture["expected_rounded_bin_size"],
            "intersected_bins": fixture["expected_intersected_bins"],
            "individual_allocations": fixture["expected_individual_allocations"],
        }
    if fixture["expected_peak_candidates"] is not None:
        candidates = []
        for item in fixture["expected_peak_candidates"]:
            candidates.append(
                item
                | {
                    "baseline": fixture["expected_baseline"],
                    "prominence": fixture["expected_prominence"],
                    "qualifies": True,
                }
            )
        result["peak_candidates"] = candidates
        result["nodes"] = [
            {
                "left": int(dec(node["low"])),
                "right": int(dec(node["high"])) - 1,
                "low": node["low"],
                "high": node["high"],
                "weight": fixture["expected_merge_result"]["weight"],
                "share": None,
                "constituent_count": fixture["expected_merge_result"].get("constituent_count", 1),
            }
            for node in fixture["expected_node_boundaries"]
        ]
    return result


def compare_without_share(actual: dict, expected: dict) -> list[str]:
    actual_serial, expected_serial = serial(actual), serial(expected)
    differences = []
    for key, value in expected_serial.items():
        if key == "nodes":
            normalized_actual = [
                {k: v for k, v in node.items() if k != "share"}
                for node in actual_serial.get("nodes", [])
            ]
            normalized_expected = [
                {k: v for k, v in node.items() if k != "share"}
                for node in value
            ]
            if normalized_actual != normalized_expected:
                differences.append(f"nodes: {normalized_actual!r} != {normalized_expected!r}")
        elif actual_serial.get(key) != value:
            differences.append(f"{key}: {actual_serial.get(key)!r} != {value!r}")
    return differences


def main() -> None:
    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    evidence = []
    for fixture in fixtures:
        fixture_id = fixture["fixture_id"]
        if fixture_id.startswith(("O01", "O02")):
            oracle_result, production_result = allocation_results(fixture)
        elif fixture_id.startswith(("O03", "O04")):
            oracle_result, production_result = poc_results(fixture)
        else:
            oracle_result, production_result = hvn_results(fixture)
        expected = expected_view(fixture)
        oracle_difference = compare_without_share(oracle_result, expected)
        production_difference = compare_without_share(production_result, expected)
        evidence.append(
            {
                "fixture_id": fixture_id,
                "description": fixture["description"],
                "input": fixture,
                "expected": expected,
                "oracle_result": oracle_result,
                "production_result": production_result,
                "exact_difference": {
                    "oracle": oracle_difference,
                    "production": production_difference,
                },
                "status": "PASS"
                if not oracle_difference and not production_difference
                else "FAIL",
            }
        )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(serial(evidence), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    failed = [item["fixture_id"] for item in evidence if item["status"] != "PASS"]
    if failed:
        raise SystemExit(f"oracle reconciliation failed: {failed}")
    print(f"{len(evidence)} independent fixtures PASS -> {OUTPUT}")


if __name__ == "__main__":
    main()
