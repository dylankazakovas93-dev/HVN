from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from hvn.interactions import (
    ApproachSide,
    Relationship,
    TouchClass,
    bar_overlaps_zone,
    complete_forward_bars,
    find_first_interaction,
    pre_touch_features,
    relationship_window,
    zone_from_prices,
)
from hvn.models import Bar

NY = ZoneInfo("America/New_York")
ZONE = zone_from_prices("Z", Decimal("100"), Decimal("101"))


def bar(minute: int, low: str, high: str, close: str, *, symbol: str = "NQH5") -> Bar:
    start = datetime(2025, 1, 7, 9, 30, tzinfo=NY) + timedelta(minutes=minute)
    return Bar(
        f"B{minute}-{low}-{high}-{close}-{symbol}",
        start + timedelta(minutes=1),
        Decimal(close),
        Decimal(high),
        Decimal(low),
        Decimal(close),
        Decimal(1),
        symbol,
    )


def window() -> object:
    return relationship_window(
        Relationship.PRIOR_RTH_TO_RTH,
        source_date=date(2025, 1, 6),
        interaction_date=date(2025, 1, 7),
    )


@pytest.mark.parametrize(
    ("relationship", "expected_start", "expected_end"),
    [
        (Relationship.PRIOR_RTH_TO_ETH, (18, 0), (9, 30)),
        (Relationship.PRIOR_RTH_TO_RTH, (9, 30), (16, 0)),
        (Relationship.OVERNIGHT_TO_RTH, (9, 30), (16, 0)),
        (Relationship.MIDNIGHT_TO_RTH, (9, 30), (16, 0)),
        (Relationship.OPENING_HOUR_TO_RTH, (10, 30), (16, 0)),
    ],
)
def test_relationship_windows(relationship, expected_start, expected_end):
    result = relationship_window(
        relationship,
        source_date=date(2025, 1, 6),
        interaction_date=date(2025, 1, 7),
    )
    assert (result.start.hour, result.start.minute) == expected_start
    assert (result.end.hour, result.end.minute) == expected_end


def test_first_touch_only_and_start_inside():
    bars = [bar(0, "100", "100.25", "100"), bar(1, "99", "100", "100")]
    result = find_first_interaction(bars, ZONE, window(), source_contract="NQH5")
    assert result.bar == bars[0]
    assert result.approach_side == ApproachSide.START_INSIDE
    assert result.touch_class == TouchClass.START_INSIDE


@pytest.mark.parametrize(
    ("bars", "side", "touch_class"),
    [
        (
            [bar(0, "99", "99.75", "99.75"), bar(1, "99.75", "100", "99.75")],
            ApproachSide.BELOW,
            TouchClass.WICK_ONLY_SAME_SIDE,
        ),
        (
            [bar(0, "99", "99.75", "99.75"), bar(1, "99.75", "100.5", "100.5")],
            ApproachSide.BELOW,
            TouchClass.CLOSE_INSIDE,
        ),
        (
            [bar(0, "99", "99.75", "99.75"), bar(1, "99.75", "101", "101")],
            ApproachSide.BELOW,
            TouchClass.CROSS_THROUGH,
        ),
        (
            [bar(0, "101", "102", "101"), bar(1, "100.75", "101", "101")],
            ApproachSide.ABOVE,
            TouchClass.WICK_ONLY_SAME_SIDE,
        ),
        (
            [bar(0, "101", "102", "101"), bar(1, "100.5", "101", "100.5")],
            ApproachSide.ABOVE,
            TouchClass.CLOSE_INSIDE,
        ),
        (
            [bar(0, "101", "102", "101"), bar(1, "99.75", "101", "99.75")],
            ApproachSide.ABOVE,
            TouchClass.CROSS_THROUGH,
        ),
    ],
)
def test_approach_and_touch_classes(bars, side, touch_class):
    result = find_first_interaction(bars, ZONE, window(), source_contract="NQH5")
    assert result.approach_side == side
    assert result.touch_class == touch_class


