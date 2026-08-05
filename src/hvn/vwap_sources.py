"""Anchored VWAP with bands, four anchors and two band definitions.

A profile answers "where did volume sit". A VWAP band answers "how far is price
from where volume sat, measured in units of its own dispersion". Those are
different questions, and they disagree often enough that counting them as
separate votes in a confluence test is meaningful rather than double-counting.

    P6  globex     18:00 ET to the anchor
    P7  cash       09:30 ET to the anchor
    P8  prior RTH  the previous session's full cash VWAP, carried forward
    P9  rolling    the trailing 20 sessions

Bands, both computed on every source and reported side by side:

    sigma       1, 2, 3, 4 volume-weighted standard deviations
    percentage  0.25%, 0.50%, 1.00%, 1.50% of the VWAP

They are not redundant. A sigma band widens when the session is volatile and a
percentage band does not, so which one lines up better with the profile levels
is itself a result.

Everything here is causal: the VWAP and its dispersion at an hourly close use
only bars that closed at or before it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .models import Bar
from .profile_sources import (
    cash_developing_window,
    globex_developing_window,
    prior_rth_window,
)
from .rolling_profile import ROLLING_SESSIONS, session_date

P6_VWAP_GLOBEX = "P6_VWAP_GLOBEX"
P7_VWAP_CASH = "P7_VWAP_CASH"
P8_VWAP_PRIOR_RTH = "P8_VWAP_PRIOR_RTH"
P9_VWAP_ROLLING = "P9_VWAP_ROLLING"

SIGMA_MULTIPLES = (Decimal(1), Decimal(2), Decimal(3), Decimal(4))
PERCENT_OFFSETS = (
    Decimal("0.0025"),
    Decimal("0.0050"),
    Decimal("0.0100"),
    Decimal("0.0150"),
)

SIGMA_BANDS = "SIGMA"
PERCENT_BANDS = "PERCENT"


@dataclass(frozen=True, slots=True)
class AnchoredVwap:
    source: str
    anchor_time: datetime
    vwap: Decimal
    dispersion: Decimal
    bars_used: int


def rolling_vwap_window(bars, anchor: datetime, sessions: int = ROLLING_SESSIONS):
    """The trailing `sessions` completed sessions as of the anchor."""
    eligible = [b for b in bars if b.close_time <= anchor]
    if not eligible:
        return []
    dates = sorted({session_date(b.close_time) for b in eligible})
    keep = set(dates[-sessions:])
    return [b for b in eligible if session_date(b.close_time) in keep]


VWAP_WINDOWS = {
    P6_VWAP_GLOBEX: globex_developing_window,
    P7_VWAP_CASH: cash_developing_window,
    P8_VWAP_PRIOR_RTH: prior_rth_window,
    P9_VWAP_ROLLING: rolling_vwap_window,
}


def typical_price(bar: Bar) -> Decimal:
    """(high + low + close) / 3 — the conventional VWAP input from OHLCV."""
    return (bar.high + bar.low + bar.close) / Decimal(3)


def anchored_vwap(window: list[Bar], anchor: datetime, *, source: str):
    """Volume-weighted mean and volume-weighted standard deviation of price."""
    volume = sum((b.volume for b in window), Decimal(0))
    if not window or volume <= 0:
        return None
    mean = sum((typical_price(b) * b.volume for b in window), Decimal(0)) / volume
    variance = sum(
        ((typical_price(b) - mean) ** 2 * b.volume for b in window), Decimal(0)
    ) / volume
    return AnchoredVwap(
        source=source,
        anchor_time=anchor,
        vwap=mean,
        dispersion=variance.sqrt(),
        bars_used=len(window),
    )


def build_vwap(bars, anchor: datetime, *, source: str):
    """Anchored VWAP for one of P6-P9, or None when the window is empty."""
    return anchored_vwap(VWAP_WINDOWS[source](bars, anchor), anchor, source=source)


def band_levels(vwap: AnchoredVwap, *, definition: str) -> dict[str, Decimal]:
    """Band edges above and below, keyed by their multiple.

    Both definitions produce the same shape so downstream code never branches on
    which one it was handed.
    """
    out: dict[str, Decimal] = {"VWAP": vwap.vwap}
    if definition == SIGMA_BANDS:
        for multiple in SIGMA_MULTIPLES:
            offset = multiple * vwap.dispersion
            out[f"+{multiple}s"] = vwap.vwap + offset
            out[f"-{multiple}s"] = vwap.vwap - offset
    elif definition == PERCENT_BANDS:
        for fraction in PERCENT_OFFSETS:
            offset = vwap.vwap * fraction
            label = f"{fraction * 100:.2f}%"
            out[f"+{label}"] = vwap.vwap + offset
            out[f"-{label}"] = vwap.vwap - offset
    else:
        raise ValueError(f"unknown band definition {definition!r}")
    return out
