"""Session histograms: additivity, allocation, and the roll refusal."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hvn.contract_selection import (
    SessionChoice,
    choose_front_month,
    third_friday,
    validate_selection,
)
from hvn.session_histogram import (
    SessionHistogram,
    build_session_histogram,
    combine,
    tick_index,
)


# ---------------------------------------------------------------------------
# Allocation


def test_a_bar_inside_one_tick_carries_no_allocation_assumption():
    histogram = SessionHistogram("2019-03-04", 1)
    histogram.add_bar(Decimal("100.00"), Decimal("100.20"), Decimal(500))
    assert len(histogram.volume) == 1
    assert histogram.volume[tick_index(Decimal("100.00"))] == Decimal(500)


def test_a_wider_bar_spreads_uniformly_across_its_ticks():
    histogram = SessionHistogram("2019-03-04", 1)
    histogram.add_bar(Decimal("100.00"), Decimal("100.75"), Decimal(400))
    assert len(histogram.volume) == 4
    assert set(histogram.volume.values()) == {Decimal(100)}


def test_seconds_count_every_bar_touching_a_tick():
    histogram = SessionHistogram("2019-03-04", 1)
    for _ in range(5):
        histogram.add_bar(Decimal("100.00"), Decimal("100.00"), Decimal(10))
    index = tick_index(Decimal("100.00"))
    assert histogram.seconds[index] == 5
    assert histogram.bars == 5


def test_total_volume_is_preserved_by_allocation():
    histogram = build_session_histogram(
        "2019-03-04", 1,
        [("100.00", "100.75", 400), ("101.00", "101.00", 250)],
    )
    assert histogram.total_volume == Decimal(650)


# ---------------------------------------------------------------------------
# Additivity is the whole point


def test_combining_sessions_sums_volume_tick_by_tick():
    one = build_session_histogram("2019-03-04", 1, [("100.00", "100.00", 100)])
    two = build_session_histogram("2019-03-05", 1, [("100.00", "100.00", 250)])
    profile = combine([one, two])
    assert profile.volume[tick_index(Decimal("100.00"))] == Decimal(350)
    assert profile.sessions == ("2019-03-04", "2019-03-05")


def test_a_combined_profile_is_gap_filled_across_its_range():
    one = build_session_histogram("2019-03-04", 1, [("100.00", "100.00", 100)])
    two = build_session_histogram("2019-03-05", 1, [("102.00", "102.00", 100)])
    profile = combine([one, two])
    # Every tick between the two prices exists, with zero volume.
    assert profile.volume[tick_index(Decimal("101.00"))] == Decimal(0)
    assert len(profile.volume) == 9


def test_combining_two_contracts_is_refused_not_silently_allowed():
    front = build_session_histogram("2019-03-04", 1, [("100.00", "100.00", 100)])
    back = build_session_histogram("2019-03-05", 2, [("140.00", "140.00", 100)])
    with pytest.raises(ValueError, match="multiple instruments"):
        combine([front, back])


def test_a_histogram_round_trips_through_its_record_form():
    original = build_session_histogram(
        "2019-03-04", 7, [("100.00", "100.50", 300), ("100.25", "100.25", 60)]
    )
    restored = SessionHistogram.from_record(original.to_record())
    assert restored.volume == original.volume
    assert restored.seconds == original.seconds
    assert restored.instrument_id == 7


# ---------------------------------------------------------------------------
# Front-month selection


def test_the_highest_volume_positive_instrument_wins():
    choice = choose_front_month(
        "2019-03-04",
        [(1, 1000, "12000.00"), (2, 250, "12010.00"), (3, 40, "12020.00")],
    )
    assert choice.instrument_id == 1
    assert choice.dominance > Decimal("0.75")


def test_a_negatively_priced_instrument_is_never_selected():
    # A spread can out-volume an outright on a roll day; it must still lose.
    choice = choose_front_month(
        "2019-03-04", [(9, 5000, "-3.50"), (1, 900, "12000.00")]
    )
    assert choice.instrument_id == 1


def test_a_session_with_no_positive_instrument_yields_no_choice():
    assert choose_front_month("2019-03-04", [(9, 100, "-3.50")]) is None


def test_the_third_friday_is_found_correctly():
    assert third_friday(2019, 3) == __import__("datetime").date(2019, 3, 15)
    assert third_friday(2019, 12) == __import__("datetime").date(2019, 12, 20)


# ---------------------------------------------------------------------------
# Validation must fail loudly on a bad mapping


def _run(instrument, start_day, days, dominance=Decimal("0.9"), price="12000"):
    from datetime import date, timedelta

    out = []
    for offset in range(days):
        day = (date.fromisoformat(start_day) + timedelta(days=offset)).isoformat()
        out.append(
            SessionChoice(day, instrument, int(900 * dominance), 900, Decimal(price))
        )
    return out


def test_a_clean_quarterly_pattern_verifies():
    choices = (
        _run(1, "2018-12-21", 84)      # Dec expiry to Mar expiry
        + _run(2, "2019-03-15", 92)
        + _run(3, "2019-06-15", 60)
    )
    report = validate_selection(choices)
    assert report.verified, report.failures
    assert report.switches == 2


def test_switching_every_few_days_fails_the_tenure_check():
    choices = []
    for index in range(10):
        from datetime import date, timedelta

        day = (date.fromisoformat("2019-01-01") + timedelta(days=index * 5)).isoformat()
        choices += _run(index, day, 5)
    report = validate_selection(choices)
    assert not report.verified
    assert "tenure" in report.failures


def test_a_thin_selection_fails_the_dominance_check():
    choices = _run(1, "2018-12-21", 84, dominance=Decimal("0.2")) + _run(
        2, "2019-03-15", 92, dominance=Decimal("0.2")
    )
    report = validate_selection(choices)
    assert not report.verified
    assert "dominance" in report.failures


def test_a_roll_that_jumps_the_price_fails_continuity():
    choices = _run(1, "2018-12-21", 84, price="12000") + _run(
        2, "2019-03-15", 92, price="12500"
    )
    atr = {c.session_date: Decimal("10") for c in choices}
    report = validate_selection(choices, atr_by_session=atr)
    assert not report.verified
    assert "continuity" in report.failures


def test_a_small_roll_gap_passes_continuity():
    choices = _run(1, "2018-12-21", 84, price="12000") + _run(
        2, "2019-03-15", 92, price="12030"
    )
    atr = {c.session_date: Decimal("10") for c in choices}
    report = validate_selection(choices, atr_by_session=atr)
    assert report.verified, report.failures
