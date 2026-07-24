from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import timedelta
from decimal import Decimal

import pytest

from hvn.engine import (
    construct_profile,
    intersected_bin_indices,
    rounded_bin_size,
    select_poc,
)
from hvn.ledger import profile_ledger_bytes
from hvn.models import AllocationMethod

from conftest import fixed_atr, make_bar, simple_window


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        ("100.00", "100.00", (400,)),
        ("100.00", "100.25", (400,)),
        ("99.999999999", "100.25", (399, 400)),
        ("100.25", "100.50", (401,)),
        ("100.00", "101.00", (400, 401, 402, 403)),
        ("100.01", "100.49", (400, 401)),
    ],
)
def test_exact_bin_membership(low, high, expected):
    assert intersected_bin_indices(Decimal(low), Decimal(high), Decimal("0.25")) == expected


@pytest.mark.parametrize(
    ("atr", "ratio", "raw", "rounded"),
    [
        ("2.5", "0.05", "0.125", "0.25"),
        ("7.5", "0.05", "0.375", "0.50"),
        ("10", "0.10", "1.0", "1.00"),
        ("1", "0.05", "0.05", "0.25"),
    ],
)
def test_round_half_up_and_tick_floor(atr, ratio, raw, rounded):
    assert rounded_bin_size(Decimal(atr), Decimal(ratio)) == (
        Decimal(raw),
        Decimal(rounded),
    )


def test_uniform_volume_conservation_and_zero_volume(base_time):
    bars = [
        make_bar(1, base_time, "100", "101", "12"),
        make_bar(2, base_time + timedelta(minutes=1), "100.25", "100.25", "0"),
    ]
    profile = construct_profile(
        bars,
        fixed_atr(base_time, "2.5"),
        simple_window(base_time),
        AllocationMethod.UNIFORM_VOLUME,
        Decimal("0.05"),
    )
    assert profile.source_total_volume == Decimal("12")
    assert profile.allocated_total_volume == Decimal("12")
    assert sum((b.profile_weight for b in profile.bins), Decimal(0)) == Decimal("12")


def test_tpo_counts_are_not_volume_weighted(base_time):
    bars = [
        make_bar(1, base_time, "100", "100.25", "999"),
        make_bar(2, base_time + timedelta(minutes=1), "100", "100.50", "1"),
    ]
    profile = construct_profile(
        bars,
        fixed_atr(base_time, "2.5"),
        simple_window(base_time),
        AllocationMethod.TPO,
        Decimal("0.05"),
    )
    assert [b.profile_weight for b in profile.bins] == [Decimal(2), Decimal(1)]
    assert profile.allocated_total_volume == 0


def test_source_start_included_source_end_excluded_and_post_freeze_ignored(base_time):
    window = simple_window(base_time, 2)
    bars = [
        make_bar(1, base_time - timedelta(minutes=1), "99", "99", "100"),
        make_bar(2, base_time, "100", "100", "10"),
        make_bar(3, window.source_end - timedelta(minutes=1), "101", "101", "20"),
        make_bar(4, window.source_end, "200", "200", "1000"),
        make_bar(5, window.source_end + timedelta(minutes=1), "300", "300", "1000"),
    ]
    profile = construct_profile(
        bars,
        fixed_atr(base_time),
        window,
        AllocationMethod.UNIFORM_VOLUME,
        Decimal("0.10"),
    )
    assert profile.source_row_ids == ("row-2", "row-3")
    assert profile.source_total_volume == 30
    assert max(b.bin_high for b in profile.bins) < 200


def test_frozen_profile_is_immutable(base_time):
    profile = construct_profile(
        [make_bar(1, base_time, "100", "100")],
        fixed_atr(base_time),
        simple_window(base_time),
        AllocationMethod.UNIFORM_VOLUME,
        Decimal("0.10"),
    )
    with pytest.raises(FrozenInstanceError):
        profile.poc_bin_index = 7
    assert isinstance(profile.bins, tuple)


def test_missing_atr_warmup_rejected(base_time):
    with pytest.raises(ValueError, match="warm-up"):
        construct_profile(
            [make_bar(1, base_time, "100", "100")],
            (),
            simple_window(base_time),
            AllocationMethod.UNIFORM_VOLUME,
            Decimal("0.10"),
        )


def test_duplicate_rows_and_timestamps_rejected(base_time):
    bar = make_bar(1, base_time, "100", "100")
    with pytest.raises(ValueError, match="duplicate source_row_id"):
        construct_profile(
            [bar, bar],
            fixed_atr(base_time),
            simple_window(base_time),
            AllocationMethod.UNIFORM_VOLUME,
            Decimal("0.10"),
        )
    with pytest.raises(ValueError, match="duplicate symbol timestamp"):
        construct_profile(
            [bar, make_bar(2, base_time, "101", "101")],
            fixed_atr(base_time),
            simple_window(base_time),
            AllocationMethod.UNIFORM_VOLUME,
            Decimal("0.10"),
        )


def test_poc_unique_maximum(base_time):
    bars = [
        make_bar(1, base_time, "100", "100", "20"),
        make_bar(2, base_time + timedelta(minutes=1), "101", "101", "5"),
    ]
    profile = construct_profile(
        bars,
        fixed_atr(base_time),
        simple_window(base_time),
        AllocationMethod.UNIFORM_VOLUME,
        Decimal("0.10"),
    )
    assert next(b for b in profile.bins if b.is_poc).bin_low == 100


def test_poc_final_lower_price_tie_break(base_time):
    bars = [
        make_bar(1, base_time, "100", "100", "10"),
        make_bar(2, base_time + timedelta(minutes=1), "102", "102", "10"),
    ]
    profile = construct_profile(
        bars,
        fixed_atr(base_time),
        simple_window(base_time),
        AllocationMethod.UNIFORM_VOLUME,
        Decimal("0.10"),
    )
    assert next(b for b in profile.bins if b.is_poc).bin_low == 100


def test_poc_weighted_mean_tie_stage():
    assert select_poc(
        {0: Decimal(10), 1: Decimal(10)},
        {0: Decimal(0), 1: Decimal(10)},
        Decimal(2),
        Decimal(5),
    ) == 0


def test_poc_range_midpoint_tie_stage():
    assert select_poc(
        {0: Decimal(10), 1: Decimal(10)},
        {0: Decimal(0), 1: Decimal(10)},
        Decimal(5),
        Decimal(9),
    ) == 1


def test_poc_lower_price_final_stage():
    assert select_poc(
        {0: Decimal(10), 1: Decimal(10)},
        {0: Decimal(0), 1: Decimal(10)},
        Decimal(5),
        Decimal(5),
    ) == 0


def test_deterministic_byte_identical_ledger(base_time):
    args = (
        [make_bar(1, base_time, "100", "101", "17")],
        fixed_atr(base_time),
        simple_window(base_time),
        AllocationMethod.UNIFORM_VOLUME,
        Decimal("0.10"),
    )
    assert profile_ledger_bytes(construct_profile(*args)) == profile_ledger_bytes(
        construct_profile(*args)
    )
