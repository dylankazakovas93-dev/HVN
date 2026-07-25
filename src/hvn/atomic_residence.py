"""Generation 3 residence metrics for atomic HVN proximity bands."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .atomic import AtomicHvn
from .atomic_proximity import BANDS
from .models import Bar

# Raw residence buckets, in minutes of continuous residence.
BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("B0", 0, 2),
    ("B1", 3, 5),
    ("B2", 6, 10),
    ("B3", 11, 20),
    ("B4", 21, None),
)


def residence_bucket(minutes: int) -> str:
    for name, low, high in BUCKETS:
        if minutes >= low and (high is None or minutes <= high):
            return name
    return BUCKETS[0][0]


@dataclass(frozen=True, slots=True)
class ResidenceResult:
    band: str
    total_minutes: int
    longest_run_minutes: int
    first_entry_minute: int | None
    first_exit_minute: int | None
    continuous_residence_minutes: int
    reentry_count: int
    first_reentry_delay_minutes: int | None
    never_entered: bool
    never_left: bool
    right_censored: bool
    residence_bucket: str
    normalized_residence: Decimal | None


def _runs(flags: list[bool]) -> list[tuple[int, int]]:
    """Contiguous (start_index, length) runs of True."""
    out, start = [], None
    for index, flag in enumerate(flags):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            out.append((start, index - start))
            start = None
    if start is not None:
        out.append((start, len(flags) - start))
    return out


def residence_metrics(
    atomic: AtomicHvn,
    forward_bars: tuple[Bar, ...],
    atr: Decimal,
) -> tuple[ResidenceResult, ...]:
    """Residence in every proximity band over the observed forward window.

    `continuous_residence_minutes` is the first unbroken run starting at the
    first entry, which is the quantity the departure analysis conditions on.
    `right_censored` marks a band still occupied at the end of the window.
    """
    results = []
    for name, expansion in BANDS:
        low, high = atomic.band(expansion, atr)
        inside = [low <= bar.close < high for bar in forward_bars]
        runs = _runs(inside)
        total = sum(inside)
        never_entered = not runs
        first_entry = runs[0][0] if runs else None
        continuous = runs[0][1] if runs else 0
        first_exit = (
            runs[0][0] + runs[0][1]
            if runs and runs[0][0] + runs[0][1] < len(inside)
            else None
        )
        never_left = bool(runs) and first_exit is None
        first_reentry_delay = (
            runs[1][0] - (runs[0][0] + runs[0][1]) if len(runs) > 1 else None
        )
        width = atomic.width_points
        results.append(
            ResidenceResult(
                band=name,
                total_minutes=total,
                longest_run_minutes=max((length for _, length in runs), default=0),
                first_entry_minute=first_entry,
                first_exit_minute=first_exit,
                continuous_residence_minutes=continuous,
                reentry_count=max(len(runs) - 1, 0),
                first_reentry_delay_minutes=first_reentry_delay,
                never_entered=never_entered,
                never_left=never_left,
                right_censored=bool(inside) and inside[-1],
                residence_bucket=residence_bucket(continuous),
                # Preserved historical statistic. Atomic zones are deliberately
                # narrow, so this ratio can become mechanically large and is
                # never the sole residence classification.
                normalized_residence=(
                    Decimal(continuous) * atr / width if width > 0 else None
                ),
            )
        )
    return tuple(results)
