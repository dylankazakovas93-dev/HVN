from __future__ import annotations

from decimal import Decimal

from .models import AtrPoint, Bar


def wilder_atr(bars: list[Bar] | tuple[Bar, ...], period: int = 24) -> tuple[AtrPoint, ...]:
    """Return ATR points available at each contributing bar's close."""
    if period < 1:
        raise ValueError("period must be positive")
    ordered = sorted(bars, key=lambda b: (b.close_time, b.source_row_id))
    if len({b.source_row_id for b in ordered}) != len(ordered):
        raise ValueError("duplicate source_row_id")
    symbols = {b.symbol for b in ordered}
    if len(symbols) > 1:
        raise ValueError("Wilder ATR requires exactly one contract symbol")
    timestamp_keys = [(b.close_time, b.symbol) for b in ordered]
    if len(set(timestamp_keys)) != len(timestamp_keys):
        raise ValueError("duplicate symbol timestamp in ATR input")
    trs: list[Decimal] = []
    out: list[AtrPoint] = []
    previous_close: Decimal | None = None
    atr: Decimal | None = None
    p = Decimal(period)
    for bar in ordered:
        tr = bar.high - bar.low
        if previous_close is not None:
            tr = max(tr, abs(bar.high - previous_close), abs(bar.low - previous_close))
        trs.append(tr)
        if len(trs) == period:
            atr = sum(trs, Decimal(0)) / p
            out.append(AtrPoint(bar.close_time, atr))
        elif len(trs) > period:
            assert atr is not None
            atr = ((atr * Decimal(period - 1)) + tr) / p
            out.append(AtrPoint(bar.close_time, atr))
        previous_close = bar.close
    return tuple(out)


def atr_before(points: tuple[AtrPoint, ...], source_start) -> AtrPoint:
    eligible = [point for point in points if point.available_time <= source_start]
    if not eligible:
        raise ValueError("insufficient completed ATR warm-up before source_start")
    return max(eligible, key=lambda point: point.available_time)