def test_half_open_upper_and_exact_lower_boundary():
    assert not bar_overlaps_zone(bar(0, "101", "101", "101"), ZONE)
    assert bar_overlaps_zone(bar(0, "100", "100", "100"), ZONE)


def test_gap_over_is_not_touch():
    bars = [bar(0, "99", "99.75", "99.75"), bar(1, "101", "102", "101")]
    result = find_first_interaction(bars, ZONE, window(), source_contract="NQH5")
    assert not result.touched
    assert result.eligible


def test_forward_labels_begin_after_touch_and_require_complete_horizon():
    touch = bar(0, "99.75", "100.25", "100")
    following = [bar(index, "100", "100", "100") for index in range(1, 4)]
    complete, reason = complete_forward_bars(
        [touch, *following], touch_bar=touch, window=window(), horizon=3
    )
    assert reason == ""
    assert complete == tuple(following)
    incomplete, reason = complete_forward_bars(
        [touch, *following[:2]], touch_bar=touch, window=window(), horizon=3
    )
    assert incomplete == ()
    assert reason == "WINDOW_END"


def test_missing_bar_and_window_expiry():
    touch = bar(0, "100", "100", "100")
    missing_minute = bar(2, "100", "100", "100")
    complete, reason = complete_forward_bars(
        [touch, missing_minute], touch_bar=touch, window=window(), horizon=1
    )
    assert complete == ()
    assert reason == "MISSING_BAR"


def test_contract_transition_exclusion():
    result = find_first_interaction(
        [bar(0, "99", "99.75", "99.75"), bar(1, "100", "100", "100", symbol="NQM5")],
        ZONE,
        window(),
        source_contract="NQH5",
    )
    assert not result.eligible
    assert result.exclusion_reason == "CONTRACT_TRANSITION"


def test_prior_eth_touch_flag():
    result = find_first_interaction(
        [bar(0, "99", "99.75", "99.75"), bar(1, "100", "100", "100")],
        ZONE,
        window(),
        source_contract="NQH5",
        prior_eth_bars=[bar(0, "100", "100", "100")],
    )
    assert result.touched_during_prior_eth is True


def test_pre_touch_features_use_full_causal_15m_history():
    closes = [str(Decimal(99) + Decimal(index) * Decimal("0.25")) for index in range(16)]
    history = [bar(index - 16, close, close, close) for index, close in enumerate(closes)]
    touch = bar(0, "99.75", "100", "100")
    features = pre_touch_features(
        history,
        touch_bar=touch,
        zone=ZONE,
        window=window(),
        interaction_open=Decimal("99"),
        atr_at_touch=Decimal(2),
        source_profile_low=Decimal(90),
        source_profile_high=Decimal(110),
        poc_price=Decimal(100),
        profile_freeze_time=datetime(2025, 1, 6, 16, tzinfo=NY),
        approach_side=ApproachSide.BELOW,
        touch_class=TouchClass.CLOSE_INSIDE,
        prior_eth_touch_flag=False,
    )
    assert features.signed_15m_pre_touch_displacement_atr == Decimal("1.875")
    assert features.pre_touch_15m_close_path_efficiency == 1
    assert features.profile_age_minutes > 0


def test_pre_touch_history_is_unavailable_not_shortened():
    touch = bar(0, "99.75", "100", "100")
    features = pre_touch_features(
        [bar(-1, "99", "99.75", "99.75")],
        touch_bar=touch,
        zone=ZONE,
        window=window(),
        interaction_open=Decimal("99"),
        atr_at_touch=Decimal(2),
        source_profile_low=Decimal(90),
        source_profile_high=Decimal(110),
        poc_price=Decimal(100),
        profile_freeze_time=datetime(2025, 1, 6, 16, tzinfo=NY),
        approach_side=ApproachSide.BELOW,
        touch_class=TouchClass.CLOSE_INSIDE,
        prior_eth_touch_flag=False,
    )
    assert features.signed_15m_pre_touch_displacement_atr is None
    assert features.pre_touch_15m_close_path_efficiency is None
