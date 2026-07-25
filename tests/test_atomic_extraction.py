"""Generation 3 atomic extraction, against hand-calculated profiles."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from hvn.atomic import (
    AtomicHvn,
    extract_atomic_hvns,
    neutral_weight_window,
    ordinary_bin_controls,
)
from hvn.models import (
    AllocationMethod,
    FrozenProfile,
    ProfileBin,
    ProfileFamily,
    ProfileWindow,
)

START = datetime(2021, 3, 1, 9, 30, tzinfo=timezone.utc)
WHEN = datetime(2021, 3, 1, 16, 0, tzinfo=timezone.utc)


def build_profile(weights: list[int], *, bin_size: str = "10", atr: str = "40"):
    """One bin per weight, 10 points wide, starting at 1000. ATR 40 -> +/-0.50
    ATR is a 20-point radius, i.e. two bins each side."""
    size = Decimal(bin_size)
    total = Decimal(sum(weights)) or Decimal(1)
    poc = max(range(len(weights)), key=lambda i: (weights[i], -i))
    bins, cumulative = [], Decimal(0)
    for index, weight in enumerate(weights):
        low = Decimal(1000) + size * index
        share = Decimal(weight) / total
        cumulative += share
        bins.append(
            ProfileBin(
                index, low, low + size, low + size / 2,
                Decimal(weight), share, cumulative, index == poc,
            )
        )
    window = ProfileWindow(ProfileFamily.PRIOR_RTH, "2021-03-01", START, WHEN, WHEN)
    return FrozenProfile(
        "PROF-TEST", window, AllocationMethod.UNIFORM_VOLUME, WHEN, Decimal(atr),
        Decimal("0.10"), size, size, bins[0].bin_low, bins[-1].bin_high,
        tuple(bins), poc, ("row-1",), total, total, "test-sha", "2021",
    )


# 1. A single-bin atomic peak.
def test_single_bin_atomic_peak():
    profile = build_profile([10, 10, 40, 10, 10])
    atomics = extract_atomic_hvns(profile, Decimal("2.0"))
    assert len(atomics) == 1
    atomic = atomics[0]
    assert (atomic.start_bin_index, atomic.end_bin_index) == (2, 2)
    assert atomic.width_bins == 1
    assert not atomic.is_plateau
    assert (atomic.atomic_low, atomic.atomic_high) == (Decimal(1020), Decimal(1030))
    assert atomic.peak_weight == 40
    assert atomic.local_baseline == 10          # median of bins 0,1,3,4
    assert atomic.prominence_ratio == 4         # 40 / 10
    assert atomic.contains_poc


# 2. An equal-weight plateau is one atomic feature spanning both bins.
def test_equal_weight_plateau_is_one_atomic_feature():
    profile = build_profile([10, 10, 40, 40, 10, 10])
    atomics = extract_atomic_hvns(profile, Decimal("2.0"))
    assert len(atomics) == 1
    atomic = atomics[0]
    assert (atomic.start_bin_index, atomic.end_bin_index) == (2, 3)
    assert atomic.width_bins == 2
    assert atomic.is_plateau
    assert (atomic.atomic_low, atomic.atomic_high) == (Decimal(1020), Decimal(1040))


# 3. No expansion through neighbouring bins holding >= 50% of peak weight.
def test_no_fifty_percent_expansion():
    # Bins 1 and 3 hold 25 = 62.5% of the peak's 40. The broad definition would
    # have swallowed them; the atomic zone must not.
    profile = build_profile([8, 25, 40, 25, 8])
    atomics = extract_atomic_hvns(profile, Decimal("1.5"))
    assert len(atomics) == 1
    atomic = atomics[0]
    assert (atomic.start_bin_index, atomic.end_bin_index) == (2, 2)
    assert atomic.width_bins == 1
    assert atomic.atomic_high - atomic.atomic_low == Decimal(10)


# 4. Two qualifying peaks are never merged, even when close together.
def test_atomic_peaks_are_never_merged():
    profile = build_profile([5, 40, 6, 40, 5], bin_size="10", atr="120")
    atomics = extract_atomic_hvns(profile, Decimal("1.5"))
    assert len(atomics) == 2
    assert [(a.start_bin_index, a.end_bin_index) for a in atomics] == [(1, 1), (3, 3)]
    assert atomics[0].atomic_high <= atomics[1].atomic_low


# 5. The POC flag.
def test_poc_flag_distinguishes_peaks():
    profile = build_profile([5, 30, 6, 60, 5], bin_size="10", atr="120")
    atomics = extract_atomic_hvns(profile, Decimal("1.5"))
    flags = {(a.start_bin_index, a.contains_poc) for a in atomics}
    assert flags == {(1, False), (3, True)}


# 6/7/8. Bands, distance to zone, distance to peak centre.
def test_bands_and_distances():
    profile = build_profile([10, 10, 40, 10, 10])
    atomic = extract_atomic_hvns(profile, Decimal("2.0"))[0]
    atr = Decimal(40)
    assert atomic.contains(Decimal(1020))            # inclusive low
    assert not atomic.contains(Decimal(1030))        # exclusive high
    assert atomic.distance_atr(Decimal(1025), atr) == 0
    # 10 points below the low edge, over ATR 40 -> 0.25
    assert atomic.distance_atr(Decimal(1010), atr) == Decimal("0.25")
    # 10 points above the high edge
    assert atomic.distance_atr(Decimal(1040), atr) == Decimal("0.25")
    # peak centre is 1025
    assert atomic.peak_distance_atr(Decimal(1045), atr) == Decimal("0.50")
    low, high = atomic.band(Decimal("0.25"), atr)
    assert (low, high) == (Decimal(1010), Decimal(1040))
    assert atomic.in_band(Decimal(1010), Decimal("0.25"), atr)
    assert not atomic.in_band(Decimal(1040), Decimal("0.25"), atr)
    assert atomic.in_band(Decimal(1000), Decimal("0.50"), atr)


def test_touch_uses_half_open_boundaries():
    profile = build_profile([10, 10, 40, 10, 10])
    atomic = extract_atomic_hvns(profile, Decimal("2.0"))[0]
    assert atomic.touched_by(Decimal(1015), Decimal(1022))   # wick into zone
    assert atomic.touched_by(Decimal(1020), Decimal(1020))   # exactly the low
    assert not atomic.touched_by(Decimal(1030), Decimal(1035))  # at/above high
    assert not atomic.touched_by(Decimal(1000), Decimal(1019))  # stops short
    assert atomic.touched_by(Decimal(1000), Decimal(1099))   # cross through


# 19/20. Ordinary-bin controls, and exclusion around peaks and the POC.
def test_ordinary_bin_controls_exclude_peaks_and_poc():
    profile = build_profile([9, 10, 40, 11, 9, 10, 12, 9], bin_size="10", atr="40")
    atomics = extract_atomic_hvns(profile, Decimal("2.0"))
    assert [(a.start_bin_index, a.end_bin_index) for a in atomics] == [(2, 2)]
    windows = ordinary_bin_controls(profile, atomics, width_bins=1)
    chosen = {start for start, _ in windows}
    assert 2 not in chosen                      # the peak itself
    assert 1 not in chosen and 3 not in chosen  # bins touching the peak
    assert profile.poc_bin_index not in chosen
    assert chosen == {0, 4, 5, 6, 7} - {profile.poc_bin_index}


def test_plateau_width_controls_match_width():
    profile = build_profile([9, 10, 40, 40, 11, 9, 10, 12, 9, 10], atr="40")
    atomics = extract_atomic_hvns(profile, Decimal("2.0"))
    assert atomics[0].width_bins == 2
    windows = ordinary_bin_controls(profile, atomics, width_bins=2)
    assert windows, "expected at least one two-bin ordinary window"
    for start, end in windows:
        assert end - start + 1 == 2
        assert not (start <= 3 and end >= 2)     # never overlaps the plateau
        assert profile.poc_bin_index not in range(start, end + 1)


def test_controls_never_extend_beyond_the_grid():
    profile = build_profile([9, 10, 40, 11, 9], atr="40")
    atomics = extract_atomic_hvns(profile, Decimal("2.0"))
    for start, end in ordinary_bin_controls(profile, atomics, width_bins=2):
        assert start >= 0 and end <= 4


def test_neutral_weight_window_is_the_middle_quartiles():
    profile = build_profile([10, 20, 30, 40, 50])
    low, high = neutral_weight_window(profile)
    assert (low, high) == (Decimal(20), Decimal(40))


def test_below_threshold_peaks_do_not_qualify():
    profile = build_profile([10, 10, 15, 10, 10])   # prominence 1.5
    assert len(extract_atomic_hvns(profile, Decimal("1.5"))) == 1   # equality qualifies
    assert extract_atomic_hvns(profile, Decimal("2.0")) == ()


def test_atomic_zone_is_strictly_narrower_than_the_broad_node():
    """The Generation 1/2 definition expands and merges; Generation 3 must not.

    Bins 1 and 3 hold 25, which is 62.5% of the peak's 40, so the broad
    definition swallows them into one wide node. The atomic zone is the peak
    bin alone.
    """
    from hvn.hvn import extract_hvns

    profile = build_profile([8, 25, 40, 25, 8])
    _, broad_nodes = extract_hvns(profile, Decimal("1.5"))
    atomics = extract_atomic_hvns(profile, Decimal("1.5"))
    assert len(broad_nodes) == 1 and len(atomics) == 1
    broad, atomic = broad_nodes[0], atomics[0]
    assert broad.hvn_high - broad.hvn_low == Decimal(30)   # bins 1..3
    assert atomic.atomic_high - atomic.atomic_low == Decimal(10)  # bin 2 only
    assert atomic.atomic_low >= broad.hvn_low
    assert atomic.atomic_high <= broad.hvn_high
    assert atomic.peak_price == broad.peak_price
