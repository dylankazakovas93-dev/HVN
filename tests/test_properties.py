from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from hvn.engine import construct_profile, intersected_bin_indices
from hvn.hvn import extract_hvns
from hvn.io import databento_rows_from_zip
from hvn.ledger import profile_ledger_bytes
from hvn.models import AllocationMethod

from conftest import fixed_atr, make_bar, simple_window

SEED = 20250724


def _profile(bars, base_time, method=AllocationMethod.UNIFORM_VOLUME):
    return construct_profile(
        bars,
        fixed_atr(base_time),
        simple_window(base_time, 20),
        method,
        Decimal("0.10"),
    )


def test_reordering_input_rows_does_not_change_profile(base_time):
    bars = [
        make_bar(i, base_time + timedelta(minutes=i), str(100 + i), str(101 + i), str(i + 2))
        for i in range(5)
    ]
    assert profile_ledger_bytes(_profile(bars, base_time)) == profile_ledger_bytes(
        _profile(list(reversed(bars)), base_time)
    )


def test_outside_and_post_freeze_bars_do_not_change_profile(base_time):
    bars = [make_bar(1, base_time, "100", "101", "10")]
    reference = profile_ledger_bytes(_profile(bars, base_time))
    outside = make_bar(2, base_time - timedelta(minutes=1), "50", "50", "999")
    post = make_bar(3, base_time + timedelta(minutes=20), "200", "200", "999")
    assert profile_ledger_bytes(_profile(bars + [outside], base_time)) == reference
    assert profile_ledger_bytes(_profile(bars + [post], base_time)) == reference


def test_split_bar_preserves_uniform_volume_but_doubles_tpo(base_time):
    one = [make_bar(1, base_time, "100", "102", "20")]
    split = [
        make_bar(1, base_time, "100", "102", "10"),
        make_bar(2, base_time + timedelta(minutes=1), "100", "102", "10"),
    ]
    uniform_one = _profile(one, base_time)
    uniform_split = _profile(split, base_time)
    assert [b.profile_weight for b in uniform_one.bins] == [
        b.profile_weight for b in uniform_split.bins
    ]
    tpo_one = _profile(one, base_time, AllocationMethod.TPO)
    tpo_split = _profile(split, base_time, AllocationMethod.TPO)
    assert [b.profile_weight * 2 for b in tpo_one.bins] == [
        b.profile_weight for b in tpo_split.bins
    ]


def test_scaling_volume_scales_weights_without_geometry_change(base_time):
    bars = [
        make_bar(1, base_time, "100", "100", "30"),
        make_bar(2, base_time + timedelta(minutes=1), "101", "101", "10"),
        make_bar(3, base_time + timedelta(minutes=2), "102", "102", "20"),
    ]
    scaled = [
        type(bar)(
            bar.source_row_id,
            bar.close_time,
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume * 7,
            bar.symbol,
        )
        for bar in bars
    ]
    first, second = _profile(bars, base_time), _profile(scaled, base_time)
    assert first.poc_bin_index == second.poc_bin_index
    assert [b.profile_weight * 7 for b in first.bins] == [
        b.profile_weight for b in second.bins
    ]
    assert [
        (n.hvn_low, n.hvn_high, n.peak_price)
        for n in extract_hvns(first, Decimal("1.5"))[1]
    ] == [
        (n.hvn_low, n.hvn_high, n.peak_price)
        for n in extract_hvns(second, Decimal("1.5"))[1]
    ]


def test_translating_prices_by_whole_bin_width_translates_geometry(base_time):
    bars = [
        make_bar(1, base_time, "100", "100", "30"),
        make_bar(2, base_time + timedelta(minutes=1), "101", "101", "10"),
        make_bar(3, base_time + timedelta(minutes=2), "102", "102", "20"),
    ]
    shift = Decimal(10)
    translated = [
        type(bar)(
            bar.source_row_id,
            bar.close_time,
            bar.open + shift,
            bar.high + shift,
            bar.low + shift,
            bar.close + shift,
            bar.volume,
            bar.symbol,
        )
        for bar in bars
    ]
    first, second = _profile(bars, base_time), _profile(translated, base_time)
    assert second.poc_bin_index - first.poc_bin_index == 10
    assert [b.bin_low + shift for b in first.bins] == [b.bin_low for b in second.bins]


def test_forbidden_path_blocks_before_archive_open(monkeypatch):
    opened = False

    def forbidden_open(*args, **kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("archive should not open")

    monkeypatch.setattr("zipfile.ZipFile", forbidden_open)
    with pytest.raises(PermissionError):
        databento_rows_from_zip(
            Path("/data/nq2024.zip"),
            "forbidden.csv.zst",
            allowed_year=2024,
        )
    assert not opened


def test_random_decimal_uniform_conservation_and_tpo_oracle(base_time):
    rng = random.Random(SEED)
    bars = []
    for i in range(100):
        low_ticks = rng.randrange(400, 460)
        width_ticks = rng.randrange(0, 8)
        low = Decimal(low_ticks) / 4
        high = Decimal(low_ticks + width_ticks) / 4
        bars.append(
            make_bar(
                i,
                base_time + timedelta(minutes=i),
                str(low),
                str(high),
                str(rng.randrange(0, 1000)),
            )
        )
    window = simple_window(base_time, 100)
    uniform = construct_profile(
        bars, fixed_atr(base_time), window, AllocationMethod.UNIFORM_VOLUME, Decimal("0.10")
    )
    assert sum((b.profile_weight for b in uniform.bins), Decimal(0)) == sum(
        (bar.volume for bar in bars), Decimal(0)
    )
    tpo = construct_profile(
        bars, fixed_atr(base_time), window, AllocationMethod.TPO, Decimal("0.10")
    )
    expected = sum(
        len(intersected_bin_indices(bar.low, bar.high, tpo.bin_size_rounded))
        for bar in bars
    )
    assert sum((b.profile_weight for b in tpo.bins), Decimal(0)) == expected


def test_repeated_identical_runs_are_byte_identical(base_time):
    bars = [make_bar(1, base_time, "100", "103", "17")]
    assert profile_ledger_bytes(_profile(bars, base_time)) == profile_ledger_bytes(
        _profile(bars, base_time)
    )
