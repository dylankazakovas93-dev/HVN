"""Stage 7: the race, the tiers, and the bucket cache."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hvn.bucket_histogram import (
    NANOS_PER_BUCKET,
    BucketStore,
    bucket_of,
    session_of_bucket,
)
from hvn.confluence import ABOVE, BELOW
from hvn.models import Bar
from hvn.race import ADVERSE, AMBIGUOUS, CENSORED, FAVOURABLE, race
from hvn.stage7_levels import bucket_index, seconds_extremes, source_windows
from hvn.tiers import LOOSE, MEDIUM, STRICT, tier


def bar(low, high, close=None):
    return Bar(
        source_row_id="x",
        close_time=datetime(2024, 1, 2, tzinfo=UTC),
        open=Decimal(low),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close if close is not None else high),
        volume=Decimal(1),
        symbol="NQ",
    )


# --------------------------------------------------------------------------
# The race


def test_favourable_first_when_price_returns():
    forward = [bar(99, 100), bar(97, 99), bar(94, 96)]
    result = race(
        forward, reference=Decimal(100), direction=ABOVE, atr=Decimal(2),
        distance=Decimal(1),
    )
    assert result.outcome == FAVOURABLE
    assert result.bars == 1


def test_adverse_first_when_price_carries_through():
    forward = [bar(100, 101), bar(101, 103)]
    result = race(
        forward, reference=Decimal(100), direction=ABOVE, atr=Decimal(2),
        distance=Decimal(1),
    )
    assert result.outcome == ADVERSE


def test_both_brackets_in_one_bar_is_ambiguous_not_guessed():
    """OHLC does not order two touches inside one bar, so neither is claimed."""
    forward = [bar(90, 110)]
    result = race(
        forward, reference=Decimal(100), direction=ABOVE, atr=Decimal(2),
        distance=Decimal(1),
    )
    assert result.outcome == AMBIGUOUS


def test_unreached_brackets_are_censored_not_scored():
    forward = [bar(99, 101) for _ in range(50)]
    result = race(
        forward, reference=Decimal(100), direction=ABOVE, atr=Decimal(2),
        distance=Decimal(3),
    )
    assert result.outcome == CENSORED
    assert result.bars is None


def test_below_barrier_mirrors_above():
    """Price arrived from above, so favourable is up."""
    forward = [bar(101, 103)]
    result = race(
        forward, reference=Decimal(100), direction=BELOW, atr=Decimal(2),
        distance=Decimal(1),
    )
    assert result.outcome == FAVOURABLE


def test_outcome_does_not_depend_on_band_width():
    """The reference is the touch price, so a wide barrier gets no head start.

    This is the failure that invalidated the Stage 5 and 6 reversal rates: an
    edge-referenced test scored a 3-ATR-wide barrier as reversing 74.8% of the
    time against 53.7% for a narrow one, on geometry alone.
    """
    forward = [bar(99, 101), bar(96, 99)]
    outcomes = {
        race(
            forward, reference=Decimal(100), direction=ABOVE, atr=Decimal(2),
            distance=Decimal(1),
        ).outcome
    }
    assert outcomes == {FAVOURABLE}


# --------------------------------------------------------------------------
# Tiers


def test_tiers_nest_from_loose_to_strict():
    """Every strict level is a medium level; every medium level is loose."""
    assert tier(LOOSE).admits(tier(MEDIUM))
    assert tier(MEDIUM).admits(tier(STRICT))
    assert tier(LOOSE).admits(tier(STRICT))


def test_strict_does_not_admit_loose():
    assert not tier(STRICT).admits(tier(LOOSE))


def test_unknown_tier_is_refused():
    with pytest.raises(ValueError):
        tier("VERY_STRICT")


# --------------------------------------------------------------------------
# Buckets


class FakeProfile:
    def __init__(self, counts):
        self.tpo = counts
        self.low_index = min(counts)
        self.high_index = max(counts)

    @property
    def indices(self):
        return range(self.low_index, self.high_index + 1)

    def tick_low(self, index):
        return Decimal(index) / 4

    def tick_high(self, index):
        return self.tick_low(index) + Decimal("0.25")


def test_seconds_extremes_are_nested_by_share():
    """A tighter share selects a subset, and always fewer ticks."""
    counts = {i: 100 + i for i in range(100)}
    for i in range(40, 60):  # a genuinely thin shelf
        counts[i] = i - 39
    strict = seconds_extremes(FakeProfile(counts), share=Decimal("0.05"))
    loose = seconds_extremes(FakeProfile(counts), share=Decimal("0.30"))
    assert strict and loose
    covered = lambda runs: sum(high - low for low, high in runs)  # noqa: E731
    assert covered(strict) < covered(loose)
    for low, high in strict:
        assert any(a <= low and high <= b for a, b in loose)


def test_seconds_share_is_a_count_cap_not_a_value_cut():
    """Ties at the thin end must not drag in the whole tail.

    Taking every tick at or below the share-quantile *value* admitted hundreds
    of tied ticks, and the strict tier emitted as many time-at-price levels as
    the loose one — 34 against 36 — which would have made the tier axis a
    label rather than a test.
    """
    counts = dict.fromkeys(range(100), 1)  # every tick tied at the minimum
    strict = seconds_extremes(FakeProfile(counts), share=Decimal("0.05"))
    loose = seconds_extremes(FakeProfile(counts), share=Decimal("0.50"))
    assert sum(high - low for low, high in strict) < sum(
        high - low for low, high in loose
    )


def write_cache(folder, payload):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "rg_0000.json").write_text(json.dumps(payload))


def test_store_merges_slices_and_sums_moments(tmp_path):
    """VWAP from summed moments equals VWAP computed directly."""
    bucket = bucket_of(int(datetime(2024, 1, 2, 15, 0, tzinfo=UTC).timestamp()) * 10**9)
    write_cache(
        tmp_path / "cache",
        {
            str(bucket): {
                "v": {"100": 10.0},
                "s": {"100": 5},
                "n": 5,
                # two prints: 100 at volume 3, 102 at volume 7
                "vol": 10.0,
                "pv": 3 * 100.0 + 7 * 102.0,
                "p2v": 3 * 100.0**2 + 7 * 102.0**2,
            }
        },
    )
    store = BucketStore(tmp_path / "cache", archive=tmp_path / "missing.tar.gz")
    mean, dispersion, bars = store.moments([bucket])
    assert bars == 5
    assert mean == pytest.approx(Decimal("101.4"), abs=Decimal("0.001"))
    expected = (3 * (100 - 101.4) ** 2 + 7 * (102 - 101.4) ** 2) / 10
    assert float(dispersion) == pytest.approx(expected**0.5, abs=1e-6)


def test_store_is_empty_without_a_cache(tmp_path):
    store = BucketStore(tmp_path / "cache", archive=tmp_path / "missing.tar.gz")
    assert store.sessions == []


def test_session_roll_puts_evening_trade_in_the_next_session():
    """17:00 Chicago starts the next session; a UTC-day key splits it in two."""
    evening = datetime(2024, 1, 2, 23, 30, tzinfo=UTC)  # 17:30 Chicago
    afternoon = datetime(2024, 1, 2, 20, 0, tzinfo=UTC)  # 14:00 Chicago
    assert session_of_bucket(bucket_index(evening)) == "2024-01-03"
    assert session_of_bucket(bucket_index(afternoon)) == "2024-01-02"


def test_bucket_index_is_thirty_minutes():
    start = datetime(2024, 1, 2, 14, 0, tzinfo=UTC)
    half = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    assert bucket_index(half) - bucket_index(start) == 1
    assert NANOS_PER_BUCKET == 30 * 60 * 10**9


def test_every_source_window_ends_strictly_before_the_anchor(tmp_path):
    """No bucket whose half hour is still open may feed a level."""
    session = "2024-01-03"
    anchor = datetime(2024, 1, 3, 15, 0, tzinfo=UTC)
    payload = {}
    first = bucket_index(datetime(2024, 1, 2, 23, 0, tzinfo=UTC))
    for offset in range(40):
        payload[str(first + offset)] = {
            "v": {"100": 1.0}, "s": {"100": 1}, "n": 1,
            "vol": 1.0, "pv": 100.0, "p2v": 10000.0,
        }
    write_cache(tmp_path / "cache", payload)
    store = BucketStore(tmp_path / "cache", archive=tmp_path / "missing.tar.gz")
    windows = source_windows(store, session, anchor)
    limit = bucket_index(anchor)
    for source, buckets in windows.items():
        assert all(b < limit for b in buckets), source


# --------------------------------------------------------------------------
# Range reads


class FlakyResponse:
    def __init__(self, body: bytes, total: int):
        self.content = body
        self.headers = {"Content-Range": f"bytes 0-{len(body) - 1}/{total}"}

    def raise_for_status(self):
        return None


class FlakySession:
    """Fails `failures` times, then serves the bytes."""

    calls = 0
    failures = 0
    total = 1000

    def __init__(self):
        pass

    def get(self, url, headers=None, timeout=None):
        type(self).calls += 1
        if type(self).calls <= type(self).failures:
            import requests

            raise requests.exceptions.ConnectionError("reset by peer")
        return FlakyResponse(b"x", type(self).total)

    def close(self):
        return None


def test_range_read_retries_a_dropped_connection(monkeypatch):
    """One reset connection must not end a scan that runs for hours."""
    import requests

    from hvn import range_reader

    FlakySession.calls = 0
    FlakySession.failures = 3
    monkeypatch.setattr(requests, "Session", FlakySession)
    monkeypatch.setattr(range_reader.time, "sleep", lambda _: None)

    reader = range_reader.HTTPRangeReader("https://example.invalid/f.parquet")
    assert reader.size == 1000
    assert FlakySession.calls == 4


def test_range_read_gives_up_after_the_retry_budget(monkeypatch):
    """A host that is genuinely gone still stops the run."""
    import requests

    from hvn import range_reader

    FlakySession.calls = 0
    FlakySession.failures = 99
    monkeypatch.setattr(requests, "Session", FlakySession)
    monkeypatch.setattr(range_reader.time, "sleep", lambda _: None)

    with pytest.raises(requests.exceptions.ConnectionError):
        range_reader.HTTPRangeReader("https://example.invalid/f.parquet")
    assert FlakySession.calls == range_reader.RETRIES


# --------------------------------------------------------------------------
# Excursion and the bracket grid


def test_bracket_grid_records_the_bar_each_distance_is_first_reached():
    from decimal import Decimal as D

    from hvn.race import excursion_and_brackets

    forward = [bar(99, 101), bar(97, 100), bar(94, 98)]
    result = excursion_and_brackets(
        forward, reference=D(100), direction=ABOVE, atr=D(2), grid=(D(1), D(3)),
    )
    # Favourable is down from 100: bar 1 reaches 97 (1.5 ATR), bar 2 reaches 94 (3 ATR).
    assert result["favourable_bar"]["1"] == 1
    assert result["favourable_bar"]["3"] == 2
    assert result["mfe_atr"] == pytest.approx(3.0)
    # Adverse never gets 1 ATR above 100 (high of 101 is 0.5 ATR).
    assert result["adverse_bar"]["1"] is None
    assert result["mae_atr"] == pytest.approx(0.5)


def test_unreached_bracket_is_none_not_the_last_bar():
    """Censored must stay distinguishable from resolved-at-the-deadline."""
    from decimal import Decimal as D

    from hvn.race import excursion_and_brackets

    forward = [bar(99, 101) for _ in range(20)]
    result = excursion_and_brackets(
        forward, reference=D(100), direction=ABOVE, atr=D(2), grid=(D(5),),
    )
    assert result["favourable_bar"]["5"] is None
    assert result["adverse_bar"]["5"] is None


def test_asymmetric_pair_is_derivable_from_the_grid():
    """A 3 ATR target against a 1 ATR stop, reconstructed without a re-scan."""
    from decimal import Decimal as D

    from hvn.race import excursion_and_brackets

    forward = [bar(99, 101), bar(97, 100), bar(94, 98)]
    grid = excursion_and_brackets(
        forward, reference=D(100), direction=ABOVE, atr=D(2), grid=(D(1), D(3)),
    )
    target = grid["favourable_bar"]["3"]
    stop = grid["adverse_bar"]["1"]
    assert target is not None and stop is None  # target hit, stop never touched


def test_bracket_mirror_cancels_the_censoring_bias():
    """Symmetric events must show no edge, however censored the cell is.

    Raw expectancy does not have this property: dropping unresolved events
    favours the near side, and on synthetic noise a 1 ATR target against a
    4 ATR stop read +0.66 ATR at 93% target-first. The mirror removes it,
    because the censoring is identical in both directions.
    """
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "scripts"))
    from excursion_stage07 import bracket_cell

    # Perfectly symmetric: every event is present alongside its swapped twin,
    # so the mirrored population is identical to the real one by construction.
    # Both grid keys must exist on both sides, because the mirror reads the
    # target off the adverse dict and the stop off the favourable one.
    events = []
    for index in range(400):
        favourable = {"1.0": index % 7, "4.0": None if index % 3 else index % 11}
        adverse = {"1.0": index % 5, "4.0": None if index % 4 else index % 9}
        events.append({"favourable_bar": favourable, "adverse_bar": adverse})
        events.append({"favourable_bar": adverse, "adverse_bar": favourable})
    cell = bracket_cell(events, "1.0", "4.0")
    assert cell is not None
    assert cell["edge_pp"] == pytest.approx(0.0, abs=1e-9)
    assert cell["expectancy_edge_atr"] == pytest.approx(0.0, abs=1e-9)
