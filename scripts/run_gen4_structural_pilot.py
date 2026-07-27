"""Generation 4 structural pilot — smoothed multi-tick HVN zones.

Structural mode constructs tick-grid profiles, densities, smoothed activity,
peak candidates, basins, zones, the POC zone, both value areas and the
relationship opportunity population. It never computes, loads or writes any
forward proximity, residence, departure or excursion result.

See `research/hvn/STAGE_02_GENERATION_4_ZONE_SPEC.md`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from decimal import Decimal
from pathlib import Path

from hvn.atomic_v2 import value_area
from hvn.atr import wilder_atr
from hvn.interactions import Relationship
from hvn.io import databento_rows_with_audit
from hvn.models import ProfileBin, ProfileFamily
from hvn.sessions import profile_window
from hvn.stage02_ledger import deterministic_csv_bytes, write_deterministic_gzip_csv
from hvn.stage02_pipeline import (
    EXPECTED_SOURCE_MINUTES,
    FAMILY_BY_RELATIONSHIP,
    AtrSelector,
    ContractSelector,
    _consecutive,
    trading_dates,
)
from hvn.zones_v4 import (
    BROAD_ACTIVITY_DISTRIBUTION,
    NONPOC_HVN_ZONE,
    POC_BROAD_DISTRIBUTION,
    POC_HVN_ZONE,
    TICK_SIZE,
    classify_zones,
    construct_tick_profile,
    peak_plateaus,
    profile_activity,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "outputs" / "stage_02_generation_4_hvn_zones_pilot"
PRESERVED = (
    ROOT / "outputs" / "stage_02",
    ROOT / "outputs" / "stage_02_generation_2",
    ROOT / "outputs" / "stage_02_generation_3_atomic",
    ROOT / "outputs" / "stage_02_generation_3_atomic_pilot_v2",
    ROOT / "outputs" / "stage_02_generation_3_atomic_pilot_v3",
    ROOT / "outputs" / "stage_02_generation_3_atomic_pilot_v4",
    ROOT / "outputs" / "stage_02_generation_3_final",
)
SOURCES = {
    2019: ("nq2018.zip", "glbx-mdp3-20180101-20191230.ohlcv-1m.csv.zst"),
    2021: ("nq2021.zip", "glbx-mdp3-20210101-20221230.ohlcv-1m.csv.zst"),
    2023: ("nq2023.zip", "glbx-mdp3-20230101-20241230.ohlcv-1m.csv.zst"),
    2025: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
    2026: ("nq2025.zip", "glbx-mdp3-20250101-20260607.ohlcv-1m.csv.zst"),
}
FORBIDDEN_YEARS = (2018, 2020, 2022, 2024)

RELATIONSHIPS_BY_FAMILY: dict[ProfileFamily, tuple[Relationship, ...]] = {}
for _relationship, _family in FAMILY_BY_RELATIONSHIP.items():
    RELATIONSHIPS_BY_FAMILY.setdefault(_family, ())
    RELATIONSHIPS_BY_FAMILY[_family] += (_relationship,)


def archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="run_gen4_structural_pilot.py",
        description=(
            "Generation 4 structural-only run. Builds tick-grid profiles, "
            "smoothed activity and HVN zones. Computes no forward outcome."
        ),
    )
    parser.add_argument("--year", type=int, choices=sorted(SOURCES), required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--structural-only",
        action="store_true",
        default=True,
        help="the only supported mode; forward outcomes are never computed",
    )
    args = parser.parse_args(argv)
    if not args.structural_only:
        parser.error("this script supports --structural-only mode only")
    output = args.output_root.resolve()
    for preserved in PRESERVED:
        if output == preserved or preserved in output.parents:
            parser.error(f"refusing to write into a preserved generation: {output}")
    args.output_root = output
    return args


def _tick_bins(profile) -> dict[int, ProfileBin]:
    """ProfileBin views of the tick grid, for the locked value-area routine."""
    return {
        i: ProfileBin(
            i,
            profile.tick_low(i),
            profile.tick_high(i),
            profile.tick_center(i),
            profile.volume.get(i, Decimal(0)),
            Decimal(0),
            Decimal(0),
            i == profile.poc_index,
        )
        for i in profile.indices
    }


def _percentile(values: list, fraction: Decimal):
    """Nearest-rank percentile over a sorted sample; deterministic."""
    if not values:
        return None
    ordered = sorted(values)
    position = (fraction * Decimal(len(ordered))).to_integral_value(rounding="ROUND_CEILING")
    index = max(1, min(len(ordered), int(position))) - 1
    return ordered[index]


def _median(values: list):
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def build(bars, *, year, code_sha):
    """Structural sweep over every frozen source profile in the partition."""
    dates = trading_dates(bars)
    by_symbol = {
        s: tuple(b for b in bars if b.symbol == s)
        for s in sorted({b.symbol for b in bars})
    }
    atrs = {s: AtrSelector(wilder_atr(v)) for s, v in by_symbol.items()}
    selector = ContractSelector(by_symbol)

    profile_rows: list[dict] = []
    raw_rows: list[dict] = []
    smoothed_rows: list[dict] = []
    candidate_rows: list[dict] = []
    zone_rows: list[dict] = []
    poc_rows: list[dict] = []
    va_rows: list[dict] = []
    tpo_va_rows: list[dict] = []
    opportunity_rows: list[dict] = []

    for position, current in enumerate(dates):
        if position == 0:
            continue
        prior = dates[position - 1]
        for family in ProfileFamily:
            source_date = prior if family == ProfileFamily.PRIOR_RTH else current
            pwindow = profile_window(family, source_date)
            try:
                symbol = selector.choose(pwindow.source_start)
            except ValueError:
                continue
            selected = by_symbol[symbol]
            source = sorted(
                [
                    b
                    for b in selected
                    if pwindow.source_start <= b.start_time < pwindow.source_end
                ],
                key=lambda b: b.close_time,
            )
            if not _consecutive(source, EXPECTED_SOURCE_MINUTES[family]):
                continue
            atr_point = atrs[symbol].before(pwindow.source_start)
            try:
                profile = construct_tick_profile(
                    source,
                    (atr_point,),
                    pwindow,
                    code_sha=code_sha,
                    data_partition=f"development_{year}",
                )
            except ValueError:
                continue

            zones, activity = classify_zones(profile)
            base = {
                "profile_id": profile.profile_id,
                "family": family.value,
                "session_date": current.isoformat(),
                "source_date": source_date.isoformat(),
                "contract": symbol,
                "year": year,
                "freeze_time": pwindow.freeze_time.isoformat(),
            }
            active_ticks = len(activity.active)
            profile_rows.append(
                base
                | {
                    "atr_value": profile.atr_value,
                    "atr_reference_time": profile.atr_reference_time,
                    "tick_count": len(list(profile.indices)),
                    "active_tick_count": active_ticks,
                    "source_bar_count": len(source),
                    "source_total_volume": profile.source_total_volume,
                    "allocated_total_volume": sum(
                        profile.volume.values(), Decimal(0)
                    ),
                    "tpo_total": sum(profile.tpo.values()),
                    "profile_range_low": profile.profile_range_low,
                    "profile_range_high": profile.profile_range_high,
                    "poc_index": profile.poc_index,
                    "poc_price": profile.tick_center(profile.poc_index),
                    "valid": activity.valid,
                    "invalid_reason": activity.invalid_reason,
                    "smoothing_half_width_ticks": activity.half_width_ticks,
                    "smoothing_span_points": Decimal(2 * activity.half_width_ticks + 1)
                    * TICK_SIZE,
                    "smoothing_span_atr": (
                        Decimal(2 * activity.half_width_ticks + 1)
                        * TICK_SIZE
                        / profile.atr_value
                    ),
                    "code_sha": code_sha,
                }
            )
            if not activity.valid:
                continue

            raw_rows.append(
                base
                | {
                    "positive_volume_ticks": sum(
                        1 for v in profile.volume.values() if v > 0
                    ),
                    "positive_tpo_ticks": sum(1 for t in profile.tpo.values() if t > 0),
                    "mean_active_volume": activity.v_total
                    / Decimal(sum(1 for v in profile.volume.values() if v > 0)),
                    "mean_active_tpo": Decimal(activity.t_total)
                    / Decimal(sum(1 for t in profile.tpo.values() if t > 0)),
                    "max_raw_activity": max(activity.raw_activity.values()),
                    "median_raw_activity": _median(
                        [v for v in activity.raw_activity.values() if v > 0]
                    ),
                }
            )
            smoothed_rows.append(
                base
                | {
                    "smoothing_half_width_ticks": activity.half_width_ticks,
                    "max_smoothed_activity": max(activity.smoothed_activity.values()),
                    "median_smoothed_activity": _median(
                        [v for v in activity.smoothed_activity.values() if v > 0]
                    ),
                    "p95_smoothed_activity": _percentile(
                        [v for v in activity.smoothed_activity.values() if v > 0],
                        Decimal("0.95"),
                    ),
                    "peak_plateau_count": len(
                        peak_plateaus(activity, profile.indices)
                    ),
                }
            )

            bins_by_index = _tick_bins(profile)
            volume_weights = {i: profile.volume.get(i, Decimal(0)) for i in profile.indices}
            tpo_weights = {
                i: Decimal(profile.tpo.get(i, 0)) for i in profile.indices
            }
            v_area = value_area(volume_weights, bins_by_index, activity.v_total)
            t_area = value_area(
                tpo_weights, bins_by_index, Decimal(activity.t_total)
            )
            if v_area:
                va_rows.append(
                    base
                    | {
                        "volume_VAL": v_area.low_price,
                        "volume_VAH": v_area.high_price,
                        "volume_POC": v_area.poc_price,
                        "volume_value_area_share": v_area.covered_share,
                        "volume_value_area_tick_count": v_area.bin_count,
                        "poc_inside": v_area.low_bin_index
                        <= v_area.poc_low_bin_index
                        <= v_area.high_bin_index,
                        "contiguous": v_area.high_bin_index >= v_area.low_bin_index,
                    }
                )
            if t_area:
                tpo_va_rows.append(
                    base
                    | {
                        "tpo_VAL": t_area.low_price,
                        "tpo_VAH": t_area.high_price,
                        "tpo_POC": t_area.poc_price,
                        "tpo_value_area_share": t_area.covered_share,
                        "tpo_value_area_tick_count": t_area.bin_count,
                        "poc_inside": t_area.low_bin_index
                        <= t_area.poc_low_bin_index
                        <= t_area.high_bin_index,
                        "contiguous": t_area.high_bin_index >= t_area.low_bin_index,
                    }
                )

            for zone in zones:
                row = base | {
                    "zone_id": zone.zone_id,
                    "physical_zone_id": zone.physical_zone_id,
                    "zone_class": zone.zone_class,
                    "low_index": zone.low_index,
                    "high_index": zone.high_index,
                    "width_ticks": zone.width_ticks,
                    "width_points": zone.width_points,
                    "width_atr": zone.width_atr,
                    "zone_low": zone.zone_low,
                    "zone_high": zone.zone_high,
                    "peak_price": zone.peak_price,
                    "peak_smoothed_activity": zone.peak_smoothed_activity,
                    "peak_activity_percentile": zone.peak_activity_percentile,
                    "zone_volume": zone.zone_volume,
                    "zone_tpo": zone.zone_tpo,
                    "zone_volume_density": zone.zone_volume_density,
                    "zone_tpo_density": zone.zone_tpo_density,
                    "zone_activity_density": zone.zone_activity_density,
                    "basin_low_index": zone.basin_low_index,
                    "basin_high_index": zone.basin_high_index,
                    "basin_width_ticks": zone.basin_high_index - zone.basin_low_index + 1,
                    "left_valley_activity": zone.left_valley_activity,
                    "right_valley_activity": zone.right_valley_activity,
                    "reference_valley_activity": zone.reference_valley_activity,
                    "peak_to_valley_ratio": zone.peak_to_valley_ratio,
                    "minimum_width_ticks": zone.minimum_width_ticks,
                    "maximum_width_ticks": zone.maximum_width_ticks,
                    "smoothing_half_width_ticks": zone.smoothing_half_width_ticks,
                    "atr_value": zone.atr_value,
                    "accepted": zone.accepted,
                    "rejection_reason": zone.rejection_reason,
                    "code_sha": code_sha,
                }
                if v_area:
                    row |= {
                        "inside_volume_value_area": v_area.low_bin_index
                        <= zone.low_index
                        and zone.high_index <= v_area.high_bin_index,
                        "overlaps_volume_VAL": zone.low_index
                        <= v_area.low_bin_index
                        <= zone.high_index,
                        "overlaps_volume_VAH": zone.low_index
                        <= v_area.high_bin_index
                        <= zone.high_index,
                        "overlaps_volume_POC": zone.low_index
                        <= profile.poc_index
                        <= zone.high_index,
                        "distance_to_volume_VAL_atr": abs(
                            zone.peak_price - v_area.low_price
                        )
                        / zone.atr_value,
                        "distance_to_volume_VAH_atr": abs(
                            zone.peak_price - v_area.high_price
                        )
                        / zone.atr_value,
                        "distance_to_volume_POC_atr": abs(
                            zone.peak_price - v_area.poc_price
                        )
                        / zone.atr_value,
                        "value_area_location": (
                            "VALUE_EDGE"
                            if (
                                zone.low_index <= v_area.low_bin_index <= zone.high_index
                                or zone.low_index
                                <= v_area.high_bin_index
                                <= zone.high_index
                            )
                            else "INSIDE_VALUE"
                            if v_area.low_bin_index <= zone.low_index
                            and zone.high_index <= v_area.high_bin_index
                            else "OUTSIDE_VALUE"
                        ),
                    }
                if t_area:
                    row |= {
                        "inside_tpo_value_area": t_area.low_bin_index <= zone.low_index
                        and zone.high_index <= t_area.high_bin_index,
                        "overlaps_tpo_VAL": zone.low_index
                        <= t_area.low_bin_index
                        <= zone.high_index,
                        "overlaps_tpo_VAH": zone.low_index
                        <= t_area.high_bin_index
                        <= zone.high_index,
                        "overlaps_tpo_POC": zone.low_index
                        <= t_area.poc_low_bin_index
                        <= zone.high_index,
                        "distance_to_tpo_VAL_atr": abs(
                            zone.peak_price - t_area.low_price
                        )
                        / zone.atr_value,
                        "distance_to_tpo_VAH_atr": abs(
                            zone.peak_price - t_area.high_price
                        )
                        / zone.atr_value,
                        "distance_to_tpo_POC_atr": abs(
                            zone.peak_price - t_area.poc_price
                        )
                        / zone.atr_value,
                    }
                candidate_rows.append(row)
                if zone.zone_class in (POC_HVN_ZONE, POC_BROAD_DISTRIBUTION):
                    poc_rows.append(row)
                zone_rows.append(row)

                # One relationship opportunity per accepted zone per
                # relationship that consumes this profile family.
                if zone.accepted:
                    for relationship in RELATIONSHIPS_BY_FAMILY.get(family, ()):
                        opportunity_rows.append(
                            {
                                "opportunity_id": (
                                    f"{zone.zone_id}-{relationship.value}"
                                ),
                                "zone_id": zone.zone_id,
                                "physical_zone_id": zone.physical_zone_id,
                                "relationship_id": relationship.value,
                                "family": family.value,
                                "zone_class": zone.zone_class,
                                "session_date": current.isoformat(),
                                "contract": symbol,
                                "year": year,
                                "width_ticks": zone.width_ticks,
                                "width_atr": zone.width_atr,
                            }
                        )

    return {
        "profiles": profile_rows,
        "raw": raw_rows,
        "smoothed": smoothed_rows,
        "candidates": candidate_rows,
        "zones": zone_rows,
        "poc": poc_rows,
        "volume_value_areas": va_rows,
        "tpo_value_areas": tpo_va_rows,
        "opportunities": opportunity_rows,
    }


def summarize(rows, keys, output, name):
    counts = Counter(tuple(str(r.get(k)) for k in keys) for r in rows)
    out = [dict(zip(keys, k)) | {"count": v} for k, v in sorted(counts.items())]
    fields = tuple(keys) + ("count",)
    (output / name).write_bytes(deterministic_csv_bytes(out, fields, sort_by=fields))
    return out


def _distribution(rows, key, label):
    values = [Decimal(str(r[key])) for r in rows if r.get(key) is not None]
    return {
        "metric": label,
        "count": len(values),
        "mean": (sum(values, Decimal(0)) / Decimal(len(values))) if values else None,
        "median": _median(values),
        "p75": _percentile(values, Decimal("0.75")),
        "p90": _percentile(values, Decimal("0.90")),
        "p95": _percentile(values, Decimal("0.95")),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def main(argv=None) -> None:
    args = parse_args(argv)
    output = args.output_root
    output.mkdir(parents=True, exist_ok=True)

    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    archive, member = SOURCES[args.year]
    source = (args.data_root / archive).resolve()
    dataset_hash = archive_sha256(source)
    bars, audit = databento_rows_with_audit(
        source, member, allowed_year=args.year, dataset_sha256=dataset_hash
    )
    for bar in bars:
        if bar.close_time.year in FORBIDDEN_YEARS or bar.start_time.year in FORBIDDEN_YEARS:
            raise AssertionError(f"forbidden partition row parsed: {bar.source_row_id}")

    built = build(bars, year=args.year, code_sha=code_sha)
    zones = built["zones"]
    accepted = [z for z in zones if z["accepted"]]
    accepted_nonpoc = [z for z in accepted if z["zone_class"] == NONPOC_HVN_ZONE]
    accepted_poc = [z for z in accepted if z["zone_class"] == POC_HVN_ZONE]
    rejected = [z for z in zones if not z["accepted"]]
    broad = [z for z in zones if z["zone_class"] == BROAD_ACTIVITY_DISTRIBUTION]
    poc_broad = [z for z in zones if z["zone_class"] == POC_BROAD_DISTRIBUTION]

    for name, rows, sort_by in (
        ("peak_candidates", built["candidates"], ("zone_id",)),
        ("accepted_hvn_zones", accepted, ("zone_id",)),
        ("rejected_candidates", rejected, ("zone_id",)),
        ("broad_distributions", broad + poc_broad, ("zone_id",)),
    ):
        fields = tuple(sorted({k for r in rows for k in r})) if rows else ("record_id",)
        write_deterministic_gzip_csv(
            output / f"{name}.csv.gz",
            rows,
            fields,
            sort_by=tuple(f for f in sort_by if f in fields),
        )

    for name, rows, sort_key in (
        ("profile_summary.csv", built["profiles"], "profile_id"),
        ("raw_tick_profile_summary.csv", built["raw"], "profile_id"),
        ("smoothed_profile_summary.csv", built["smoothed"], "profile_id"),
        ("poc_zone_summary.csv", built["poc"], "zone_id"),
        ("volume_value_area_summary.csv", built["volume_value_areas"], "profile_id"),
        ("tpo_value_area_summary.csv", built["tpo_value_areas"], "profile_id"),
    ):
        fields = tuple(sorted({k for r in rows for k in r})) if rows else ("record_id",)
        (output / name).write_bytes(
            deterministic_csv_bytes(
                rows, fields, sort_by=(sort_key,) if rows and sort_key in fields else ()
            )
        )

    # Width, density and separation distributions.
    width_rows = [
        _distribution(accepted_nonpoc, "width_ticks", "accepted_nonpoc_width_ticks"),
        _distribution(accepted_nonpoc, "width_points", "accepted_nonpoc_width_points"),
        _distribution(accepted_nonpoc, "width_atr", "accepted_nonpoc_width_atr"),
        _distribution(accepted_poc, "width_ticks", "accepted_poc_width_ticks"),
        _distribution(accepted_poc, "width_atr", "accepted_poc_width_atr"),
        _distribution(accepted, "width_ticks", "accepted_all_width_ticks"),
        _distribution(accepted, "width_atr", "accepted_all_width_atr"),
    ]
    (output / "zone_width_summary.csv").write_bytes(
        deterministic_csv_bytes(
            width_rows,
            ("metric", "count", "mean", "median", "p75", "p90", "p95", "minimum", "maximum"),
            sort_by=("metric",),
        )
    )
    density_rows = [
        _distribution(accepted_nonpoc, "zone_volume_density", "nonpoc_volume_density"),
        _distribution(accepted_nonpoc, "zone_tpo_density", "nonpoc_tpo_density"),
        _distribution(accepted_nonpoc, "zone_activity_density", "nonpoc_activity_density"),
        _distribution(
            accepted_nonpoc, "peak_activity_percentile", "nonpoc_peak_percentile"
        ),
        _distribution(
            accepted_nonpoc, "peak_smoothed_activity", "nonpoc_peak_smoothed_activity"
        ),
        _distribution(accepted_poc, "zone_volume_density", "poc_volume_density"),
        _distribution(accepted_poc, "zone_tpo_density", "poc_tpo_density"),
        _distribution(accepted_poc, "zone_activity_density", "poc_activity_density"),
    ]
    (output / "zone_density_summary.csv").write_bytes(
        deterministic_csv_bytes(
            density_rows,
            ("metric", "count", "mean", "median", "p75", "p90", "p95", "minimum", "maximum"),
            sort_by=("metric",),
        )
    )
    separation_rows = [
        _distribution(accepted_nonpoc, "peak_to_valley_ratio", "nonpoc_peak_to_valley"),
        _distribution(accepted_nonpoc, "basin_width_ticks", "nonpoc_basin_width_ticks"),
        _distribution(
            accepted_nonpoc, "reference_valley_activity", "nonpoc_reference_valley"
        ),
    ]
    (output / "zone_separation_summary.csv").write_bytes(
        deterministic_csv_bytes(
            separation_rows,
            ("metric", "count", "mean", "median", "p75", "p90", "p95", "minimum", "maximum"),
            sort_by=("metric",),
        )
    )

    # Zones per physical profile, counted over profiles that could host a zone.
    per_profile: Counter = Counter()
    for zone in accepted_nonpoc:
        per_profile[zone["profile_id"]] += 1
    host_profiles = [
        p["profile_id"] for p in built["profiles"] if p["valid"]
    ]
    counts = [Decimal(per_profile.get(pid, 0)) for pid in host_profiles]
    zones_per_profile = [
        {
            "metric": "accepted_nonpoc_zones_per_valid_profile",
            "profiles": len(host_profiles),
            "mean": (sum(counts, Decimal(0)) / Decimal(len(counts))) if counts else None,
            "median": _median(counts),
            "p75": _percentile(counts, Decimal("0.75")),
            "p90": _percentile(counts, Decimal("0.90")),
            "maximum": max(counts) if counts else None,
        }
    ]
    (output / "zones_per_profile_summary.csv").write_bytes(
        deterministic_csv_bytes(
            zones_per_profile,
            ("metric", "profiles", "mean", "median", "p75", "p90", "maximum"),
            sort_by=("metric",),
        )
    )

    summarize(
        built["opportunities"],
        ("relationship_id", "family", "zone_class"),
        output,
        "relationship_opportunity_summary.csv",
    )
    summarize(zones, ("rejection_reason", "zone_class"), output, "rejection_summary.csv")

    unique_physical = {z["physical_zone_id"] for z in accepted}
    unique_physical_nonpoc = {z["physical_zone_id"] for z in accepted_nonpoc}
    reconciliation = [
        {"check": "bars_admitted", "value": len(bars)},
        {"check": "profiles_constructed", "value": len(built["profiles"])},
        {"check": "profiles_valid", "value": len(host_profiles)},
        {"check": "peak_candidates", "value": len(built["candidates"])},
        {"check": "accepted_zones", "value": len(accepted)},
        {"check": "accepted_poc_zones", "value": len(accepted_poc)},
        {"check": "accepted_nonpoc_zones", "value": len(accepted_nonpoc)},
        {"check": "poc_broad_distributions", "value": len(poc_broad)},
        {"check": "nonpoc_broad_distributions", "value": len(broad)},
        {"check": "rejected_candidates", "value": len(rejected)},
        {"check": "unique_physical_zones", "value": len(unique_physical)},
        {"check": "unique_physical_nonpoc_zones", "value": len(unique_physical_nonpoc)},
        {"check": "relationship_opportunities", "value": len(built["opportunities"])},
        {"check": "volume_value_areas", "value": len(built["volume_value_areas"])},
        {"check": "tpo_value_areas", "value": len(built["tpo_value_areas"])},
        {
            "check": "candidates_equal_accepted_plus_rejected",
            "value": int(len(built["candidates"]) == len(accepted) + len(rejected)),
        },
        {
            "check": "min_accepted_width_ticks",
            "value": min((int(z["width_ticks"]) for z in accepted), default=0),
        },
        {
            "check": "max_accepted_nonpoc_width_ticks",
            "value": max((int(z["width_ticks"]) for z in accepted_nonpoc), default=0),
        },
        {"check": "forward_outcomes_computed", "value": 0},
        {"check": "rows_admitted_from_archive", "value": audit.rows_admitted},
        {"check": "rows_excluded_earlier_year", "value": audit.rows_excluded_earlier_year},
        {"check": "rows_excluded_later_year", "value": audit.rows_excluded_later_year},
        {"check": "rows_skipped_non_outright", "value": audit.rows_skipped_non_outright},
        {
            "check": "forbidden_year_rows_admitted",
            "value": sum(
                1 for b in bars if b.start_time.year in FORBIDDEN_YEARS
            ),
        },
    ]
    (output / "structural_reconciliation.csv").write_bytes(
        deterministic_csv_bytes(reconciliation, ("check", "value"), sort_by=("check",))
    )

    artifacts = {}
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name not in (
            "manifest.json",
            "GENERATION_4_STRUCTURAL_REPORT.md",
        ):
            artifacts[str(path.relative_to(output))] = {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
    manifest = {
        "generation": "STAGE_02_GENERATION_4_HVN_ZONES",
        "specification": "research/hvn/STAGE_02_GENERATION_4_ZONE_SPEC.md",
        "mode": "structural_only",
        "forward_outcomes_computed": False,
        "year": args.year,
        "archive": archive,
        "member": member,
        "dataset_sha256": dataset_hash,
        "code_sha": code_sha,
        "ingestion_audit": {
            "archive": audit.archive,
            "requested_year": audit.requested_year,
            "parsed_years": sorted(audit.parsed_years),
            "rows_admitted": audit.rows_admitted,
            "rows_excluded_earlier_year": audit.rows_excluded_earlier_year,
            "rows_excluded_later_year": audit.rows_excluded_later_year,
            "rows_skipped_non_outright": audit.rows_skipped_non_outright,
        },
        "bars": len(bars),
        "profiles": len(built["profiles"]),
        "candidates": len(built["candidates"]),
        "accepted_zones": len(accepted),
        "accepted_nonpoc_zones": len(accepted_nonpoc),
        "unique_physical_nonpoc_zones": len(unique_physical_nonpoc),
        "relationship_opportunities": len(built["opportunities"]),
        "artifacts": artifacts,
        "reproduction_command": (
            f"PYTHONPATH=src python3 scripts/run_gen4_structural_pilot.py "
            f"--year {args.year} --data-root <data-root> --structural-only"
        ),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n"
    )
    print(
        json.dumps(
            {k: v for k, v in manifest.items() if k != "artifacts"},
            sort_keys=True,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
