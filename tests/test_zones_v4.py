"""Generation 4 smoothed HVN zone fixtures.

Every expectation here is hand-derived from
`research/hvn/STAGE_02_GENERATION_4_ZONE_SPEC.md`, not from production output.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hvn.models import AtrPoint, Bar, ProfileFamily, ProfileWindow
from hvn.zones_v4 import (
    BROAD_ACTIVITY_DISTRIBUTION,
    NO_VALID_BASIN_SEPARATION,
    NONPOC_HVN_ZONE,
    POC_HVN_ZONE,
    TickProfile,
    _merged_pairs,
    _replace_rejection,
    classify_zones,
    construct_tick_profile,
    maximum_poc_zone_width_ticks,
    maximum_zone_width_ticks,
    minimum_zone_width_ticks,
    profile_activity,
    smooth,
    smoothing_half_width_ticks,
    triangular_weights,
)

ATR = Decimal("20.00")


def window(start: datetime) -> ProfileWindow:
    end = start + timedelta(minutes=60)
    return ProfileWindow(
        family=ProfileFamily.PRIOR_RTH,
        source_session_date=start.date().isoformat(),
        source_start=start,
        source_end=end,
        freeze_time=end,
    )


def tick_profile(volume: dict[int, Decimal], tpo: dict[int, int], *, atr=ATR) -> TickProfile:
    """A hand-built tick profile; indices are contiguous by construction."""
    low, high = min(volume), max(volume)
    for index in range(low, high + 1):
        volume.setdefault(index, Decimal(0))
        tpo.setdefault(index, 0)
    poc = max(range(low, high + 1), key=lambda i: (volume[i], -i))
    start = datetime(2019, 1, 2, 14, 0, tzinfo=UTC)
    return TickProfile(
        profile_id="TESTPROFILE",
        window=window(start),
        atr_reference_time=start,
        atr_value=atr,
        low_index=low,
        high_index=high,
        volume=volume,
        tpo=tpo,
        poc_index=poc,
        source_row_ids=("NQH9|1",),
        source_total_volume=sum(volume.values(), Decimal(0)),
        profile_range_low=Decimal(low) * Decimal("0.25"),
        profile_range_high=Decimal(high + 1) * Decimal("0.25"),
        code_sha="TEST",
        data_partition="development",
    )


# ---------------------------------------------------------------------------
# Frozen scalar rules


def test_smoothing_half_width_is_five_percent_of_atr_with_a_two_tick_floor():
    # 0.05 * 20.00 / 0.25 = 4 ticks.
    assert smoothing_half_width_ticks(Decimal("20.00")) == 4
    # 0.05 * 12.00 / 0.25 = 2.4 -> 2 ticks.
    assert smoothing_half_width_ticks(Decimal("12.00")) == 2
    # 0.05 * 2.00 / 0.25 = 0.4 -> 0, raised to the two-tick floor.
    assert smoothing_half_width_ticks(Decimal("2.00")) == 2
    # Half-up at the exact midpoint: 0.05 * 12.50 / 0.25 = 2.5 -> 3.
    assert smoothing_half_width_ticks(Decimal("12.50")) == 3


def test_triangular_weights_peak_at_the_centre_and_fall_to_one():
    assert triangular_weights(2) == (1, 2, 3, 2, 1)
    assert triangular_weights(1) == (1, 2, 1)


def test_smoothing_renormalizes_at_the_profile_edge():
    values = {0: Decimal(3), 1: Decimal(0), 2: Decimal(0)}
    out = smooth(values, 1, range(0, 3))
    # Edge tick 0 sees weights (2, 1) over available ticks 0 and 1.
    assert out[0] == Decimal(2) * Decimal(3) / Decimal(3)
    # Interior tick 1 sees the full (1, 2, 1) span.
    assert out[1] == Decimal(3) / Decimal(4)


def test_no_zone_may_be_one_tick_wide():
    # 0.10 * 20.00 / 0.25 = 8 ticks.
    assert minimum_zone_width_ticks(Decimal("20.00")) == 8
    # 0.10 * 5.00 / 0.25 = 2 ticks, raised to the four-tick absolute floor.
    assert minimum_zone_width_ticks(Decimal("5.00")) == 4
    # The floor holds for any ATR, however small.
    assert minimum_zone_width_ticks(Decimal("0.50")) == 4


def test_maximum_width_is_never_below_the_minimum():
    # 0.75 * 20.00 / 0.25 = 60 ticks.
    assert maximum_zone_width_ticks(Decimal("20.00")) == 60
    # 0.75 * 1.00 / 0.25 = 3 ticks, which is below the four-tick minimum.
    assert maximum_zone_width_ticks(Decimal("1.00")) == 4
    assert maximum_zone_width_ticks(Decimal("1.00")) == minimum_zone_width_ticks(
        Decimal("1.00")
    )


# ---------------------------------------------------------------------------
# Densities


def test_composite_activity_is_the_geometric_mean_of_both_proxies():
    volume = {0: Decimal(10), 1: Decimal(30)}
    tpo = {0: 1, 1: 3}
    activity = profile_activity(tick_profile(volume, tpo))
    # Mean volume 20, mean TPO 2, so densities are 0.5/1.5 and 0.5/1.5.
    assert activity.volume_density[0] == Decimal("0.5")
    assert activity.tpo_density[1] == Decimal("1.5")
    assert activity.raw_activity[1] == pytest.approx(Decimal("1.5"))


def test_a_tick_with_no_volume_has_zero_composite_activity():
    activity = profile_activity(tick_profile({0: Decimal(0), 1: Decimal(40)}, {0: 0, 1: 4}))
    assert activity.raw_activity[0] == Decimal(0)


# ---------------------------------------------------------------------------
# Zone geometry


def _twin_peak_profile(gap_ticks: int, valley_volume: int) -> TickProfile:
    """Two symmetric humps separated by `gap_ticks` of `valley_volume`."""
    volume: dict[int, Decimal] = {}
    tpo: dict[int, int] = {}
    hump = [1, 2, 4, 8, 16, 8, 4, 2, 1]
    index = 0
    for _ in range(6):
        volume[index] = Decimal(1)
        tpo[index] = 1
        index += 1
    for weight in hump:
        volume[index] = Decimal(weight)
        tpo[index] = weight
        index += 1
    for _ in range(gap_ticks):
        volume[index] = Decimal(valley_volume)
        tpo[index] = max(1, valley_volume)
        index += 1
    for weight in hump:
        volume[index] = Decimal(weight)
        tpo[index] = weight
        index += 1
    for _ in range(6):
        volume[index] = Decimal(1)
        tpo[index] = 1
        index += 1
    return tick_profile(volume, tpo, atr=Decimal("2.00"))


def test_an_accepted_zone_is_never_one_tick_wide():
    zones, _ = classify_zones(_twin_peak_profile(10, 1))
    accepted = [z for z in zones if z.accepted]
    assert accepted, "expected at least one accepted zone"
    for zone in accepted:
        assert zone.width_ticks >= 4
        assert zone.width_points >= Decimal("1.00")
        assert zone.width_ticks >= zone.minimum_width_ticks


def test_accepted_zones_never_overlap_within_one_profile():
    zones, _ = classify_zones(_twin_peak_profile(10, 1))
    accepted = sorted((z for z in zones if z.accepted), key=lambda z: z.low_index)
    for left, right in zip(accepted, accepted[1:]):
        assert left.high_index < right.low_index


def test_a_deep_valley_keeps_two_peaks_separate():
    zones, _ = classify_zones(_twin_peak_profile(10, 1))
    accepted = [z for z in zones if z.accepted]
    assert len(accepted) >= 2


def test_a_shallow_valley_between_adjacent_cores_becomes_one_broad_distribution():
    """Two cores one tick apart over a valley at 0.85+ of the lower peak."""
    profile = _twin_peak_profile(10, 1)
    zones, activity = classify_zones(profile)
    accepted = sorted((z for z in zones if z.accepted), key=lambda z: z.low_index)
    assert len(accepted) == 2

    # Move the two accepted cores one tick apart and raise the tick between
    # them to the lower peak's own activity: no meaningful separation remains.
    left, right = accepted
    near_left = replace(left, high_index=left.high_index, low_index=left.low_index)
    near_right = replace(
        right,
        low_index=left.high_index + 2,
        high_index=left.high_index + 2 + right.width_ticks - 1,
    )
    smoothed = dict(activity.smoothed_activity)
    smoothed[left.high_index + 1] = min(
        left.peak_smoothed_activity, right.peak_smoothed_activity
    )
    shallow = replace(activity, smoothed_activity=smoothed)
    assert _merged_pairs(shallow, [near_left, near_right]) == {
        near_left.zone_id,
        near_right.zone_id,
    }

    # A deep valley in the same geometry keeps them separate.
    smoothed[left.high_index + 1] = Decimal("0.10")
    deep = replace(activity, smoothed_activity=smoothed)
    assert _merged_pairs(deep, [near_left, near_right]) == set()


def test_a_merged_pair_is_recorded_as_a_broad_activity_distribution():
    zone = _twin_peak_profile(10, 1)
    zones, _ = classify_zones(zone)
    sample = next(z for z in zones if z.accepted and z.zone_class == NONPOC_HVN_ZONE)
    demoted = _replace_rejection(
        sample, NO_VALID_BASIN_SEPARATION, BROAD_ACTIVITY_DISTRIBUTION
    )
    assert demoted.zone_class == BROAD_ACTIVITY_DISTRIBUTION
    assert not demoted.accepted
    assert demoted.rejection_reason == NO_VALID_BASIN_SEPARATION


def test_a_candidate_overlapping_the_poc_zone_is_rejected():
    profile = _twin_peak_profile(10, 1)
    zones, _ = classify_zones(profile)
    poc = next(z for z in zones if z.zone_class == POC_HVN_ZONE)
    poc_span = range(poc.low_index, poc.high_index + 1)
    for zone in zones:
        if zone.zone_class == POC_HVN_ZONE or not zone.accepted:
            continue
        assert not any(i in poc_span for i in range(zone.low_index, zone.high_index + 1))


def test_the_poc_zone_is_always_recorded():
    zones, _ = classify_zones(_twin_peak_profile(10, 1))
    poc = [z for z in zones if z.zone_class in (POC_HVN_ZONE, "POC_BROAD_DISTRIBUTION")]
    assert len(poc) == 1


def test_every_accepted_non_poc_zone_satisfies_all_density_gates():
    zones, _ = classify_zones(_twin_peak_profile(10, 1))
    for zone in zones:
        if not (zone.accepted and zone.zone_class == NONPOC_HVN_ZONE):
            continue
        assert zone.peak_activity_percentile >= Decimal("95.0")
        assert zone.peak_smoothed_activity >= Decimal("1.50")
        assert zone.zone_volume_density >= Decimal("1.25")
        assert zone.zone_tpo_density >= Decimal("1.00")
        assert zone.zone_activity_density >= Decimal("1.35")
        assert zone.peak_to_valley_ratio is not None
        assert zone.peak_to_valley_ratio >= Decimal("1.10")
        assert zone.width_ticks <= zone.maximum_width_ticks


def test_a_flat_profile_produces_no_accepted_non_poc_zone():
    flat = tick_profile(
        {i: Decimal(10) for i in range(40)}, {i: 1 for i in range(40)},
        atr=Decimal("2.00"),
    )
    zones, _ = classify_zones(flat)
    assert not [z for z in zones if z.accepted and z.zone_class == NONPOC_HVN_ZONE]


def test_classification_is_deterministic():
    profile = _twin_peak_profile(10, 1)
    first, _ = classify_zones(profile)
    second, _ = classify_zones(profile)
    assert [
        (z.zone_id, z.low_index, z.high_index, z.accepted, z.rejection_reason)
        for z in first
    ] == [
        (z.zone_id, z.low_index, z.high_index, z.accepted, z.rejection_reason)
        for z in second
    ]


def test_physical_zone_id_is_independent_of_the_consuming_relationship():
    zones, _ = classify_zones(_twin_peak_profile(10, 1))
    accepted = [z for z in zones if z.accepted]
    assert len({z.physical_zone_id for z in accepted}) == len(accepted)


# ---------------------------------------------------------------------------
# Tick-grid construction from real bar geometry


def _bars(start: datetime, rows: list[tuple[str, str, str]]) -> list[Bar]:
    out = []
    for minute, (low, high, volume) in enumerate(rows):
        close = start + timedelta(minutes=minute + 1)
        out.append(
            Bar(
                source_row_id=f"NQH9|{minute}",
                close_time=close,
                open=Decimal(low),
                high=Decimal(high),
                low=Decimal(low),
                close=Decimal(high),
                volume=Decimal(volume),
                symbol="NQH9",
            )
        )
    return out


def test_tick_construction_conserves_volume_and_counts_bin_level_tpo():
    start = datetime(2019, 1, 2, 14, 0, tzinfo=UTC)
    bars = _bars(start, [("100.00", "101.00", "12"), ("100.50", "100.75", "6")])
    atr = (AtrPoint(start - timedelta(minutes=1), Decimal("20.00")),)
    profile = construct_tick_profile(bars, atr, window(start))

    assert sum(profile.volume.values(), Decimal(0)) == Decimal(18)
    # The first bar spans ticks [100.00,101.00) = four ticks; the second spans
    # [100.50,100.75) = one tick. TPO is per occupied tick, not per bar.
    assert sum(profile.tpo.values()) == 5
    assert profile.tpo[int(Decimal("100.50") / Decimal("0.25"))] == 2
    assert profile.tpo[int(Decimal("100.00") / Decimal("0.25"))] == 1


def test_construction_refuses_a_window_with_no_completed_bars():
    start = datetime(2019, 1, 2, 14, 0, tzinfo=UTC)
    atr = (AtrPoint(start - timedelta(minutes=1), Decimal("20.00")),)
    with pytest.raises(ValueError):
        construct_tick_profile([], atr, window(start))


def test_a_bar_completing_after_the_freeze_time_is_excluded():
    start = datetime(2019, 1, 2, 14, 0, tzinfo=UTC)
    rows = [("100.00", "100.25", "4")] * 61
    bars = _bars(start, rows)
    atr = (AtrPoint(start - timedelta(minutes=1), Decimal("20.00")),)
    profile = construct_tick_profile(bars, atr, window(start))
    # Sixty one-minute bars fit inside the sixty-minute window; the last does not.
    assert len(profile.source_row_ids) == 60
    assert sum(profile.volume.values(), Decimal(0)) == Decimal(240)


def test_the_poc_ceiling_is_not_raised_to_the_minimum_width():
    """G4-S05: an accepted POC zone can never exceed 1.00 ATR.

    When the four-tick absolute floor already exceeds 1.00 ATR the POC rule
    `minimum width <= width <= 1.00 ATR` is unsatisfiable, and the POC must be
    a broad distribution rather than an oversized accepted zone.
    """
    # ATR 0.56 points: 1.00 ATR is 2.24 ticks, below the four-tick floor.
    assert maximum_poc_zone_width_ticks(Decimal("0.56")) == 2
    assert minimum_zone_width_ticks(Decimal("0.56")) == 4
    # The non-POC maximum is still clamped upward, as its own rule requires.
    assert maximum_zone_width_ticks(Decimal("0.56")) == 4
