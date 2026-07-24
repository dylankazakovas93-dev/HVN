from datetime import date
from decimal import Decimal

from hvn.stage02_statistics import (
    PairObservation,
    gate_sample_support,
    paired_summary,
    session_pair_block_bootstrap,
    stable_grid,
    standardized_mean_difference,
)


def observation(index: int, difference: str, design: str = "PRIMARY_CROSS_SESSION"):
    return PairObservation(
        f"P{index}",
        design,
        "R02",
        "C01",
        "uniform_bar_volume",
        Decimal("0.10"),
        Decimal("2.0"),
        2025,
        date(2025, 1, 1 + index % 2),
        date(2025, 2, 1 + index % 3),
        f"E{index}",
        "inside_close_share_30",
        Decimal(difference),
        Decimal(0),
    )


def test_session_pair_bootstrap_is_deterministic():
    observations = [observation(i, str(i / 10)) for i in range(6)]
    assert session_pair_block_bootstrap(observations, resamples=100) == (
        session_pair_block_bootstrap(observations, resamples=100)
    )


def test_paired_summary_and_year_level_fields():
    result = paired_summary(
        [observation(0, "0.1"), observation(1, "0.3")], resamples=100
    )
    assert result.count == 2
    assert result.mean == Decimal("0.2")
    assert result.expected_sign_share == 1


def test_smd_zero_and_material_imbalance():
    assert standardized_mean_difference([Decimal(1), Decimal(1)], [Decimal(1), Decimal(1)]) == 0
    assert standardized_mean_difference([Decimal(2), Decimal(2)], [Decimal(1), Decimal(1)]).is_infinite()


def test_grid_stability_requires_six_of_nine_and_positive_median():
    cells = {
        (ratio, prominence): Decimal(1 if index < 6 else -1)
        for index, (ratio, prominence) in enumerate(
            (ratio, prominence)
            for ratio in (Decimal("0.05"), Decimal("0.10"), Decimal("0.20"))
            for prominence in (Decimal("1.5"), Decimal("2.0"), Decimal("2.5"))
        )
    }
    assert stable_grid(cells)


def test_same_session_results_cannot_enter_gates():
    secondary = [observation(i, "1", "SECONDARY_SAME_SESSION") for i in range(120)]
    assert gate_sample_support(secondary) == "UNDERPOWERED"
