"""Directional impulse fixtures: displacement, volume, efficiency, seasonality."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from hvn.gen5_impulse import (
    DOWN,
    UP,
    SeasonalVolume,
    bucket_of,
    compute_impulse,
    dominant_direction,
    dwell_bucket,
    forward_outcome,
    DISPLACEMENT_BUCKETS,
    EFFICIENCY_BUCKETS,
    RELATIVE_VOLUME_BUCKETS,
)
from hvn.models import Bar

NY = ZoneInfo("America/New_York")
ATR = Decimal("2.00")


def bar(minute_offset: int, close: str, volume: str = "10", *, start=None) -> Bar:
    start = start or datetime(2019, 3, 4, 10, 0, tzinfo=NY)
    close_time = start + timedelta(minutes=minute_offset + 1)
    price = Decimal(close)
    return Bar(
        source_row_id=f"NQH9|{start.date()}|{minute_offset}",
        close_time=close_time,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal(volume),
        symbol="NQH9",
    )


def series(closes: list[str], volumes: list[str] | None = None, *, start=None):
    volumes = volumes or ["10"] * len(closes)
    return [bar(i, c, v, start=start) for i, (c, v) in enumerate(zip(closes, volumes))]


# ---------------------------------------------------------------------------
# Displacement and efficiency


def test_directional_displacement_sums_only_moves_in_that_direction():
    # Closes 100 -> 102 -> 101 -> 104: up moves +2 and +3, down move -1.
    window = series(["100", "102", "101", "104"])
    up = compute_impulse(window, direction=UP, atr=ATR)
    down = compute_impulse(window, direction=DOWN, atr=ATR)
    assert up.directional_displacement_atr == Decimal("2.5")   # 5 points / 2.00
    assert down.directional_displacement_atr == Decimal("0.5")  # 1 point / 2.00


def test_efficiency_separates_a_clean_move_from_a_noisy_one():
    clean = compute_impulse(series(["100", "101", "102", "103"]), direction=UP, atr=ATR)
    noisy = compute_impulse(series(["100", "103", "100", "103"]), direction=UP, atr=ATR)
    # Both finish +3, but the noisy path travels 9 points to get there.
    assert clean.net_close_change_atr == noisy.net_close_change_atr
    assert clean.efficiency == Decimal(1)
    assert noisy.efficiency == Decimal(3) / Decimal(9)
    assert clean.efficiency_bucket == "high"
    assert noisy.efficiency_bucket == "medium"


def test_a_round_trip_has_zero_efficiency():
    result = compute_impulse(series(["100", "104", "100"]), direction=UP, atr=ATR)
    assert result.efficiency == 0
    assert result.net_close_change_atr == 0
    # The up displacement is still real: price did travel 4 points up.
    assert result.directional_displacement_atr == Decimal(2)


def test_a_flat_window_has_zero_movement_and_zero_efficiency():
    result = compute_impulse(series(["100", "100", "100"]), direction=UP, atr=ATR)
    assert result.efficiency == 0
    assert result.directional_displacement_atr == 0


def test_a_window_shorter_than_two_bars_is_not_evaluated():
    assert not compute_impulse(series(["100"]), direction=UP, atr=ATR).evaluated
    assert not compute_impulse([], direction=UP, atr=ATR).evaluated


def test_dominant_direction_breaks_an_exact_tie_downward():
    assert dominant_direction(series(["100", "103", "101"])) == UP
    assert dominant_direction(series(["100", "101", "97"])) == DOWN
    # +2 up then -2 down is an exact tie.
    assert dominant_direction(series(["100", "102", "100"])) == DOWN


# ---------------------------------------------------------------------------
# Seasonal volume baseline


def _session(day: int, volumes: list[str]):
    start = datetime(2019, 3, day, 10, 0, tzinfo=NY)
    return series(["100"] * len(volumes), volumes, start=start)


def test_the_baseline_uses_only_strictly_prior_sessions():
    bars = []
    for day, volume in ((4, "10"), (5, "20"), (6, "30"), (7, "999")):
        bars += _session(day, [volume, volume])
    seasonal = SeasonalVolume(bars)
    # On the 7th, the 10:00 baseline is the median of 10, 20, 30 from the 4th to
    # the 6th. The 7th's own huge volume must not enter its own baseline.
    target = datetime(2019, 3, 7, 10, 0, tzinfo=NY)
    assert seasonal.expected(target) == Decimal(20)


def test_a_minute_with_too_few_prior_sessions_has_no_baseline():
    bars = _session(4, ["10", "10"]) + _session(5, ["10", "10"])
    seasonal = SeasonalVolume(bars)
    # Only two prior observations on the 6th, below the three-observation floor.
    assert seasonal.expected(datetime(2019, 3, 6, 10, 0, tzinfo=NY)) is None
    # And the first session has none at all.
    assert seasonal.expected(datetime(2019, 3, 4, 10, 0, tzinfo=NY)) is None


def test_the_baseline_is_per_minute_of_day_not_a_daily_average():
    bars = []
    for day in (4, 5, 6, 7):
        # 10:00 is quiet, 10:01 is busy, every session.
        bars += _session(day, ["10", "500"])
    seasonal = SeasonalVolume(bars)
    quiet = seasonal.expected(datetime(2019, 3, 7, 10, 0, tzinfo=NY))
    busy = seasonal.expected(datetime(2019, 3, 7, 10, 1, tzinfo=NY))
    assert quiet == Decimal(10)
    assert busy == Decimal(500)


def test_relative_volume_uses_the_seasonal_baseline_not_the_local_one():
    history = []
    for day in (4, 5, 6):
        history += _session(day, ["100", "100", "100"])
    today = _session(7, ["100", "300", "300"])
    seasonal = SeasonalVolume(history + today)
    # Every close rises, so all volume is directional; 600 traded against a
    # 200 baseline over the two counted bars.
    window = [
        bar(0, "100", "100", start=datetime(2019, 3, 7, 10, 0, tzinfo=NY)),
        bar(1, "101", "300", start=datetime(2019, 3, 7, 10, 0, tzinfo=NY)),
        bar(2, "102", "300", start=datetime(2019, 3, 7, 10, 0, tzinfo=NY)),
    ]
    result = compute_impulse(window, direction=UP, atr=ATR, seasonal=seasonal)
    assert result.seasonal_baseline_available
    assert result.directional_volume_ratio == Decimal(3)
    assert result.volume_bucket == "extreme"


def test_volume_ratio_is_undefined_without_a_baseline_rather_than_assumed():
    window = series(["100", "101"], ["50", "50"])
    seasonal = SeasonalVolume([])
    result = compute_impulse(window, direction=UP, atr=ATR, seasonal=seasonal)
    assert result.directional_volume_ratio is None
    assert result.volume_bucket == "undefined"
    assert not result.seasonal_baseline_available


def test_volume_counts_only_bars_moving_in_the_direction():
    history = []
    for day in (4, 5, 6):
        history += _session(day, ["100", "100", "100"])
    window = [
        bar(0, "100", "100", start=datetime(2019, 3, 7, 10, 0, tzinfo=NY)),
        bar(1, "101", "400", start=datetime(2019, 3, 7, 10, 0, tzinfo=NY)),
        bar(2, "100", "400", start=datetime(2019, 3, 7, 10, 0, tzinfo=NY)),
    ]
    seasonal = SeasonalVolume(history + window)
    up = compute_impulse(window, direction=UP, atr=ATR, seasonal=seasonal)
    down = compute_impulse(window, direction=DOWN, atr=ATR, seasonal=seasonal)
    # The up bar and the down bar each carry 400 against a 200 total baseline.
    assert up.directional_volume_ratio == Decimal(2)
    assert down.directional_volume_ratio == Decimal(2)


# ---------------------------------------------------------------------------
# Buckets


def test_buckets_are_half_open_and_exhaustive_at_the_edges():
    assert bucket_of(Decimal("0.79"), RELATIVE_VOLUME_BUCKETS) == "below_normal"
    assert bucket_of(Decimal("0.80"), RELATIVE_VOLUME_BUCKETS) == "normal"
    assert bucket_of(Decimal("1.25"), RELATIVE_VOLUME_BUCKETS) == "elevated"
    assert bucket_of(Decimal("2.00"), RELATIVE_VOLUME_BUCKETS) == "extreme"
    assert bucket_of(Decimal("99"), RELATIVE_VOLUME_BUCKETS) == "extreme"
    assert bucket_of(None, RELATIVE_VOLUME_BUCKETS) == "undefined"

    assert bucket_of(Decimal("0.49"), DISPLACEMENT_BUCKETS) == "lt_0.5"
    assert bucket_of(Decimal("1.5"), DISPLACEMENT_BUCKETS) == "gt_1.5"
    assert bucket_of(Decimal("0.30"), EFFICIENCY_BUCKETS) == "medium"

    assert dwell_bucket(0) == "0-2"
    assert dwell_bucket(3) == "3-6"
    assert dwell_bucket(12) == "7-12"
    assert dwell_bucket(400) == "13+"
    assert dwell_bucket(None) == "undefined"


# ---------------------------------------------------------------------------
# Forward outcome


def test_continuation_and_reversion_are_complementary():
    forward = series(["100"] * 14 + ["106"])
    up = forward_outcome(
        forward, direction=UP, reference_close=Decimal("100"), atr=ATR, horizon_bars=15
    )
    assert up.evaluated and up.continued and not up.reverted
    assert up.signed_move_atr == Decimal(3)

    down = forward_outcome(
        forward, direction=DOWN, reference_close=Decimal("100"), atr=ATR, horizon_bars=15
    )
    assert down.reverted and not down.continued
    assert down.signed_move_atr == Decimal(-3)


def test_an_unchanged_close_is_neither_continuation_nor_reversion():
    forward = series(["100"] * 15)
    result = forward_outcome(
        forward, direction=UP, reference_close=Decimal("100"), atr=ATR, horizon_bars=15
    )
    assert result.evaluated
    assert result.continued is False and result.reverted is False


def test_a_short_forward_window_is_not_evaluated():
    result = forward_outcome(
        series(["100"] * 5),
        direction=UP,
        reference_close=Decimal("100"),
        atr=ATR,
        horizon_bars=15,
    )
    assert not result.evaluated and result.signed_move_atr is None


def test_no_seasonal_baseline_is_reported_as_unavailable_not_available():
    result = compute_impulse(series(["100", "101"]), direction=UP, atr=ATR)
    assert result.directional_volume_ratio is None
    assert result.seasonal_baseline_available is False
