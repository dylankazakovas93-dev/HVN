from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from .engine import TICK_SIZE
from .models import Bar

NY = ZoneInfo("America/New_York")


class Relationship(StrEnum):
    PRIOR_RTH_TO_ETH = "R01"
    PRIOR_RTH_TO_RTH = "R02"
    OVERNIGHT_TO_RTH = "R03"
    MIDNIGHT_TO_RTH = "R04"
    OPENING_HOUR_TO_RTH = "R05"


class ApproachSide(StrEnum):
    START_INSIDE = "START_INSIDE"
    BELOW = "APPROACH_FROM_BELOW"
    ABOVE = "APPROACH_FROM_ABOVE"


class TouchClass(StrEnum):
    START_INSIDE = "START_INSIDE"
    WICK_ONLY_SAME_SIDE = "WICK_ONLY_SAME_SIDE"
    CLOSE_INSIDE = "CLOSE_INSIDE"
    CROSS_THROUGH = "CROSS_THROUGH"


@dataclass(frozen=True, slots=True)
class Zone:
    zone_id: str
    low_ticks: int
    high_ticks: int

    def __post_init__(self) -> None:
        if self.low_ticks >= self.high_ticks:
            raise ValueError("zone must contain at least one tick")

    @property
    def low(self) -> Decimal:
        return Decimal(self.low_ticks) * TICK_SIZE

    @property
    def high(self) -> Decimal:
        return Decimal(self.high_ticks) * TICK_SIZE

    @property
    def center(self) -> Decimal:
        return (self.low + self.high) / Decimal(2)


@dataclass(frozen=True, slots=True)
class InteractionWindow:
    relationship: Relationship
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("interaction timestamps must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("interaction window must be nonempty")


@dataclass(frozen=True, slots=True)
class FirstInteraction:
    touched: bool
    eligible: bool
    exclusion_reason: str
    bar: Bar | None
    event_time: datetime | None
    approach_side: ApproachSide | None
    touch_class: TouchClass | None
    touched_during_prior_eth: bool | None = None


@dataclass(frozen=True, slots=True)
class PreTouchFeatures:
    touch_time: datetime
    minute_from_interaction_start: int
    minute_of_rth_or_eth: int
    approach_side: ApproachSide
    touch_class: TouchClass
    atr_1m_at_touch: Decimal
    zone_width_points: Decimal
    zone_width_atr: Decimal
    distance_from_interaction_open_to_zone_center_atr: Decimal
    distance_from_pre_touch_close_to_zone_edge_atr: Decimal | None
    absolute_15m_pre_touch_displacement_atr: Decimal | None
    signed_15m_pre_touch_displacement_atr: Decimal | None
    pre_touch_15m_close_path_efficiency: Decimal | None
    source_profile_range_atr: Decimal
    zone_distance_from_poc_atr: Decimal
    profile_age_minutes: int
    prior_eth_touch_flag: bool | None


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=NY)


def relationship_window(
    relationship: Relationship,
    *,
    source_date: date,
    interaction_date: date,
) -> InteractionWindow:
    if relationship == Relationship.PRIOR_RTH_TO_ETH:
        start, end = _at(source_date, 18), _at(interaction_date, 9, 30)
    elif relationship in {
        Relationship.PRIOR_RTH_TO_RTH,
        Relationship.OVERNIGHT_TO_RTH,
        Relationship.MIDNIGHT_TO_RTH,
    }:
        start, end = _at(interaction_date, 9, 30), _at(interaction_date, 16)
    elif relationship == Relationship.OPENING_HOUR_TO_RTH:
        start, end = _at(interaction_date, 10, 30), _at(interaction_date, 16)
    else:  # pragma: no cover - exhaustive StrEnum guard
        raise ValueError(f"unsupported relationship: {relationship}")
    return InteractionWindow(relationship, start, end)


