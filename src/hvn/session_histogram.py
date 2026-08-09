"""One histogram per session, so a profile never walks the raw bars again.

A volume profile is **additive over sessions**. That single fact is what makes
one-second data usable: stream a session's bars once, collapse them to a compact
`tick -> (volume, seconds)` map, and every profile downstream is a sum of those
maps. Building a 20-session composite then costs the same whether the underlying
data is one-minute or one-second, because the bar count never enters it.

The Stage 3-5 engine walked ~8,000 one-minute bars per anchor. At one second
that is ~1.6M bars per anchor, which neither fits in memory nor finishes. Summing
twenty histograms of a few thousand entries does.

Allocation across a bar's range is unchanged from earlier stages so results stay
comparable. It matters far less here: a one-second bar usually spans one to three
ticks, where a one-minute bar often spanned twenty, so the share of volume placed
by assumption rather than observation collapses.

`seconds` replaces the older TPO count. At one-second resolution the number of
bars touching a tick *is* the time spent there, which is what TPO was always
meant to approximate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

TICK_SIZE = Decimal("0.25")


def tick_index(price: Decimal) -> int:
    """Index of the tick containing `price`, on the fixed 0.25 grid."""
    return int((price / TICK_SIZE).to_integral_value(rounding="ROUND_FLOOR"))


@dataclass(slots=True)
class SessionHistogram:
    """Volume and seconds per tick for one session of one instrument."""

    session_date: str
    instrument_id: int
    volume: dict[int, Decimal] = field(default_factory=dict)
    seconds: dict[int, int] = field(default_factory=dict)
    bars: int = 0

    def add_bar(self, low: Decimal, high: Decimal, volume: Decimal) -> None:
        """Spread one bar's volume across the ticks its range intersects.

        Uniform allocation, as in every earlier stage. A bar touching a single
        tick contributes all of its volume there and carries no assumption at
        all, which is the common case at one-second resolution.
        """
        first = tick_index(low)
        last = tick_index(high)
        if last < first:
            first, last = last, first
        span = last - first + 1
        share = Decimal(volume) / Decimal(span)
        for index in range(first, last + 1):
            self.volume[index] = self.volume.get(index, Decimal(0)) + share
            self.seconds[index] = self.seconds.get(index, 0) + 1
        self.bars += 1

    @property
    def total_volume(self) -> Decimal:
        return sum(self.volume.values(), Decimal(0))

    @property
    def traded_ticks(self) -> int:
        return len(self.volume)

    def to_record(self) -> dict:
        """Compact, deterministic form for the on-disk cache."""
        return {
            "session_date": self.session_date,
            "instrument_id": self.instrument_id,
            "bars": self.bars,
            "ticks": sorted(self.volume),
            "volume": [str(self.volume[i]) for i in sorted(self.volume)],
            "seconds": [self.seconds[i] for i in sorted(self.volume)],
        }

    @classmethod
    def from_record(cls, record: dict) -> SessionHistogram:
        histogram = cls(
            session_date=record["session_date"],
            instrument_id=int(record["instrument_id"]),
            bars=int(record.get("bars", 0)),
        )
        for index, volume, seconds in zip(
            record["ticks"], record["volume"], record["seconds"], strict=True
        ):
            histogram.volume[int(index)] = Decimal(volume)
            histogram.seconds[int(index)] = int(seconds)
        return histogram


def build_session_histogram(session_date: str, instrument_id: int, bars) -> SessionHistogram:
    """Collapse an iterable of (low, high, volume) into one histogram."""
    histogram = SessionHistogram(session_date=session_date, instrument_id=instrument_id)
    for low, high, volume in bars:
        histogram.add_bar(Decimal(low), Decimal(high), Decimal(volume))
    return histogram


@dataclass(frozen=True, slots=True)
class CompositeProfile:
    """A summed profile over several sessions, on the same tick grid."""

    sessions: tuple[str, ...]
    volume: dict[int, Decimal]
    seconds: dict[int, int]
    low_index: int
    high_index: int

    @property
    def indices(self) -> range:
        return range(self.low_index, self.high_index + 1)

    def tick_low(self, index: int) -> Decimal:
        return Decimal(index) * TICK_SIZE

    def tick_high(self, index: int) -> Decimal:
        return self.tick_low(index) + TICK_SIZE


def combine(histograms: list[SessionHistogram] | tuple[SessionHistogram, ...]) -> CompositeProfile | None:
    """Sum histograms into one profile.

    Mixing instruments is refused rather than silently allowed: two contracts
    trade at different absolute prices, so a summed profile across a roll would
    place nodes at prices where nothing ever traded.
    """
    if not histograms:
        return None
    instruments = {h.instrument_id for h in histograms}
    if len(instruments) > 1:
        raise ValueError(
            f"refusing to combine histograms from multiple instruments: {sorted(instruments)}"
        )
    volume: dict[int, Decimal] = {}
    seconds: dict[int, int] = {}
    for histogram in histograms:
        for index, value in histogram.volume.items():
            volume[index] = volume.get(index, Decimal(0)) + value
        for index, value in histogram.seconds.items():
            seconds[index] = seconds.get(index, 0) + value
    if not volume:
        return None
    low, high = min(volume), max(volume)
    for index in range(low, high + 1):
        volume.setdefault(index, Decimal(0))
        seconds.setdefault(index, 0)
    return CompositeProfile(
        sessions=tuple(sorted({h.session_date for h in histograms})),
        volume=volume,
        seconds=seconds,
        low_index=low,
        high_index=high,
    )
