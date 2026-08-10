"""Loose, medium and strict level definitions.

One tier is an arbitrary choice; three tiers ordered by selectivity is a test.
If levels carry information, the strict tier should carry more of it per level
than the loose one, and if it does not, that is an answer rather than a null
result about one threshold somebody picked.

**What the tiers are calibrated on.** Frequency, and nothing else. A tier is
tuned until it emits roughly the intended number of levels per session, and it
is frozen there before a single outcome is computed. Frequency is a property of
the levels themselves; whether they reverse price is the thing under test, and
touching the thresholds after seeing that would make the whole study worthless.

Intended frequency, across all nine sources at one anchor:

    loose    a cluttered chart; most of the profile is a level of some sort
    medium   a handful; roughly what a discretionary reader would mark up
    strict   rare; many anchors have no strict level near price at all

Every gate below is an interpretable quantity, not a fitted constant:

    percentile      rank of smoothed activity among ticks that actually traded
    activity        smoothed activity as a multiple of the profile's mean
    seconds share   time spent at a tick, as a fraction of the traded ticks
    band multiple   which VWAP and value-area bands count as levels at all

The tiers nest: every strict level is a medium level, and every medium level is
a loose one. That is what makes "more selective" mean something. It is asserted
in the tests rather than left as a comment.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

LOOSE = "LOOSE"
MEDIUM = "MEDIUM"
STRICT = "STRICT"
TIERS = (LOOSE, MEDIUM, STRICT)


@dataclass(frozen=True, slots=True)
class Tier:
    """One frozen level definition."""

    name: str
    # Node detection, against the smoothed activity profile.
    high_node_percentile: Decimal
    high_node_min_activity: Decimal
    low_node_percentile: Decimal
    low_node_max_activity: Decimal
    # Time-at-price: a level is a tick whose seconds sit in the bottom share.
    seconds_bottom_share: Decimal
    # Which band multiples are levels at this tier.
    sigma_multiples: tuple[Decimal, ...]
    vwap_sigma_multiples: tuple[Decimal, ...]
    vwap_percent_offsets: tuple[Decimal, ...]
    # Whether the softer, always-present kinds count at all.
    include_value_edges: bool
    include_poc: bool

    def admits(self, other: "Tier") -> bool:
        """Is every level of `other` also a level here? Used to assert nesting."""
        return (
            self.high_node_percentile <= other.high_node_percentile
            and self.high_node_min_activity <= other.high_node_min_activity
            and self.low_node_percentile >= other.low_node_percentile
            and self.low_node_max_activity >= other.low_node_max_activity
            and self.seconds_bottom_share >= other.seconds_bottom_share
            and set(other.sigma_multiples) <= set(self.sigma_multiples)
            and set(other.vwap_sigma_multiples) <= set(self.vwap_sigma_multiples)
            and set(other.vwap_percent_offsets) <= set(self.vwap_percent_offsets)
            and (self.include_value_edges or not other.include_value_edges)
            and (self.include_poc or not other.include_poc)
        )


TIER_SPECS = {
    LOOSE: Tier(
        name=LOOSE,
        high_node_percentile=Decimal("70"),
        high_node_min_activity=Decimal("1.15"),
        low_node_percentile=Decimal("30"),
        low_node_max_activity=Decimal("0.85"),
        seconds_bottom_share=Decimal("0.30"),
        sigma_multiples=(Decimal(1), Decimal(2), Decimal(3), Decimal(4)),
        vwap_sigma_multiples=(Decimal(1), Decimal(2), Decimal(3), Decimal(4)),
        vwap_percent_offsets=(
            Decimal("0.0025"), Decimal("0.0050"), Decimal("0.0100"), Decimal("0.0150"),
        ),
        include_value_edges=True,
        include_poc=True,
    ),
    MEDIUM: Tier(
        name=MEDIUM,
        high_node_percentile=Decimal("88"),
        high_node_min_activity=Decimal("1.35"),
        low_node_percentile=Decimal("12"),
        low_node_max_activity=Decimal("0.65"),
        seconds_bottom_share=Decimal("0.12"),
        sigma_multiples=(Decimal(2), Decimal(3), Decimal(4)),
        vwap_sigma_multiples=(Decimal(2), Decimal(3), Decimal(4)),
        vwap_percent_offsets=(Decimal("0.0150"),),
        include_value_edges=True,
        include_poc=True,
    ),
    STRICT: Tier(
        name=STRICT,
        high_node_percentile=Decimal("98"),
        high_node_min_activity=Decimal("1.80"),
        low_node_percentile=Decimal("2"),
        low_node_max_activity=Decimal("0.40"),
        seconds_bottom_share=Decimal("0.03"),
        sigma_multiples=(Decimal(4),),
        vwap_sigma_multiples=(Decimal(4),),
        vwap_percent_offsets=(),
        include_value_edges=False,
        include_poc=False,
    ),
}


def tier(name: str) -> Tier:
    try:
        return TIER_SPECS[name]
    except KeyError:
        raise ValueError(f"unknown tier {name!r}; expected one of {TIERS}") from None


__all__ = ["LOOSE", "MEDIUM", "STRICT", "TIERS", "TIER_SPECS", "Tier", "tier"]
