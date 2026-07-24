from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reviews"))

from reference_stage_01b.oracle import allocate_tpo, allocate_uniform, intersected

from hvn.atr import wilder_atr
from hvn.engine import construct_profile
from hvn.hvn import extract_hvns
from hvn.io import databento_rows_from_zip
from hvn.ledger import profile_ledger_bytes
from hvn.models import AllocationMethod, Bar, ProfileFamily
from hvn.sessions import profile_window

ARCHIVE = Path("/Users/mariusvidziunas/Downloads/quant-data-upload/NQ/nq2025.zip")
MEMBER = "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"
OUTPUT = ROOT / "outputs" / "stage_01b"
CODE_SHA = os.environ.get("STAGE_01B_CODE_SHA", "STAGE_01B_WORKTREE")
ANCHORS = (date(2025, 1, 6), date(2025, 1, 7))
LOOKBACK = timedelta(hours=72)

FIELDS = [
    "profile_id",
    "source_file",
    "source_session_date",
    "profile_family",
    "contract_symbol",
    "contract_selection_start",
    "contract_selection_end",
    "contract_selection_volume",
    "source_start",
    "source_end",
    "freeze_time",
    "source_bar_count",
    "first_source_row_id",
    "last_source_row_id",
    "atr_reference_time",
    "atr_value",
    "raw_bin_size",
    "rounded_bin_size",
    "allocation_method",
    "bin_ratio",
    "prominence_threshold",
    "source_total_volume",
    "allocated_total_volume",
    "conservation_difference",
    "tpo_expected_total",
    "tpo_actual_total",
    "number_of_profile_bins",
    "poc_bin",
    "poc_price",
    "number_of_peak_candidates",
    "number_of_qualifying_candidates",
    "number_of_final_hvns",
    "hvn_boundaries",
    "node_total_weights",
    "node_weight_shares",
    "independent_all_bins_exact",
    "independent_checked_bin_indices",
    "post_freeze_mutation_hash_before",
    "post_freeze_mutation_hash_after",
    "result",
]


def choose_contract(bars: tuple[Bar, ...], source_start: datetime) -> tuple[str, Decimal]:
    volumes: dict[str, Decimal] = defaultdict(Decimal)
    lookback_start = source_start - LOOKBACK
    for bar in bars:
        if lookback_start <= bar.start_time < source_start:
            volumes[bar.symbol] += bar.volume
    if not volumes:
        raise ValueError(f"no contract-selection bars before {source_start}")
    symbol = min(volumes, key=lambda candidate: (-volumes[candidate], candidate))
    return symbol, volumes[symbol]


def config(family: ProfileFamily, anchor: date, method: AllocationMethod) -> tuple[Decimal, Decimal]:
    if family == ProfileFamily.PRIOR_RTH and anchor == ANCHORS[0]:
        if method == AllocationMethod.UNIFORM_VOLUME:
            return Decimal("0.05"), Decimal("1.5")
        return Decimal("0.20"), Decimal("2.5")
    if family == ProfileFamily.FULL_OVERNIGHT and anchor == ANCHORS[0]:
        if method == AllocationMethod.UNIFORM_VOLUME:
            return Decimal("0.05"), Decimal("2.0")
        return Decimal("0.20"), Decimal("2.0")
    return Decimal("0.10"), Decimal("2.0")


def source_bars(bars: tuple[Bar, ...], symbol: str, window) -> list[Bar]:
    return sorted(
        [
            bar
            for bar in bars
            if bar.symbol == symbol
            and window.source_start <= bar.start_time < window.source_end
            and bar.close_time <= window.freeze_time
        ],
        key=lambda bar: (bar.close_time, bar.source_row_id),
    )


def independent_weights(profile, bars: list[Bar]) -> dict[int, Decimal]:
    raw = [
        {"low": bar.low, "high": bar.high, "volume": bar.volume}
        for bar in bars
    ]
    if profile.allocation_method == AllocationMethod.UNIFORM_VOLUME:
        weights, _ = allocate_uniform(raw, profile.bin_size_rounded)
        return weights
    return allocate_tpo(raw, profile.bin_size_rounded)


