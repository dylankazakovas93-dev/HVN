from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction
from statistics import median

TICK = Decimal("0.25")
ALLOCATION_QUANTUM = Decimal("1e-50")


def rounded_size(atr: Decimal, ratio: Decimal) -> tuple[Decimal, Decimal]:
    raw = atr * ratio
    ticks = (raw / TICK).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return raw, max(TICK, ticks * TICK)


def intersected(low: Decimal, high: Decimal, size: Decimal) -> tuple[int, ...]:
    first = int((low / size).to_integral_value(rounding=ROUND_FLOOR))
    if low == high:
        return (first,)
    last = int((high / size).to_integral_value(rounding=ROUND_CEILING)) - 1
    return tuple(range(first, last + 1))


def allocate_uniform(bars: list[dict], size: Decimal) -> tuple[dict[int, Decimal], list[dict]]:
    weights: dict[int, Decimal] = {}
    details: list[dict] = []
    with localcontext() as context:
        context.prec = 80
        for bar in bars:
            indices = intersected(bar["low"], bar["high"], size)
            each = (bar["volume"] / Decimal(len(indices))).quantize(ALLOCATION_QUANTUM)
            allocations = [each] * (len(indices) - 1)
            allocations.append(bar["volume"] - each * Decimal(len(indices) - 1))
            details.append(
                {
                    "indices": indices,
                    "allocations": tuple(allocations),
                    "sum": sum(allocations, Decimal(0)),
                }
            )
            for index, value in zip(indices, allocations):
                weights[index] = weights.get(index, Decimal(0)) + value
        for index in range(min(weights), max(weights) + 1):
            weights.setdefault(index, Decimal(0))
        source_total = sum((bar["volume"] for bar in bars), Decimal(0))
        allocated_total = sum((Fraction(value) for value in weights.values()), Fraction(0))
        residual = Fraction(source_total) - allocated_total
        weights[max(weights)] += Decimal(residual.numerator) / Decimal(residual.denominator)
    return dict(sorted(weights.items())), details


def allocate_tpo(bars: list[dict], size: Decimal) -> dict[int, Decimal]:
    weights: dict[int, Decimal] = {}
    for bar in bars:
        for index in intersected(bar["low"], bar["high"], size):
            weights[index] = weights.get(index, Decimal(0)) + 1
    for index in range(min(weights), max(weights) + 1):
        weights.setdefault(index, Decimal(0))
    return dict(sorted(weights.items()))


def select_poc(
    weights: dict[int, Decimal],
    size: Decimal,
    source_low: Decimal,
    source_high: Decimal,
) -> int:
    total = sum(weights.values(), Decimal(0))
    centers = {i: (Decimal(i) + Decimal("0.5")) * size for i in weights}
    mean = sum((centers[i] * w for i, w in weights.items()), Decimal(0)) / total
    midpoint = (source_low + source_high) / 2
    maximum = max(weights.values())
    tied = [i for i, value in weights.items() if value == maximum]
    return min(
        tied,
        key=lambda i: (
            abs(centers[i] - mean),
            abs(centers[i] - midpoint),
            centers[i],
        ),
    )


def peak_and_nodes(
    weights: list[Decimal],
    *,
    size: Decimal,
    atr: Decimal,
    prominence_threshold: Decimal,
    source_low: Decimal,
    source_high: Decimal,
) -> tuple[list[dict], list[dict]]:
    total = sum(weights, Decimal(0))
    centers = [(Decimal(i) + Decimal("0.5")) * size for i in range(len(weights))]
    mean = sum((centers[i] * weight for i, weight in enumerate(weights)), Decimal(0)) / total
    midpoint = (source_low + source_high) / 2
    candidates: list[dict] = []
    cursor = 0
    while cursor < len(weights):
        end = cursor
        while end + 1 < len(weights) and weights[end + 1] == weights[cursor]:
            end += 1
        left = weights[cursor - 1] if cursor else Decimal("-Infinity")
        right = weights[end + 1] if end + 1 < len(weights) else Decimal("-Infinity")
        if weights[cursor] > left and weights[end] > right:
            plateau = list(range(cursor, end + 1))
            representative = min(
                plateau,
                key=lambda i: (
                    abs(centers[i] - mean),
                    abs(centers[i] - midpoint),
                    centers[i],
                ),
            )
            baseline_indices = [
                i
                for i, center in enumerate(centers)
                if i not in plateau
                and abs(center - centers[representative]) <= atr * Decimal("0.50")
            ]
            baseline = (
                median([weights[i] for i in baseline_indices])
                if len(baseline_indices) >= 2
                else None
            )
            prominence = None
            if baseline == 0:
                prominence = Decimal("Infinity")
            elif baseline is not None:
                prominence = weights[representative] / baseline
            candidates.append(
                {
                    "start": cursor,
                    "end": end,
                    "representative": representative,
                    "peak_weight": weights[representative],
                    "baseline_indices": baseline_indices,
                    "baseline": baseline,
                    "prominence": prominence,
                    "qualifies": prominence is not None
                    and prominence >= prominence_threshold,
                }
            )
        cursor = end + 1

    raw_nodes: list[dict] = []
    for candidate in candidates:
        if not candidate["qualifies"]:
            continue
        threshold = candidate["peak_weight"] / 2
        left, right = candidate["start"], candidate["end"]
        while left > 0 and weights[left - 1] >= threshold:
            left -= 1
        while right + 1 < len(weights) and weights[right + 1] >= threshold:
            right += 1
        raw_nodes.append({"left": left, "right": right, "candidates": [candidate]})
    merged: list[dict] = []
    for node in raw_nodes:
        if merged and node["left"] <= merged[-1]["right"] + 1:
            merged[-1]["right"] = max(merged[-1]["right"], node["right"])
            merged[-1]["candidates"].extend(node["candidates"])
        else:
            merged.append(node)
    nodes = [
        {
            "left": node["left"],
            "right": node["right"],
            "low": Decimal(node["left"]) * size,
            "high": Decimal(node["right"] + 1) * size,
            "weight": sum(weights[node["left"] : node["right"] + 1], Decimal(0)),
            "share": sum(weights[node["left"] : node["right"] + 1], Decimal(0)) / total,
            "constituent_count": len(node["candidates"]),
        }
        for node in merged
    ]
    return candidates, nodes
