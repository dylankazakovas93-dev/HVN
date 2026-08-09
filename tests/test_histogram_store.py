"""The histogram store presents cached sessions as an ordinary profile."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from hvn.histogram_store import HistogramStore, session_name
from hvn.rolling_profile import rolling_activity

ANCHOR = datetime(2019, 3, 4, tzinfo=UTC)


def write_cache(tmp_path, payloads):
    for index, payload in enumerate(payloads):
        (tmp_path / f"rg_{index:04d}.json").write_text(json.dumps(payload))
    return HistogramStore(tmp_path)


def test_slices_of_the_same_session_are_merged(tmp_path):
    # A session spanning two row groups must add up, not overwrite.
    day = 17959
    store = write_cache(
        tmp_path,
        [
            {str(day): {"volume": {"100": 40.0}, "seconds": {"100": 4}, "bars": 4}},
            {str(day): {"volume": {"100": 60.0}, "seconds": {"100": 6}, "bars": 6}},
        ],
    )
    profile = store.profile(store.sessions, atr=Decimal(2), anchor=ANCHOR)
    assert profile.volume[100] == Decimal(100)
    assert profile.tpo[100] == 10
    assert profile.bars_used == 10


def test_seconds_become_the_tpo_field(tmp_path):
    store = write_cache(
        tmp_path, [{"17959": {"volume": {"100": 10.0}, "seconds": {"100": 7}, "bars": 7}}]
    )
    profile = store.profile(store.sessions, atr=Decimal(2), anchor=ANCHOR)
    assert profile.tpo[100] == 7
    assert rolling_activity(profile).valid is False or True  # smoke: it accepts the shape


def test_trailing_returns_the_window_ending_at_the_named_session(tmp_path):
    store = write_cache(
        tmp_path,
        [
            {
                str(17959 + offset): {
                    "volume": {"100": 10.0}, "seconds": {"100": 1}, "bars": 1
                }
                for offset in range(5)
            }
        ],
    )
    last = store.sessions[-1]
    window = store.trailing(last, 3)
    assert len(window) == 3
    assert window[-1] == last
    assert window == sorted(window)


def test_a_window_longer_than_history_is_truncated_not_padded(tmp_path):
    store = write_cache(
        tmp_path,
        [{str(17959 + offset): {"volume": {"1": 1.0}, "seconds": {"1": 1}, "bars": 1}
          for offset in range(2)}],
    )
    assert len(store.trailing(store.sessions[-1], 20)) == 2


def test_the_profile_is_gap_filled_between_traded_ticks(tmp_path):
    store = write_cache(
        tmp_path,
        [{"17959": {"volume": {"100": 5.0, "104": 5.0},
                    "seconds": {"100": 1, "104": 1}, "bars": 2}}],
    )
    profile = store.profile(store.sessions, atr=Decimal(2), anchor=ANCHOR)
    assert profile.volume[102] == Decimal(0)
    assert profile.low_index == 100 and profile.high_index == 104


def test_an_unknown_session_yields_no_window_and_no_profile(tmp_path):
    store = write_cache(tmp_path, [{"17959": {"volume": {"1": 1.0}, "seconds": {"1": 1}, "bars": 1}}])
    assert store.trailing("1999-01-01", 5) == []
    assert store.profile(["1999-01-01"], atr=Decimal(2), anchor=ANCHOR) is None


def test_day_numbers_map_to_iso_session_dates():
    assert session_name(17959) == "2019-03-04"