def add_post_freeze_bar(bars: tuple[Bar, ...], profile, symbol: str) -> tuple[Bar, ...]:
    poc = next(bin_ for bin_ in profile.bins if bin_.bin_index == profile.poc_bin_index)
    extra = Bar(
        f"POST-FREEZE-{profile.profile_id}",
        profile.window.freeze_time + timedelta(minutes=1),
        poc.bin_center,
        poc.bin_center,
        poc.bin_center,
        poc.bin_center,
        Decimal(999999),
        symbol,
    )
    return bars + (extra,)


def main() -> None:
    all_bars = databento_rows_from_zip(
        ARCHIVE,
        MEMBER,
        allowed_year=2025,
        start_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end_utc=datetime(2025, 1, 8, 23, tzinfo=timezone.utc),
    )
    records = []
    selection_records = []
    selected_bin_records = []
    for family in ProfileFamily:
        for anchor in ANCHORS:
            window = profile_window(family, anchor)
            symbol, selected_volume = choose_contract(all_bars, window.source_start)
            selected = tuple(bar for bar in all_bars if bar.symbol == symbol)
            points = wilder_atr(selected)
            actual_source = source_bars(selected, symbol, window)
            selection_records.append(
                {
                    "profile_family": family.value,
                    "source_session_date": anchor.isoformat(),
                    "rule": "greatest outright-contract volume in [source_start-72h, source_start); symbol ascending tie-break",
                    "selected_symbol": symbol,
                    "selected_volume": format(selected_volume, "f"),
                    "source_bar_count": len(actual_source),
                }
            )
            for method in AllocationMethod:
                ratio, prominence = config(family, anchor, method)
                profile = construct_profile(
                    selected,
                    points,
                    window,
                    method,
                    ratio,
                    code_sha=CODE_SHA,
                    data_partition="development_2025",
                )
                candidates, nodes = extract_hvns(profile, prominence)
                expected_weights = independent_weights(profile, actual_source)
                production_weights = {
                    bin_.bin_index: bin_.profile_weight for bin_ in profile.bins
                }
                all_bins_exact = expected_weights == production_weights
                checked = sorted(
                    {
                        profile.bins[0].bin_index,
                        profile.poc_bin_index,
                        profile.bins[len(profile.bins) // 2].bin_index,
                        profile.bins[-1].bin_index,
                    }
                )
                for bin_index in checked:
                    production_value = production_weights[bin_index]
                    independent_value = expected_weights[bin_index]
                    selected_bin_records.append(
                        {
                            "profile_id": profile.profile_id,
                            "source_session_date": anchor.isoformat(),
                            "profile_family": family.value,
                            "allocation_method": method.value,
                            "bin_ratio": format(ratio, "f"),
                            "prominence_threshold": format(prominence, "f"),
                            "bin_index": bin_index,
                            "production_weight": format(production_value, "f"),
                            "independent_weight": format(independent_value, "f"),
                            "exact_difference": format(
                                production_value - independent_value, "f"
                            ),
                            "result": "PASS"
                            if production_value == independent_value
                            else "FAIL",
                        }
                    )
                tpo_expected = sum(
                    len(intersected(bar.low, bar.high, profile.bin_size_rounded))
                    for bar in actual_source
                )
                tpo_actual = sum(
                    (bin_.profile_weight for bin_ in profile.bins), Decimal(0)
                )
                if method == AllocationMethod.UNIFORM_VOLUME:
                    conservation = profile.allocated_total_volume - profile.source_total_volume
                else:
                    conservation = Decimal(0)
                before = hashlib.sha256(profile_ledger_bytes(profile)).hexdigest()
                after_profile = construct_profile(
                    add_post_freeze_bar(selected, profile, symbol),
                    points,
                    window,
                    method,
                    ratio,
                    code_sha=CODE_SHA,
                    data_partition="development_2025",
                )
                after = hashlib.sha256(profile_ledger_bytes(after_profile)).hexdigest()
                result = (
                    "PASS"
                    if conservation == 0
                    and all_bins_exact
                    and before == after
                    and (
                        method != AllocationMethod.TPO
                        or Decimal(tpo_expected) == tpo_actual
                    )
                    else "FAIL"
                )
                poc_bin = next(
                    bin_ for bin_ in profile.bins if bin_.bin_index == profile.poc_bin_index
                )
                records.append(
                    {
                        "profile_id": profile.profile_id,
                        "source_file": ARCHIVE.name,
                        "source_session_date": anchor.isoformat(),
                        "profile_family": family.value,
                        "contract_symbol": symbol,
                        "contract_selection_start": (window.source_start - LOOKBACK).isoformat(),
                        "contract_selection_end": window.source_start.isoformat(),
                        "contract_selection_volume": format(selected_volume, "f"),
                        "source_start": window.source_start.isoformat(),
                        "source_end": window.source_end.isoformat(),
                        "freeze_time": window.freeze_time.isoformat(),
                        "source_bar_count": len(profile.source_row_ids),
                        "first_source_row_id": profile.source_row_ids[0],
                        "last_source_row_id": profile.source_row_ids[-1],
                        "atr_reference_time": profile.atr_reference_time.isoformat(),
                        "atr_value": format(profile.atr_value, "f"),
                        "raw_bin_size": format(profile.bin_size_raw, "f"),
                        "rounded_bin_size": format(profile.bin_size_rounded, "f"),
                        "allocation_method": method.value,
                        "bin_ratio": format(ratio, "f"),
                        "prominence_threshold": format(prominence, "f"),
                        "source_total_volume": format(profile.source_total_volume, "f"),
                        "allocated_total_volume": format(profile.allocated_total_volume, "f"),
                        "conservation_difference": format(conservation, "f"),
                        "tpo_expected_total": tpo_expected
                        if method == AllocationMethod.TPO
                        else "",
                        "tpo_actual_total": format(tpo_actual, "f")
                        if method == AllocationMethod.TPO
                        else "",
                        "number_of_profile_bins": len(profile.bins),
                        "poc_bin": profile.poc_bin_index,
                        "poc_price": format(poc_bin.bin_center, "f"),
                        "number_of_peak_candidates": len(candidates),
                        "number_of_qualifying_candidates": sum(
                            candidate.qualifies for candidate in candidates
                        ),
                        "number_of_final_hvns": len(nodes),
                        "hvn_boundaries": "|".join(
                            f"{node.hvn_low}:{node.hvn_high}" for node in nodes
                        ),
                        "node_total_weights": "|".join(
                            format(node.node_total_weight, "f") for node in nodes
                        ),
                        "node_weight_shares": "|".join(
                            format(node.node_weight_share, "f") for node in nodes
                        ),
                        "independent_all_bins_exact": str(all_bins_exact).lower(),
                        "independent_checked_bin_indices": "|".join(map(str, checked)),
                        "post_freeze_mutation_hash_before": before,
                        "post_freeze_mutation_hash_after": after,
                        "result": result,
                    }
                )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "real_nq_reconciliation.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    (OUTPUT / "real_nq_sample_selection.json").write_text(
        json.dumps(selection_records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (OUTPUT / "real_nq_selected_bins.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        fields = list(selected_bin_records[0])
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected_bin_records)
    failures = [record["profile_id"] for record in records if record["result"] != "PASS"]
    if failures:
        raise SystemExit(f"real reconciliation failures: {failures}")
    print(
        f"{len(records)} real NQ profiles PASS; "
        f"{sum(Decimal(r['source_total_volume']) for r in records if r['allocation_method'] == AllocationMethod.UNIFORM_VOLUME.value)} "
        "uniform source volume reconciled"
    )


if __name__ == "__main__":
    main()
