"""Line the levels up: which prices several independent sources agree on.

A level is an interval with a source label. Confluence merges levels from
*different* sources whose intervals overlap once each is widened by a tolerance,
and the degree `k` of the resulting cluster is the count of distinct sources in
it. Two levels from the same source are one vote, always — otherwise a source
that happens to emit many levels would manufacture confluence by itself.

Tolerance is an axis, not a constant. Different constructions have no reason to
agree to the tick, and a tolerance chosen too tight would report "no confluence
exists" when the truth is that the levels cluster loosely. Because a wider
tolerance mechanically raises k, degree is only ever compared within a single
tolerance.

The barrier selection at the end is deliberately crude: the nearest cluster
above the prevailing price and the nearest below it. It needs no threshold, it
cannot be tuned, and it is the object a chart reader actually looks at.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

# Predeclared tolerances, in ATR. Never searched.
TOLERANCES_ATR = (Decimal("0.25"), Decimal("1.00"), Decimal("2.00"))

ABOVE = "ABOVE"
BELOW = "BELOW"


@dataclass(frozen=True, slots=True)
class Level:
    """One vote from one source, as a half-open price interval."""

    source: str
    kind: str
    low: Decimal
    high: Decimal
    detail: str = ""

    def widened(self, tolerance: Decimal) -> tuple[Decimal, Decimal]:
        return self.low - tolerance, self.high + tolerance


@dataclass(frozen=True, slots=True)
class Cluster:
    """A set of levels from distinct sources that agree on a price region."""

    low: Decimal
    high: Decimal
    degree: int
    sources: tuple[str, ...]
    kinds: tuple[str, ...]
    members: tuple[Level, ...]

    @property
    def midpoint(self) -> Decimal:
        return (self.low + self.high) / 2

    def contains(self, price: Decimal) -> bool:
        return self.low <= price < self.high


def cluster_levels(
    levels: list[Level] | tuple[Level, ...], *, tolerance: Decimal
) -> list[Cluster]:
    """Group overlapping levels into clusters, sorted by price.

    Sweep in price order and extend the open cluster while the next widened
    level still overlaps it. Chaining is accepted: A may reach C through B even
    when A and C do not touch. That merges slightly more aggressively than a
    strict pairwise rule, which understates confluence degree rather than
    inflating it, and understating is the safe direction for a test whose whole
    claim is that degree matters.

    The reported interval is the *unwidened* union of its members, so tolerance
    decides what groups together without silently inflating every barrier's
    width.
    """
    if not levels:
        return []
    ordered = sorted(levels, key=lambda level: (level.low, level.high, level.source))
    clusters: list[list[Level]] = []
    current: list[Level] = [ordered[0]]
    reach = ordered[0].widened(tolerance)[1]
    for level in ordered[1:]:
        low, high = level.widened(tolerance)
        if low <= reach:
            current.append(level)
            reach = max(reach, high)
        else:
            clusters.append(current)
            current = [level]
            reach = high
    clusters.append(current)

    out = []
    for members in clusters:
        sources = tuple(sorted({m.source for m in members}))
        out.append(
            Cluster(
                low=min(m.low for m in members),
                high=max(m.high for m in members),
                degree=len(sources),
                sources=sources,
                kinds=tuple(sorted({m.kind for m in members})),
                members=tuple(members),
            )
        )
    return out


def nearest_barriers(
    clusters: list[Cluster], price: Decimal
) -> dict[str, Cluster | None]:
    """The closest cluster above the price and the closest below it.

    A cluster containing the price is not a barrier in either direction — price
    is already inside it, so there is nothing to travel to. It is excluded from
    both sides rather than counted twice.
    """
    above = [c for c in clusters if c.low > price]
    below = [c for c in clusters if c.high <= price]
    return {
        ABOVE: min(above, key=lambda c: c.low - price) if above else None,
        BELOW: max(below, key=lambda c: c.high) if below else None,
    }


@dataclass(frozen=True, slots=True)
class LevelSet:
    """Every level visible at one anchor, with the causality claim recorded."""

    anchor_time: datetime
    levels: tuple[Level, ...]
    latest_bar_close: datetime | None

    def assert_causal(self) -> None:
        """No bar later than the anchor may have contributed to any level.

        Called by the runner at every anchor rather than trusted. Nine sources
        is nine chances to leak the future, and a single leak would produce a
        spectacular result that means nothing.
        """
        if self.latest_bar_close is not None and self.latest_bar_close > self.anchor_time:
            raise ValueError(
                f"lookahead: a bar closing {self.latest_bar_close.isoformat()} "
                f"contributed to levels anchored {self.anchor_time.isoformat()}"
            )
