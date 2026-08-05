"""Stage 4 sources: window causality, value area both ways, TPO extremes, VWAP."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from hvn.models import Bar
from hvn.profile_sources import (
    P2_SINGLE_HOUR,
    P4_CASH_DEVELOPING,
    P5_PRIOR_RTH,
    build_source_profile,
    cash_developing_window,
    globex_developing_window,
    poc_index,
    prior_rth_window,
    profile_from_window,
    single_hour_window,
    tpo_extremes,
    value_area_pct,
    value_area_sigma,
    volume_weighted_moments,
)
from hvn.vwap_sources import (
    P7_VWAP_CASH,
    PERCENT_BANDS,
    SIGMA_BANDS,
    anchored_vwap,
    band_levels,
    build_vwap,
)

NY = ZoneInfo("America/New_York")
ATR = Decimal("2.00")


def bar(when: datetime, low: str, high: str, volume: str = "10", close=None) -> Bar:
    return Bar(
        source_row_id=f"NQH9|{when.isoformat()}",
        close_time=when,
        open=Decimal(low),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close if close is not None else high),
        volume=Decimal(volume),
        symbol="NQH9",
    )


def run(start: datetime, count: int, low="100", high="101", volume="10"):
    return [bar(start + timedelta(minutes=i + 1), low, high, volume) for i in range(count)]


# ---------------------------------------------------------------------------
# Window causality


def test_no_window_returns_a_bar_that_closed_after_the_anchor():
    bars = run(datetime(2019, 3, 4, 8, 0, tzinfo=NY), 240)
    anchor = datetime(2019, 3, 4, 11, 0, tzinfo=NY)
    for selector in (
        single_hour_window,
        globex_developing_window,
        cash_developing_window,
        prior_rth_window,
    ):
        for candidate in selector(bars, anchor):
            assert candidate.close_time <= anchor, selector.__name__


def test_the_single_hour_window_is_exactly_the_hour_before_the_anchor():
    bars = run(datetime(2019, 3, 4, 8, 0, tzinfo=NY), 240)
    anchor = datetime(2019, 3, 4, 11, 0, tzinfo=NY)
    window = single_hour_window(bars, anchor)
    assert len(window) == 60
    assert window[0].close_time == datetime(2019, 3, 4, 10, 1, tzinfo=NY)
    assert window[-1].close_time == anchor


def test_the_cash_window_is_empty_before_the_cash_open():
    bars = run(datetime(2019, 3, 4, 1, 0, tzinfo=NY), 120)
    anchor = datetime(2019, 3, 4, 3, 0, tzinfo=NY)
    assert cash_developing_window(bars, anchor) == []
    assert build_source_profile(bars, anchor, atr=ATR, source=P4_CASH_DEVELOPING) is None


def test_the_globex_window_starts_at_the_evening_open_not_midnight():
    evening = run(datetime(2019, 3, 3, 18, 0, tzinfo=NY), 120, low="200", high="201")
    morning = run(datetime(2019, 3, 4, 9, 0, tzinfo=NY), 60)
    anchor = datetime(2019, 3, 4, 10, 0, tzinfo=NY)
    window = globex_developing_window(evening + morning, anchor)
    # The prior evening belongs to the 2019-03-04 session and must be included.
    assert any(b.low == Decimal("200") for b in window)


def test_the_prior_rth_window_is_the_previous_session_cash_hours_only():
    prior_cash = run(datetime(2019, 3, 4, 9, 30, tzinfo=NY), 390, low="150", high="151")
    prior_evening = run(datetime(2019, 3, 4, 18, 0, tzinfo=NY), 60, low="300", high="301")
    today = run(datetime(2019, 3, 5, 9, 30, tzinfo=NY), 60)
    anchor = datetime(2019, 3, 5, 11, 0, tzinfo=NY)
    window = prior_rth_window(prior_cash + prior_evening + today, anchor)
    assert window, "the previous session's cash hours must be found"
    assert all(b.low == Decimal("150") for b in window)


def test_a_source_with_fewer_than_two_bars_yields_no_profile():
    bars = run(datetime(2019, 3, 4, 10, 0, tzinfo=NY), 1)
    anchor = bars[-1].close_time
    assert build_source_profile(bars, anchor, atr=ATR, source=P2_SINGLE_HOUR) is None


def test_the_prior_rth_source_is_absent_on_the_first_session():
    bars = run(datetime(2019, 3, 4, 9, 30, tzinfo=NY), 60)
    anchor = datetime(2019, 3, 4, 11, 0, tzinfo=NY)
    assert build_source_profile(bars, anchor, atr=ATR, source=P5_PRIOR_RTH) is None


# ---------------------------------------------------------------------------
# Value area


def _graded_profile():
    """Heavy volume in the middle, light at the wings."""
    start = datetime(2019, 3, 4, 10, 0, tzinfo=NY)
    bars, minute = [], 0
    for tick in range(40):
        price = Decimal("100.00") + Decimal(tick) * Decimal("0.25")
        volume = "500" if 16 <= tick < 24 else "20"
        bars.append(
            bar(start + timedelta(minutes=minute + 1), str(price),
                str(price + Decimal("0.25")), volume)
        )
        minute += 1
    return profile_from_window(bars, bars[-1].close_time, atr=ATR, label="TEST")


def test_the_poc_sits_in_the_heavy_zone():
    profile = _graded_profile()
    peak = profile.tick_low(poc_index(profile))
    assert Decimal("104.00") <= peak < Decimal("106.00")


def test_the_value_area_is_narrower_than_the_full_range():
    profile = _graded_profile()
    low, high = value_area_pct(profile)
    assert profile.tick_low(profile.low_index) <= low < high
    assert high <= profile.tick_high(profile.high_index)
    assert (high - low) < (
        profile.tick_high(profile.high_index) - profile.tick_low(profile.low_index)
    )


def test_a_larger_fraction_never_gives_a_narrower_value_area():
    profile = _graded_profile()
    narrow = value_area_pct(profile, Decimal("0.50"))
    wide = value_area_pct(profile, Decimal("0.90"))
    assert (wide[1] - wide[0]) >= (narrow[1] - narrow[0])


def test_sigma_bands_widen_with_the_multiple_and_straddle_the_mean():
    profile = _graded_profile()
    mean, sigma = volume_weighted_moments(profile)
    assert sigma > 0
    one = value_area_sigma(profile, Decimal(1))
    two = value_area_sigma(profile, Decimal(2))
    assert one[0] < mean < one[1]
    assert two[0] < one[0] and two[1] > one[1]


# ---------------------------------------------------------------------------
# TPO extremes


def _tpo_profile():
    """One tick visited once, one visited twice, the rest visited many times."""
    start = datetime(2019, 3, 4, 10, 0, tzinfo=NY)
    bars, minute = [], 0
    for tick in range(30):
        price = Decimal("100.00") + Decimal(tick) * Decimal("0.25")
        visits = 1 if tick == 10 else 2 if tick == 20 else 8
        for _ in range(visits):
            bars.append(
                bar(start + timedelta(minutes=minute + 1), str(price),
                    str(price + Decimal("0.25")))
            )
            minute += 1
    return profile_from_window(bars, bars[-1].close_time, atr=ATR, label="TEST")


def test_a_single_print_is_found_by_t1_and_the_two_print_is_not():
    profile = _tpo_profile()
    single = tpo_extremes(profile, threshold="T1")
    assert len(single) == 1
    assert single[0][0] == Decimal("102.50")  # tick 10


def test_t2_admits_both_the_one_and_two_print_levels():
    profile = _tpo_profile()
    levels = tpo_extremes(profile, threshold="T2")
    lows = {low for low, _ in levels}
    assert Decimal("102.50") in lows and Decimal("105.00") in lows


def test_adjacent_thin_ticks_become_one_level_not_several():
    start = datetime(2019, 3, 4, 10, 0, tzinfo=NY)
    bars, minute = [], 0
    for tick in range(20):
        price = Decimal("100.00") + Decimal(tick) * Decimal("0.25")
        visits = 1 if tick in (8, 9, 10) else 6
        for _ in range(visits):
            bars.append(
                bar(start + timedelta(minutes=minute + 1), str(price),
                    str(price + Decimal("0.25")))
            )
            minute += 1
    profile = profile_from_window(bars, bars[-1].close_time, atr=ATR, label="TEST")
    levels = tpo_extremes(profile, threshold="T1")
    assert len(levels) == 1, "three adjacent single prints are one shelf"
    assert levels[0][1] - levels[0][0] >= Decimal("0.75")


# ---------------------------------------------------------------------------
# Anchored VWAP


def test_the_vwap_leans_toward_the_heavier_price():
    start = datetime(2019, 3, 4, 10, 0, tzinfo=NY)
    light = bar(start + timedelta(minutes=1), "100", "100", "1", close="100")
    heavy = bar(start + timedelta(minutes=2), "200", "200", "99", close="200")
    result = anchored_vwap([light, heavy], heavy.close_time, source="TEST")
    assert result.vwap > Decimal("190")


def test_a_flat_window_has_no_dispersion():
    bars = run(datetime(2019, 3, 4, 10, 0, tzinfo=NY), 10, low="100", high="100")
    result = anchored_vwap(bars, bars[-1].close_time, source="TEST")
    assert result.dispersion == 0


def test_sigma_bands_and_percent_bands_both_straddle_the_vwap():
    bars = run(datetime(2019, 3, 4, 10, 0, tzinfo=NY), 60, low="100", high="104")
    result = anchored_vwap(bars, bars[-1].close_time, source="TEST")
    for definition in (SIGMA_BANDS, PERCENT_BANDS):
        levels = band_levels(result, definition=definition)
        assert levels["VWAP"] == result.vwap
        above = [v for k, v in levels.items() if k.startswith("+")]
        below = [v for k, v in levels.items() if k.startswith("-")]
        assert len(above) == 4 and len(below) == 4
        assert min(above) > result.vwap > max(below)


def test_percent_bands_ignore_volatility_and_sigma_bands_do_not():
    start = datetime(2019, 3, 4, 10, 0, tzinfo=NY)

    def walk(step: str):
        """Prices that move bar to bar — VWAP dispersion is across bars."""
        out = []
        for i in range(60):
            price = Decimal("1000") + Decimal(step) * Decimal(i % 10 - 5)
            out.append(
                bar(start + timedelta(minutes=i + 1), str(price), str(price),
                    close=str(price))
            )
        return out

    calm, wild = walk("0.25"), walk("20")
    calm_v = anchored_vwap(calm, calm[-1].close_time, source="TEST")
    wild_v = anchored_vwap(wild, wild[-1].close_time, source="TEST")
    # Sigma responds to the range; the percentage offset does not.
    assert wild_v.dispersion > calm_v.dispersion
    calm_pct = band_levels(calm_v, definition=PERCENT_BANDS)
    wild_pct = band_levels(wild_v, definition=PERCENT_BANDS)
    calm_width = calm_pct["+1.00%"] - calm_v.vwap
    wild_width = wild_pct["+1.00%"] - wild_v.vwap
    assert abs(calm_width / calm_v.vwap - wild_width / wild_v.vwap) < Decimal("0.0001")


def test_the_cash_vwap_is_absent_before_the_cash_open():
    bars = run(datetime(2019, 3, 4, 1, 0, tzinfo=NY), 60)
    anchor = datetime(2019, 3, 4, 2, 0, tzinfo=NY)
    assert build_vwap(bars, anchor, source=P7_VWAP_CASH) is None


# ---------------------------------------------------------------------------
# Resampling for the 5-minute ATR


def test_resampling_preserves_the_extremes_and_sums_the_volume():
    from hvn.profile_sources import resample

    start = datetime(2019, 3, 4, 10, 0, tzinfo=NY)
    bars = [
        bar(start + timedelta(minutes=i + 1), str(100 + i), str(110 + i), "10")
        for i in range(5)
    ]
    five = resample(bars, 5)
    assert len(five) == 1
    assert five[0].high == max(b.high for b in bars)
    assert five[0].low == min(b.low for b in bars)
    assert five[0].volume == Decimal(50)


def test_a_resampled_bar_is_stamped_with_its_last_constituent_close():
    from hvn.profile_sources import resample

    start = datetime(2019, 3, 4, 10, 0, tzinfo=NY)
    bars = run(start, 10)
    five = resample(bars, 5)
    for aggregated in five:
        contributors = [b for b in bars if b.close_time <= aggregated.close_time]
        assert aggregated.close_time == max(b.close_time for b in contributors[-5:])
        assert aggregated.close_time <= bars[-1].close_time


def test_one_minute_resampling_is_the_identity():
    from hvn.profile_sources import resample

    bars = run(datetime(2019, 3, 4, 10, 0, tzinfo=NY), 10)
    assert resample(bars, 1) == bars