def price_to_ticks(price: Decimal) -> int:
    ticks = price / TICK_SIZE
    integral = ticks.to_integral_value()
    if ticks != integral:
        raise ValueError(f"price {price} is not on the NQ tick grid")
    return int(integral)


def zone_from_prices(zone_id: str, low: Decimal, high: Decimal) -> Zone:
    return Zone(zone_id, price_to_ticks(low), price_to_ticks(high))


def bar_overlaps_zone(bar: Bar, zone: Zone) -> bool:
    low = price_to_ticks(bar.low)
    high = price_to_ticks(bar.high)
    return max(low, zone.low_ticks) <= min(high, zone.high_ticks - 1)


def close_inside(bar: Bar, zone: Zone) -> bool:
    close = price_to_ticks(bar.close)
    return zone.low_ticks <= close < zone.high_ticks


def _touch_class(bar: Bar, zone: Zone, side: ApproachSide) -> TouchClass:
    close = price_to_ticks(bar.close)
    if zone.low_ticks <= close < zone.high_ticks:
        return TouchClass.CLOSE_INSIDE
    if side == ApproachSide.BELOW:
        return (
            TouchClass.CROSS_THROUGH
            if close >= zone.high_ticks
            else TouchClass.WICK_ONLY_SAME_SIDE
        )
    return (
        TouchClass.CROSS_THROUGH
        if close < zone.low_ticks
        else TouchClass.WICK_ONLY_SAME_SIDE
    )


def find_first_interaction(
    bars: list[Bar] | tuple[Bar, ...],
    zone: Zone,
    window: InteractionWindow,
    *,
    source_contract: str,
    prior_eth_bars: list[Bar] | tuple[Bar, ...] = (),
) -> FirstInteraction:
    ordered = sorted(bars, key=lambda bar: (bar.close_time, bar.source_row_id))
    in_window = [
        bar
        for bar in ordered
        if window.start <= bar.start_time < window.end
    ]
    if not in_window:
        return FirstInteraction(False, False, "NO_INTERACTION_BARS", None, None, None, None)
    if any(bar.symbol != source_contract for bar in in_window):
        return FirstInteraction(False, False, "CONTRACT_TRANSITION", None, None, None, None)
    if len({(bar.symbol, bar.close_time) for bar in in_window}) != len(in_window):
        return FirstInteraction(False, False, "DUPLICATE_SYMBOL_TIMESTAMP", None, None, None, None)

    prior_touch = None
    if window.relationship == Relationship.PRIOR_RTH_TO_RTH:
        prior_touch = any(
            bar.symbol == source_contract and bar_overlaps_zone(bar, zone)
            for bar in prior_eth_bars
        )

    for index, bar in enumerate(in_window):
        if not bar_overlaps_zone(bar, zone):
            continue
        if index == 0:
            return FirstInteraction(
                True,
                True,
                "",
                bar,
                bar.close_time,
                ApproachSide.START_INSIDE,
                TouchClass.START_INSIDE,
                prior_touch,
            )
        previous = in_window[index - 1]
        if bar.start_time != previous.close_time:
            return FirstInteraction(
                False, False, "MISSING_PRE_TOUCH_BAR", None, None, None, None, prior_touch
            )
        previous_close = price_to_ticks(previous.close)
        if previous_close < zone.low_ticks:
            side = ApproachSide.BELOW
        elif previous_close >= zone.high_ticks:
            side = ApproachSide.ABOVE
        else:
            return FirstInteraction(
                False, False, "AMBIGUOUS_APPROACH", None, None, None, None, prior_touch
            )
        return FirstInteraction(
            True,
            True,
            "",
            bar,
            bar.close_time,
            side,
            _touch_class(bar, zone, side),
            prior_touch,
        )
    return FirstInteraction(False, True, "", None, None, None, None, prior_touch)


