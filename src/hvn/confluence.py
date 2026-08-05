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

# A barrier wider than this is not a level. Tied to the 0.5 ATR tap band rather
# than fitted: a band six times the tap width cannot be interacted with in any
# way a chart reader would recognise as touching a level.
MAX_CLUSTER_WIDTH_ATR = Decimal("3.00")

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

    @property
    def midpoint(self) -> Decimal:
        return (self.low + self.high) / 2

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


def within(a: Level, b: Level, tolerance: Decimal) -> bool:
    """Do two levels agree, allowing a gap of at most `tolerance`?

    Tolerance is the gap between the intervals, not a margin added to each. If
    both were widened, a tolerance of 1 ATR would in fact merge levels 2 ATR
    apart, and the reported axis would mean twice what it says.
    """
    return a.low - tolerance < b.high and b.low - tolerance < a.high


def cluster_levels(
    levels: list[Level] | tuple[Level, ...],
    *,
    tolerance: Decimal,
    max_width: Decimal | None = None,
) -> list[Cluster]:
    """Group levels that all agree with each other, sorted by price.

    **Complete linkage.** A level joins a group only when its tolerance-widened
    interval overlaps that of *every* member already in it, not merely the
    nearest one. Chaining is impossible by construction.

    An earlier version used single linkage — A joins B, B joins C, so A and C
    end up together though they are nowhere near each other. With nine sources
    emitting hundreds of levels, widening each by a whole ATR made everything
    touch: barriers 130 ATR wide, and worse, a width that rose monotonically
    with degree. That is the one confound this study cannot tolerate, because
    degree is the axis under test. Single linkage is not an option here.

    `max_width` drops clusters wider than the given price span. A region wider
    than a few ATR is not a level a chart reader would draw, and it cannot be
    tapped meaningfully by a 0.5 ATR band.
    """
    if not levels:
        return []
    ordered = sorted(levels, key=lambda level: (level.low, level.high, level.source))
    groups: list[list[Level]] = []
    current: list[Level] = [ordered[0]]
    for level in ordered[1:]:
        # Complete linkage: it must agree with every member already in the
        # group, not merely with the one nearest it. That single condition is
        # what makes chaining impossible.
        if all(within(level, member, tolerance) for member in current):
            current.append(level)
        else:
            groups.append(current)
            current = [level]
    groups.append(current)

    out = []
    for members in groups:
        low = min(m.low for m in members)
        high = max(m.high for m in members)
        if max_width is not None and high - low > max_width:
            continue
        sources = tuple(sorted({m.source for m in members}))
        out.append(
            Cluster(
                low=low,
                high=high,
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
