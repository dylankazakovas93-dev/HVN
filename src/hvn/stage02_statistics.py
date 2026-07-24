from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from .control_zones import percentile_type7

BOOTSTRAP_SEED = 20260724
BOOTSTRAP_RESAMPLES = 10_000


@dataclass(frozen=True, slots=True)
class PairObservation:
    pair_id: str
    match_design: str
    relationship_id: str
    control_family: str
    allocation_method: str
    bin_ratio: Decimal
    prominence_threshold: Decimal
    year: int
    treated_session_date: date
    control_session_date: date
    economic_episode_id: str
    metric_name: str
    treated_value: Decimal
    control_value: Decimal

    @property
    def difference(self) -> Decimal:
        return self.treated_value - self.control_value


@dataclass(frozen=True, slots=True)
class PairedSummary:
    count: int
    mean: Decimal | None
    median: Decimal | None
    standard_deviation: Decimal | None
    iqr: Decimal | None
    expected_sign_share: Decimal | None
    ci_low: Decimal | None
    ci_high: Decimal | None


def primary_only(observations: list[PairObservation] | tuple[PairObservation, ...]):
    return tuple(
        observation
        for observation in observations
        if observation.match_design == "PRIMARY_CROSS_SESSION"
    )


def session_pair_block_bootstrap(
    observations: list[PairObservation] | tuple[PairObservation, ...],
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[Decimal, Decimal]:
    if not observations:
        raise ValueError("bootstrap requires observations")
    blocks: dict[tuple[date, date], list[Decimal]] = defaultdict(list)
    for observation in observations:
        blocks[
            (observation.treated_session_date, observation.control_session_date)
        ].append(observation.difference)
    keys = sorted(blocks)
    rng = random.Random(seed)
    means = []
    with localcontext() as context:
        context.prec = 40
        for _ in range(resamples):
            sampled = [rng.choice(keys) for _ in keys]
            values = [
                value
                for key in sampled
                for value in blocks[key]
            ]
            means.append(sum(values, Decimal(0)) / Decimal(len(values)))
    return (
        percentile_type7(means, Decimal("0.025")),
        percentile_type7(means, Decimal("0.975")),
    )


def paired_summary(
    observations: list[PairObservation] | tuple[PairObservation, ...],
    *,
    expected_positive: bool = True,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> PairedSummary:
    observations = tuple(observations)
    if not observations:
        return PairedSummary(0, None, None, None, None, None, None, None)
    values = [observation.difference for observation in observations]
    mean = sum(values, Decimal(0)) / Decimal(len(values))
    median = percentile_type7(values, Decimal("0.5"))
    q25 = percentile_type7(values, Decimal("0.25"))
    q75 = percentile_type7(values, Decimal("0.75"))
    standard_deviation = None
    if len(values) > 1:
        variance = sum(((value - mean) ** 2 for value in values), Decimal(0)) / Decimal(
            len(values) - 1
        )
        standard_deviation = variance.sqrt()
    expected = sum(
        1
        for value in values
        if (value > 0 if expected_positive else value < 0)
    )
    low, high = session_pair_block_bootstrap(
        observations, resamples=resamples, seed=BOOTSTRAP_SEED
    )
    return PairedSummary(
        len(values),
        mean,
        median,
        standard_deviation,
        q75 - q25,
        Decimal(expected) / Decimal(len(values)),
        low,
        high,
    )


def standardized_mean_difference(
    treated: list[Decimal] | tuple[Decimal, ...],
    control: list[Decimal] | tuple[Decimal, ...],
) -> Decimal:
    if not treated or not control:
        raise ValueError("SMD requires two samples")
    mean_t = sum(treated, Decimal(0)) / Decimal(len(treated))
    mean_c = sum(control, Decimal(0)) / Decimal(len(control))

    def variance(values, mean):
        if len(values) < 2:
            return Decimal(0)
        return sum(((value - mean) ** 2 for value in values), Decimal(0)) / Decimal(
            len(values) - 1
        )

    pooled = ((variance(treated, mean_t) + variance(control, mean_c)) / 2).sqrt()
    if pooled == 0:
        if mean_t == mean_c:
            return Decimal(0)
        return Decimal("Infinity") if mean_t > mean_c else Decimal("-Infinity")
    return (mean_t - mean_c) / pooled


def stable_grid(cell_effects: dict[tuple[Decimal, Decimal], Decimal | None]) -> bool:
    expected = {
        (ratio, prominence)
        for ratio in (Decimal("0.05"), Decimal("0.10"), Decimal("0.20"))
        for prominence in (Decimal("1.5"), Decimal("2.0"), Decimal("2.5"))
    }
    if set(cell_effects) != expected or any(value is None for value in cell_effects.values()):
        return False
    values = [value for value in cell_effects.values() if value is not None]
    return sum(value > 0 for value in values) >= 6 and percentile_type7(
        values, Decimal("0.5")
    ) > 0


def gate_sample_support(observations: list[PairObservation] | tuple[PairObservation, ...]) -> str:
    primary = primary_only(observations)
    if len(primary) < 100:
        return "UNDERPOWERED"
    per_year: dict[int, int] = defaultdict(int)
    for observation in primary:
        per_year[observation.year] += 1
    return "PASS" if sum(count >= 20 for count in per_year.values()) >= 3 else "UNDERPOWERED"