def complete_forward_bars(
    bars: list[Bar] | tuple[Bar, ...],
    *,
    touch_bar: Bar,
    window: InteractionWindow,
    horizon: int,
) -> tuple[tuple[Bar, ...], str]:
    if horizon < 1:
        raise ValueError("horizon must be positive")
    candidates = sorted(
        (
            bar
            for bar in bars
            if touch_bar.close_time <= bar.start_time < window.end
        ),
        key=lambda bar: (bar.close_time, bar.source_row_id),
    )
    if any(bar.symbol != touch_bar.symbol for bar in candidates[:horizon]):
        return (), "CONTRACT_TRANSITION"
    selected: list[Bar] = []
    expected_start = touch_bar.close_time
    for bar in candidates:
        if len(selected) == horizon:
            break
        if bar.start_time != expected_start:
            return (), "MISSING_BAR"
        selected.append(bar)
        expected_start = bar.close_time
    if len(selected) != horizon:
        return (), "WINDOW_END"
    return tuple(selected), ""


def pre_touch_features(
    bars: list[Bar] | tuple[Bar, ...],
    *,
    touch_bar: Bar,
    zone: Zone,
    window: InteractionWindow,
    interaction_open: Decimal,
    atr_at_touch: Decimal,
    source_profile_low: Decimal,
    source_profile_high: Decimal,
    poc_price: Decimal,
    profile_freeze_time: datetime,
    approach_side: ApproachSide,
    touch_class: TouchClass,
    prior_eth_touch_flag: bool | None,
) -> PreTouchFeatures:
    if atr_at_touch <= 0:
        raise ValueError("ATR at touch must be positive")
    if touch_bar.close_time <= profile_freeze_time:
        raise ValueError("interaction must occur strictly after profile freeze")
    width = zone.high - zone.low
    previous = sorted(
        (
            bar
            for bar in bars
            if bar.symbol == touch_bar.symbol and bar.close_time <= touch_bar.start_time
        ),
        key=lambda bar: (bar.close_time, bar.source_row_id),
    )
    pre_touch_close = previous[-1].close if previous else None
    edge_distance = None
    if pre_touch_close is not None and approach_side != ApproachSide.START_INSIDE:
        edge = zone.low if approach_side == ApproachSide.BELOW else zone.high
        edge_distance = abs(pre_touch_close - edge) / atr_at_touch

    displacement = absolute_displacement = efficiency = None
    if len(previous) >= 16:
        path = previous[-16:]
        expected = path[0].close_time
        consecutive = True
        for bar in path[1:]:
            expected += timedelta(minutes=1)
            if bar.close_time != expected:
                consecutive = False
                break
        if consecutive and path[-1].close_time == touch_bar.start_time:
            raw_displacement = path[-1].close - path[0].close
            displacement = raw_displacement / atr_at_touch
            absolute_displacement = abs(displacement)
            travelled = sum(
                (
                    abs(path[index].close - path[index - 1].close)
                    for index in range(1, len(path))
                ),
                Decimal(0),
            )
            efficiency = Decimal(0) if travelled == 0 else abs(raw_displacement) / travelled

    minute_from_start = int(
        (touch_bar.start_time - window.start).total_seconds() // 60
    )
    session_anchor = (
        touch_bar.start_time.replace(hour=9, minute=30, second=0, microsecond=0)
        if window.relationship != Relationship.PRIOR_RTH_TO_ETH
        else window.start
    )
    minute_of_session = int(
        (touch_bar.start_time - session_anchor).total_seconds() // 60
    )
    return PreTouchFeatures(
        touch_bar.close_time,
        minute_from_start,
        minute_of_session,
        approach_side,
        touch_class,
        atr_at_touch,
        width,
        width / atr_at_touch,
        abs(interaction_open - zone.center) / atr_at_touch,
        edge_distance,
        absolute_displacement,
        displacement,
        efficiency,
        (source_profile_high - source_profile_low) / atr_at_touch,
        abs(zone.center - poc_price) / atr_at_touch,
        int((touch_bar.close_time - profile_freeze_time).total_seconds() // 60),
        prior_eth_touch_flag,
    )
