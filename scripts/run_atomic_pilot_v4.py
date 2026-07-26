"""Generation 3 Pilot V2 — structural-only session-normalized atomic nodes.

Structural mode constructs profiles, normalized features, POC, both value areas,
candidates, accepted and rejected nodes and controls. It never computes, loads
or writes any forward proximity, residence, departure or excursion result.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from hvn.atomic_v2 import (
    POC_ATOMIC,
    POC_BROAD,
    poc_plateau,
    profile_normalization,
    value_area,
)
from hvn.atomic_v3 import (
    BROAD_COMPOSITE_PLATEAU,
    NONPOC_ATOMIC_HVN,
    select_composite_controls,
)
from hvn.atomic_v4 import classify_final_nodes
from hvn.atr import wilder_atr
from hvn.engine import construct_profile
from hvn.interactions import Relationship
from hvn.io import databento_rows_from_zip
from hvn.models import AllocationMethod
from hvn.sessions import profile_window
from hvn.stage02_ledger import deterministic_csv_bytes, write_deterministic_gzip_csv
from hvn.stage02_pipeline import (
    EXPECTED_SOURCE_MINUTES,
    FAMILY_BY_RELATIONSHIP,
    PROMINENCES,
    RATIOS,
    AtrSelector,
    ContractSelector,
    _consecutive,
    trading_dates,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "stage_02_generation_3_atomic_pilot_v4"
RESERVED = (
    ROOT / "outputs" / "stage_02",
    ROOT / "outputs" / "stage_02_generation_2",
    ROOT / "outputs" / "stage_02_generation_3_atomic",
    ROOT / "outputs" / "stage_02_generation_3_atomic_pilot_v2",
    ROOT / "outputs" / "stage_02_generation_3_atomic_pilot_v3",
)
SOURCES = {
    2019: ("nq2018.zip", "glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst"),
    2021: ("nq2021.zip", "glbx-mdp3-20210101-20221230.ohlcv-1m.csv.zst"),
    2023: ("nq2023.zip", "glbx-mdp3-20230101-20241230.ohlcv-1m.csv.zst"),
    2025: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
    2026: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
}
FORBIDDEN_YEARS = (2018, 2020, 2022, 2024)


def archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="run_atomic_pilot_v4.py",
        description=(
            "Generation 3 Pilot V4 structural-only run. Builds profiles, "
            "normalized features, POC, value areas and atomic nodes. Computes "
            "no forward outcome."
        ),
    )
    parser.add_argument("--year", type=int, choices=sorted(SOURCES), required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--structural-only",
        action="store_true",
        default=True,
        help="the only supported mode in this script; forward outcomes are never computed",
    )
    args = parser.parse_args(argv)
    if not args.structural_only:
        parser.error("this script supports --structural-only mode only")
    output = args.output_root.resolve()
    for reserved in RESERVED:
        if output == reserved or reserved in output.parents:
            parser.error(f"refusing to write into a preserved generation: {output}")
    args.output_root = output
    return args


def build(bars, *, year, code_sha):
    """Structural sweep over every frozen profile in the partition."""
    dates = trading_dates(bars)
    by_symbol = {
        s: tuple(b for b in bars if b.symbol == s)
        for s in sorted({b.symbol for b in bars})
    }
    atrs = {s: AtrSelector(wilder_atr(v)) for s, v in by_symbol.items()}
    selector = ContractSelector(by_symbol)

    profiles, nodes_out, poc_rows, va_rows, tpo_va_rows, bin_rows = [], [], [], [], [], []
    control_rows = []

    for position, current in enumerate(dates):
        if position == 0:
            continue
        prior = dates[position - 1]
        for relationship in Relationship:
            family = FAMILY_BY_RELATIONSHIP[relationship]
            source_date = prior if family.value == "prior_rth" else current
            pwindow = profile_window(family, source_date)
            try:
                symbol = selector.choose(pwindow.source_start)
            except ValueError:
                continue
            selected = by_symbol[symbol]
            source = sorted(
                [b for b in selected
                 if pwindow.source_start <= b.start_time < pwindow.source_end],
                key=lambda b: b.close_time,
            )
            if not _consecutive(source, EXPECTED_SOURCE_MINUTES[family]):
                continue
            atr_point = atrs[symbol].before(pwindow.source_start)
            for ratio in RATIOS:
                built = {}
                for method in AllocationMethod:
                    try:
                        built[method] = construct_profile(
                            source, (atr_point,), pwindow, method, ratio,
                            code_sha=code_sha, data_partition=f"development_{year}",
                        )
                    except ValueError:
                        built = {}
                        break
                if not built:
                    continue
                volume_profile = built[AllocationMethod.UNIFORM_VOLUME]
                tpo_profile = built[AllocationMethod.TPO]
                tpo_by_index = {
                    b.bin_index: b.profile_weight for b in tpo_profile.bins
                }
                norm = profile_normalization(volume_profile, tpo_by_index)
                bins_by_index = {b.bin_index: b for b in volume_profile.bins}
                volume_weights = {
                    b.bin_index: b.profile_weight for b in volume_profile.bins
                }

                base = {
                    "profile_id": volume_profile.profile_id,
                    "relationship_id": relationship.value,
                    "family": family.value,
                    "session_date": current,
                    "contract": symbol,
                    "bin_ratio": ratio,
                    "year": year,
                }
                # One row per constructed Stage 1 profile, so the ledger count
                # matches Generation 1 exactly. Node detection pairs the volume
                # and TPO constructions of the same ratio.
                for method, built_profile in sorted(
                    built.items(), key=lambda item: item[0].value
                ):
                    profiles.append(
                        base | {
                            "profile_id": built_profile.profile_id,
                            "method": method.value,
                            "v_total": sum(
                                (b.profile_weight for b in built_profile.bins),
                                Decimal(0),
                            ),
                            "n_active_paired": norm.n_active,
                            "t_total_paired": norm.t_total,
                            "bin_count": len(built_profile.bins),
                            "atr_value": built_profile.atr_value,
                            "valid": norm.valid,
                            "invalid_reason": norm.invalid_reason,
                            "source_bar_count": len(source),
                        }
                    )
                if norm.valid:
                    bin_rows.append(
                        base | {
                            "mean_active_volume": norm.mean_active_volume,
                            "mean_active_tpo": norm.mean_active_tpo,
                            "positive_volume_bins": sum(
                                1 for b in volume_profile.bins if b.profile_weight > 0
                            ),
                            "positive_tpo_bins": sum(
                                1 for w in tpo_by_index.values() if w > 0
                            ),
                        }
                    )

                run = poc_plateau(volume_profile)
                poc_width = len(run)
                poc_rows.append(
                    base | {
                        "poc_low_bin_index": run[0].bin_index if run else None,
                        "poc_high_bin_index": run[-1].bin_index if run else None,
                        "poc_width_bins": poc_width,
                        "poc_price": run[0].bin_center if run else None,
                        "poc_volume": sum((b.profile_weight for b in run), Decimal(0)),
                        "poc_class": (
                            POC_ATOMIC if 0 < poc_width <= 5 else POC_BROAD
                        ),
                    }
                )

                v_area = value_area(volume_weights, bins_by_index, norm.v_total)
                t_area = value_area(tpo_by_index, bins_by_index, norm.t_total)
                if v_area:
                    va_rows.append(base | {
                        "volume_VAL": v_area.low_price,
                        "volume_VAH": v_area.high_price,
                        "volume_POC": v_area.poc_price,
                        "volume_value_area_volume_share": v_area.covered_share,
                        "volume_value_area_bin_count": v_area.bin_count,
                        "poc_inside": v_area.low_bin_index
                        <= v_area.poc_low_bin_index
                        <= v_area.high_bin_index,
                        "contiguous": v_area.high_bin_index >= v_area.low_bin_index,
                    })
                if t_area:
                    tpo_va_rows.append(base | {
                        "tpo_VAL": t_area.low_price,
                        "tpo_VAH": t_area.high_price,
                        "tpo_POC": t_area.poc_price,
                        "tpo_value_area_tpo_share": t_area.covered_share,
                        "tpo_value_area_bin_count": t_area.bin_count,
                        "poc_inside": t_area.low_bin_index
                        <= t_area.poc_low_bin_index
                        <= t_area.high_bin_index,
                        "contiguous": t_area.high_bin_index >= t_area.low_bin_index,
                    })

                if True:
                    nodes, _ = classify_final_nodes(volume_profile, tpo_by_index)
                    for node in nodes:
                        row = base | {
                            "node_id": node.node_id,
                            "node_class": node.node_class,
                            "geometry": node.geometry,
                            "start_bin_index": node.start_bin_index,
                            "end_bin_index": node.end_bin_index,
                            "width_bins": node.width_bins,
                            "zone_low": node.zone_low,
                            "zone_high": node.zone_high,
                            "zone_width_points": node.width_points,
                            "zone_width_atr": node.width_points / volume_profile.atr_value,
                            "peak_price": node.peak_price,
                            "peak_volume": node.peak_volume,
                            "zone_volume_density_ratio": node.zone_volume_density_ratio,
                            "zone_tpo_density_ratio": node.zone_tpo_density_ratio,
                            "zone_activity_density_ratio": node.zone_activity_density_ratio,
                            "peak_volume_density_ratio": node.peak_volume_density_ratio,
                            "peak_tpo_density_ratio": node.peak_tpo_density_ratio,
                            "peak_activity_density_ratio": node.peak_activity_density_ratio,
                            "volume_percentile": node.volume_percentile,
                            "tpo_percentile": node.tpo_percentile,
                            "activity_percentile": node.activity_percentile,
                            "local_volume_prominence": node.local_volume_prominence,
                            "local_tpo_prominence": node.local_tpo_prominence,
                            "local_activity_prominence": node.local_activity_prominence,
                            "accepted": node.accepted,
                            "rejection_reason": node.rejection_reason,
                            "activity_percentile_band": (
                                "ge_99" if node.activity_percentile >= 99
                                else "ge_95" if node.activity_percentile >= 95
                                else "ge_90" if node.activity_percentile >= 90
                                else "lt_90"
                            ),
                            "code_sha": code_sha,
                        }
                        if v_area:
                            row["inside_volume_value_area"] = (
                                v_area.low_bin_index <= node.start_bin_index
                                and node.end_bin_index <= v_area.high_bin_index
                            )
                            row["distance_to_volume_POC_atr"] = abs(
                                node.peak_price - v_area.poc_price
                            ) / volume_profile.atr_value
                            row["distance_to_volume_VAL_atr"] = abs(
                                node.peak_price - v_area.low_price
                            ) / volume_profile.atr_value
                            row["distance_to_volume_VAH_atr"] = abs(
                                node.peak_price - v_area.high_price
                            ) / volume_profile.atr_value
                        if t_area:
                            row["inside_tpo_value_area"] = (
                                t_area.low_bin_index <= node.start_bin_index
                                and node.end_bin_index <= t_area.high_bin_index
                            )
                            row["distance_to_tpo_POC_atr"] = abs(
                                node.peak_price - t_area.poc_price
                            ) / volume_profile.atr_value
                        nodes_out.append(row)
                    taken: set = set()
                    for node in nodes:
                        if not node.accepted:
                            continue
                        for control in select_composite_controls(
                            volume_profile, tpo_by_index, nodes, node, taken=taken
                        ):
                            taken |= set(range(
                                control.start_bin_index, control.end_bin_index + 1
                            ))
                            control_rows.append(base | {
                                "control_id": control.control_id,
                                "control_family": control.control_family,
                                "matched_node_id": control.matched_node_id,
                                "start_bin_index": control.start_bin_index,
                                "end_bin_index": control.end_bin_index,
                                "width_bins": control.width_bins,
                                "control_low": control.control_low,
                                "control_high": control.control_high,
                                "zone_volume_density_ratio":
                                    control.zone_volume_density_ratio,
                                "zone_tpo_density_ratio":
                                    control.zone_tpo_density_ratio,
                                "zone_activity_density_ratio":
                                    control.zone_activity_density_ratio,
                                "code_sha": code_sha,
                            })
    return profiles, bin_rows, nodes_out, poc_rows, va_rows, tpo_va_rows, control_rows


def summarize(rows, keys, output, name):
    counts = Counter(tuple(str(r[k]) for k in keys) for r in rows)
    out = [dict(zip(keys, k)) | {"count": v} for k, v in sorted(counts.items())]
    fields = tuple(keys) + ("count",)
    (output / name).write_bytes(deterministic_csv_bytes(out, fields, sort_by=fields))
    return out


def main(argv=None) -> None:
    args = parse_args(argv)
    output = args.output_root
    output.mkdir(parents=True, exist_ok=True)
    detail = output / "detailed"
    detail.mkdir(parents=True, exist_ok=True)

    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    archive, member = SOURCES[args.year]
    source = (args.data_root / archive).resolve()
    dataset_hash = archive_sha256(source)
    bars = databento_rows_from_zip(source, member, allowed_year=args.year)
    for bar in bars:
        if bar.close_time.year in FORBIDDEN_YEARS:
            raise AssertionError(f"forbidden partition row parsed: {bar.source_row_id}")

    profiles, bin_rows, nodes, poc_rows, va_rows, tpo_va_rows, controls = build(
        bars, year=args.year, code_sha=code_sha
    )

    for name, rows, sort_by in (
        ("composite_candidates", nodes, ("node_id",)),
        ("accepted_atomic_nodes", [r for r in nodes if r["accepted"]], ("node_id",)),
        ("rejected_atomic_nodes", [r for r in nodes if not r["accepted"]], ("node_id",)),
    ):
        fields = tuple(sorted({k for r in rows for k in r})) if rows else ("record_id",)
        write_deterministic_gzip_csv(
            detail / f"{name}_{args.year}.csv.gz", rows, fields,
            sort_by=tuple(f for f in sort_by if f in fields),
        )

    for name, rows in (
        ("profile_summary.csv", profiles),
        ("composite_bin_summary.csv", bin_rows),
        ("poc_summary.csv", poc_rows),
        ("volume_value_area_summary.csv", va_rows),
        ("tpo_value_area_summary.csv", tpo_va_rows),
    ):
        fields = tuple(sorted({k for r in rows for k in r})) if rows else ("record_id",)
        (output / name).write_bytes(
            deterministic_csv_bytes(rows, fields, sort_by=("profile_id",) if rows else ())
        )

    accepted = [r for r in nodes if r["accepted"]]
    summarize(nodes, ("node_class", "geometry", "width_bins"), output,
              "node_width_summary.csv")
    summarize(accepted, ("relationship_id", "node_class",
                         "inside_volume_value_area"), output,
              "node_location_summary.csv")
    summarize(nodes, ("rejection_reason",), output, "rejection_summary.csv")
    summarize(controls, ("relationship_id", "control_family", "width_bins"),
              output, "control_summary.csv")
    summarize(nodes, ("relationship_id", "node_class"), output, "node_class_summary.csv")
    summarize(
        [r for r in nodes if r["accepted"]],
        ("node_class", "activity_percentile_band"), output,
        "activity_percentile_summary.csv",
    )
    summarize(
        [r for r in nodes if r["accepted"]],
        ("node_class",), output, "prominence_summary.csv",
    )
    fields = tuple(sorted({k for r in controls for k in r})) if controls else ("record_id",)
    write_deterministic_gzip_csv(
        detail / f"composite_controls_{args.year}.csv.gz", controls, fields,
        sort_by=tuple(f for f in ("control_id",) if f in fields),
    )

    reconciliation = [
        {"check": "profiles", "value": len(profiles)},
        {"check": "candidates", "value": len(nodes)},
        {"check": "accepted", "value": len(accepted)},
        {"check": "rejected", "value": len(nodes) - len(accepted)},
        {"check": "accepted_poc_atomic",
         "value": sum(1 for r in accepted if r["node_class"] == POC_ATOMIC)},
        {"check": "accepted_nonpoc",
         "value": sum(1 for r in accepted if r["node_class"] == NONPOC_ATOMIC_HVN)},
        {"check": "poc_broad",
         "value": sum(1 for r in poc_rows if r["poc_class"] == POC_BROAD)},
        {"check": "broad_plateaus_excluded",
         "value": sum(1 for r in nodes if r["geometry"] == BROAD_COMPOSITE_PLATEAU)},
        {"check": "max_accepted_width_bins",
         "value": max((int(r["width_bins"]) for r in accepted), default=0)},
        {"check": "value_areas_contiguous_with_poc_inside",
         "value": sum(1 for r in va_rows if r["poc_inside"] and r["contiguous"])},
        {"check": "value_areas_total", "value": len(va_rows)},
        {"check": "controls", "value": len(controls)},
        {"check": "tpo_value_areas_contiguous_with_poc_inside",
         "value": sum(1 for r in tpo_va_rows if r["poc_inside"] and r["contiguous"])},
        {"check": "tpo_value_areas_total", "value": len(tpo_va_rows)},
        {"check": "value_areas_below_70pct",
         "value": sum(1 for r in va_rows
                      if Decimal(str(r["volume_value_area_volume_share"])) < Decimal("0.70"))},
    ]
    (output / "structural_reconciliation.csv").write_bytes(
        deterministic_csv_bytes(reconciliation, ("check", "value"), sort_by=("check",))
    )

    artifacts = {}
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            artifacts[str(path.relative_to(output))] = {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
    manifest = {
        "generation": "GENERATION_3_PILOT_V4_GLOBAL_AND_LOCAL",
        "amendment": "STAGE_02_GENERATION_3_AMENDMENT_03",
        "mode": "structural_only",
        "forward_outcomes_computed": False,
        "year": args.year,
        "archive": archive,
        "member": member,
        "dataset_sha256": dataset_hash,
        "code_sha": code_sha,
        "bars": len(bars),
        "profiles": len(profiles),
        "candidates": len(nodes),
        "accepted": len(accepted),
        "artifacts": artifacts,
        "reproduction_command": (
            f"PYTHONPATH=src python3 scripts/run_atomic_pilot_v4.py --year {args.year} "
            f"--data-root <data-root> --structural-only"
        ),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n"
    )
    print(json.dumps(
        {k: v for k, v in manifest.items() if k != "artifacts"},
        sort_keys=True, default=str,
    ))


if __name__ == "__main__":
    main()
