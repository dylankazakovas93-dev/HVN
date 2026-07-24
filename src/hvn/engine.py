from __future__ import annotations

import hashlib
from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_UP,
    Decimal,
    localcontext,
)

from .atr import atr_before
from .models import (
    AllocationMethod,
    AtrPoint,
    Bar,
    FrozenProfile,
    ProfileBin,
    ProfileWindow,
)

TICK_SIZE = Decimal("0.25")
GRID_ORIGIN = Decimal("0")


def rounded_bin_size(atr: Decimal, ratio: Decimal) -> tuple[Decimal, Decimal]:
    raw = atr * ratio
    ticks = (raw / TICK_SIZE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return raw, max(TICK_SIZE, ticks * TICK_SIZE)


def intersected_bin_indices(low: Decimal, high: Decimal, size: Decimal) -> tuple[int, ...]:
    if low > high or size <= 0:
        raise ValueError("invalid range or bin size")
    low_index = int(((low - GRID_ORIGIN) / size).to_integral_value(rounding=ROUND_FLOOR))
    if low == high:
        return (low_index,)
    high_index = int(
        (((high - GRID_ORIGIN) / size).to_integral_value(rounding=ROUND_CEILING)) - 1
    )
    return tuple(range(low_index, high_index + 1))


def _profile_id(window: ProfileWindow, method: AllocationMethod, ratio: Decimal) -> str:
    key = "|".join(
        [
            window.family.value,
            window.source_session_date,
            window.source_start.isoformat(),
            window.source_end.isoformat(),
            method.value,
            str(ratio),
        ]
    )
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def select_poc(
    weights: dict[int, Decimal],
    centers: dict[int, Decimal],
    weighted_mean: Decimal,
    range_midpoint: Decimal,
) -> int:
    """Apply the documented POC hierarchy, including the unique-max stage."""
    max_weight = max(weights.values())
    tied = [index for index, weight in weights.items() if weight == max_weight]
    return min(
        tied,
        key=lambda index: (
            abs(centers[index] - weighted_mean),
            abs(centers[index] - range_midpoint),
            centers[index],
        ),
    )


def construct_profile(
    bars: list[Bar] | tuple[Bar, ...],
    atr_points: tuple[AtrPoint, ...],
    window: ProfileWindow,
    method: AllocationMethod,
    bin_ratio: Decimal,
    *,
    code_sha: str = "UNCOMMITTED",
    data_partition: str = "development",
) -> FrozenProfile:
    if bin_ratio not in {Decimal("0.05"), Decimal("0.10"), Decimal("0.20")}:
        raise ValueError("bin_ratio is outside the Stage 1 definitions")
    atr = atr_before(atr_points, window.source_start)
    if atr.available_time > window.source_start:
        raise AssertionError("causal ATR violation")
    raw_size, size = rounded_bin_size(atr.value, bin_ratio)
    source = sorted(
        (
            b
            for b in bars
            if window.source_start <= b.start_time < window.source_end
            and b.close_time <= window.freeze_time
        ),
        key=lambda b: (b.close_time, b.source_row_id),
    )
    if not source:
        raise ValueError("no source bars in profile window")
    row_ids = tuple(b.source_row_id for b in source)
    if len(set(row_ids)) != len(row_ids):
        raise ValueError("duplicate source_row_id in source window")
    timestamp_keys = [(b.close_time, b.symbol) for b in source]
    if len(set(timestamp_keys)) != len(timestamp_keys):
        raise ValueError("duplicate symbol timestamp in source window")
    weights: dict[int, Decimal] = {}
    with localcontext() as ctx:
        ctx.prec = 40
        for bar in source:
            indices = intersected_bin_indices(bar.low, bar.high, size)
            if method == AllocationMethod.UNIFORM_VOLUME:
                contribution = bar.volume / Decimal(len(indices))
                contributions = [contribution] * (len(indices) - 1)
                contributions.append(
                    bar.volume - contribution * Decimal(len(indices) - 1)
                )
            else:
                contributions = [Decimal(1)] * len(indices)
            for index, contribution in zip(indices, contributions):
                weights[index] = weights.get(index, Decimal(0)) + contribution
        total_weight = sum(weights.values(), Decimal(0))
        source_total_volume = sum((b.volume for b in source), Decimal(0))
    if total_weight <= 0:
        raise ValueError("profile has no positive weight")
    allocated = (
        total_weight if method == AllocationMethod.UNIFORM_VOLUME else Decimal(0)
    )
    if method == AllocationMethod.UNIFORM_VOLUME and allocated != source_total_volume:
        tolerance = max(Decimal("1e-25"), source_total_volume * Decimal("1e-30"))
        if abs(allocated - source_total_volume) > tolerance:
            raise AssertionError("uniform allocation failed volume conservation")

    centers = {i: GRID_ORIGIN + (Decimal(i) + Decimal("0.5")) * size for i in weights}
    weighted_mean = sum(
        (centers[i] * weight for i, weight in weights.items()), Decimal(0)
    ) / total_weight
    range_mid = (min(b.low for b in source) + max(b.high for b in source)) / Decimal(2)
    poc = select_poc(weights, centers, weighted_mean, range_mid)
    cumulative = Decimal(0)
    bins: list[ProfileBin] = []
    for index in sorted(weights):
        share = weights[index] / total_weight
        cumulative += share
        low = GRID_ORIGIN + Decimal(index) * size
        bins.append(
            ProfileBin(
                index,
                low,
                low + size,
                centers[index],
                weights[index],
                share,
                cumulative,
                index == poc,
            )
        )
    return FrozenProfile(
        _profile_id(window, method, bin_ratio),
        window,
        method,
        atr.available_time,
        atr.value,
        bin_ratio,
        raw_size,
        size,
        tuple(bins),
        poc,
        row_ids,
        source_total_volume,
        allocated,
        code_sha,
        data_partition,
    )
