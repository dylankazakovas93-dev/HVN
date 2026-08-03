"""Rolling multi-session profile, high/low node detection, and tap validity."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from hvn.models import Bar
from hvn.rolling_profile import (
    HIGH_NODE,
    LOW_NODE,
    build_rolling_profile,
    detect_nodes,
    find_tap,
    reanchor_times,
    rolling_activity,
    session_date,
)

NY = ZoneInfo("America/New_York")
ATR = Decimal("2.00")


def bar(when: datetime, low: str, high: str, volume: str = "10") -> Bar:
    return Bar(
        source_row_id=f"NQH9|{when.isoformat()}",
        close_time=when,
        open=Decimal(low),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(high),
        volume=Decimal(volume),
        symbol="NQH9",
    )


def session(day: int, *, low="100", high="101", count=10, volume="10", hour=10):
    start = datetime(2019, 3, day, hour, 0, tzinfo=NY)
    return [bar(start + timedelta(minutes=i + 1), low, high, volume) for i in range(count)]


# ---------------------------------------------------------------------------
# Session attribution and re-anchoring


def test_the_evening_session_belongs_to_the_next_calendar_date():
    assert session_date(datetime(2019, 3, 4, 10, 0, tzinfo=NY)) == "2019-03-04"
    assert session_date(datetime(2019, 3, 4, 17, 59, tzinfo=NY)) == "2019-03-04"
    # 18:00 opens the next session.
    assert session_date(datetime(2019, 3, 4, 18, 0, tzinfo=NY)) == "2019-03-05"
    assert session_date(datetime(2019, 3, 4, 23, 30, tzinfo=NY)) == "2019-03-05"


def test_reanchors_fall_only_on_the_hour():
    start = datetime(2019, 3, 4, 9, 58, tzinfo=NY)
    bars = [bar(start + timedelta(minutes=i), "100", "101") for i in range(5)]
    anchors = reanchor_times(bars)
    assert len(anchors) == 1
    assert anchors[0].astimezone(NY).minute == 0
    assert anchors[0].astimezone(NY).hour == 10


# ---------------------------------------------------------------------------
# Causality


def test_a_profile_contains_no_bar_that_closed_after_its_anchor():
    bars = session(4, count=30)
    anchor = bars[10].close_time
    profile = build_rolling_profile(bars, anchor, atr=ATR)
    assert profile is not None
    assert profile.bars_used == 11  # the anchor bar itself is complete and counts


def test_a_later_session_never_leaks_into_an_earlier_anchor():
    early = session(4, low="100", high="101")
    late = session(5, low="200", high="201")
    anchor = early[-1].close_time
    profile = build_rolling_profile(early + late, anchor, atr=ATR)
    assert profile is not None
    # The 200-level bars are entirely outside the profile's index range.
    assert profile.tick_high(profile.high_index) <= Decimal("120")


def test_the_window_keeps_only_the_trailing_sessions():
    bars = []
    for day in range(4, 12):
        bars += session(day)
    anchor = bars[-1].close_time
    profile = build_rolling_profile(bars, anchor, atr=ATR, sessions=3)
    assert profile is not None
    assert len(profile.sessions) == 3
    assert profile.sessions[-1] == "2019-03-11"


def test_an_anchor_before_any_data_yields_no_profile():
    bars = session(4)
    assert build_rolling_profile(bars, datetime(2019, 3, 1, tzinfo=NY), atr=ATR) is None


# ---------------------------------------------------------------------------
# Node detection


def _shelf_profile():
    """A realistic profile: a thick shelf, a thin shelf, and ordinary levels.

    Eighty ticks of traded range so that a decile means something. Each bar
    covers one tick; the number of bars at a level sets that level's activity.
    """
    bars = []
    for day in range(4, 9):
        start = datetime(2019, 3, day, 10, 0, tzinfo=NY)
        minute = 0
        for tick in range(80):
            price = Decimal("100.00") + Decimal(tick) * Decimal("0.25")
            if 20 <= tick < 28:        # thick shelf around 105.00-107.00
                visits, volume = 12, "200"
            elif 48 <= tick < 56:      # thin shelf around 112.00-114.00
                visits, volume = 1, "5"
            else:                      # ordinary background
                visits, volume = 4, "60"
            for _ in range(visits):
                bars.append(
                    bar(
                        start + timedelta(minutes=minute + 1),
                        str(price),
                        str(price + Decimal("0.25")),
                        volume,
                    )
                )
                minute += 1
    return bars


def test_both_high_and_low_nodes_are_detected():
    bars = _shelf_profile()
    profile = build_rolling_profile(bars, bars[-1].close_time, atr=ATR)
    activity = rolling_activity(profile)
    assert activity.valid
    nodes = detect_nodes(profile, activity, min_width_ticks=2)
    classes = {n.node_class for n in nodes}
    assert HIGH_NODE in classes, "expected a high node at the thick shelf"
    assert LOW_NODE in classes, "expected a low node at the thin shelf"


def test_a_high_node_sits_where_activity_is_high_and_a_low_node_where_it_is_low():
    bars = _shelf_profile()
    profile = build_rolling_profile(bars, bars[-1].close_time, atr=ATR)
    activity = rolling_activity(profile)
    nodes = detect_nodes(profile, activity, min_width_ticks=2)
    highs = [n for n in nodes if n.node_class == HIGH_NODE]
    lows = [n for n in nodes if n.node_class == LOW_NODE]
    assert min(n.smoothed_activity for n in highs) > max(
        n.smoothed_activity for n in lows
    )
    assert min(n.activity_percentile for n in highs) >= Decimal("90.0")
    assert max(n.activity_percentile for n in lows) <= Decimal("10.0")


def test_nodes_outside_the_width_band_are_dropped_not_truncated():
    bars = _shelf_profile()
    profile = build_rolling_profile(bars, bars[-1].close_time, atr=ATR)
    activity = rolling_activity(profile)
    nodes = detect_nodes(profile, activity, min_width_ticks=2, max_width_ticks=3)
    for node in nodes:
        assert 2 <= node.width_ticks <= 3


def test_node_intervals_are_half_open_and_never_one_tick_by_default():
    bars = _shelf_profile()
    profile = build_rolling_profile(bars, bars[-1].close_time, atr=ATR)
    activity = rolling_activity(profile)
    nodes = detect_nodes(profile, activity)
    for node in nodes:
        assert node.node_high > node.node_low
        assert node.contains(node.node_low)
        assert not node.contains(node.node_high)
        assert node.width_ticks >= 3


# ---------------------------------------------------------------------------
# Tap validity


def _node():
    from hvn.rolling_profile import Node

    return Node(
        node_class=HIGH_NODE,
        low_index=400,
        high_index=411,
        node_low=Decimal("100.00"),
        node_high=Decimal("103.00"),
        peak_index=405,
        peak_price=Decimal("101.25"),
        smoothed_activity=Decimal("2"),
        activity_percentile=Decimal("95"),
        anchor_time=datetime(2019, 3, 4, 10, 0, tzinfo=NY),
    )


def _forward(rows):
    start = datetime(2019, 3, 4, 10, 0, tzinfo=NY)
    return [
        bar(start + timedelta(minutes=i + 1), low, high)
        for i, (low, high) in enumerate(rows)
    ]


def test_a_single_brush_is_not_a_tap():
    node = _node()
    forward = _forward([("103", "104"), ("110", "111"), ("110", "111")])
    tap = find_tap(
        forward, node, atr=ATR, max_distance_atr=Decimal("0.5"), min_bars_within=3
    )
    assert not tap.valid


def test_three_consecutive_bars_inside_the_band_qualify():
    node = _node()
    forward = _forward([("110", "111"), ("103", "104"), ("103", "104"), ("103", "104")])
    tap = find_tap(
        forward, node, atr=ATR, max_distance_atr=Decimal("0.5"), min_bars_within=3
    )
    assert tap.valid
    assert tap.first_index == 1
    assert tap.bars_within == 3


def test_the_run_resets_when_price_leaves_the_band():
    node = _node()
    forward = _forward(
        [("103", "104"), ("103", "104"), ("120", "121"), ("103", "104"), ("103", "104")]
    )
    tap = find_tap(
        forward, node, atr=ATR, max_distance_atr=Decimal("0.5"), min_bars_within=3
    )
    assert not tap.valid, "two runs of two must not be counted as one run of four"


def test_a_wider_band_admits_a_tap_the_tight_band_rejects():
    node = _node()
    forward = _forward([("105", "106")] * 3)
    tight = find_tap(
        forward, node, atr=ATR, max_distance_atr=Decimal("0.5"), min_bars_within=3
    )
    wide = find_tap(
        forward, node, atr=ATR, max_distance_atr=Decimal("1.5"), min_bars_within=3
    )
    assert not tight.valid and wide.valid


def test_the_closest_approach_is_recorded_even_when_no_tap_qualifies():
    node = _node()
    forward = _forward([("104", "105"), ("120", "121")])
    tap = find_tap(
        forward, node, atr=ATR, max_distance_atr=Decimal("0.1"), min_bars_within=3
    )
    assert not tap.valid
    assert tap.closest_distance_atr == Decimal("0.5")  # 104 is 1 point above 103
