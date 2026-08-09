"""Which instrument_id is the front-month outright, and is that claim defensible?

The one-second dataset carries numeric `instrument_id` values with no symbology.
Several IDs overlap at any moment, calendar spreads sit alongside outrights, and
the roll methodology is undocumented. This project cannot proceed on that: a
20-session composite profile spanning a roll would blend two contracts' price
levels and every node in it would be fiction.

The working proposal is the obvious one — **the front month is the highest-volume
instrument in a session** — and it is an *inference*, not a fact the data states.
So it is never used silently. `validate_selection` runs five checks that the
inference must survive; if any fails, the selection is reported as unverified and
the caller is expected to stop rather than proceed.

    1. tenure       a selected id holds for roughly a quarter, not days
    2. calendar     switches land near quarterly expiry, third Friday of
                    March, June, September, December
    3. sign         its prices are strictly positive
    4. dominance    it carries a large share of the session's volume
    5. continuity   the price gap across a roll is small relative to ATR

None of these prove the mapping. Together they make an incorrect mapping
unlikely to pass, which is the most an unlabelled dataset allows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

# Predeclared thresholds. Chosen from contract mechanics, not fitted.
MIN_DOMINANCE = Decimal("0.60")      # share of session volume
# A calendar spread quotes the *difference* between two outrights, so its price
# is a couple of hundred points where an outright is tens of thousands. Observed
# directly in June 2023: ids 3522 and 2130 closed at 14,922.75 and 15,106.75,
# and id 1584 closed at 184.70 — exactly their difference. Spreads are therefore
# not reliably negative, and a sign test alone does not exclude them.
MIN_PRICE_SHARE_OF_MAX = Decimal("0.50")
MIN_TENURE_DAYS = 45                 # a quarterly contract leads far longer
MAX_EXPIRY_DISTANCE_DAYS = 20        # switch should sit near the quarterly roll
MAX_ROLL_GAP_ATR = Decimal("5.0")    # a roll gap is a spread, not a dislocation
QUARTERLY_MONTHS = (3, 6, 9, 12)


@dataclass(frozen=True, slots=True)
class SessionChoice:
    """The winning instrument for one session, with the evidence behind it."""

    session_date: str
    instrument_id: int
    volume: int
    session_volume: int
    close_price: Decimal | None

    @property
    def dominance(self) -> Decimal:
        if not self.session_volume:
            return Decimal(0)
        return Decimal(self.volume) / Decimal(self.session_volume)


@dataclass(frozen=True, slots=True)
class SelectionReport:
    verified: bool
    failures: tuple[str, ...]
    sessions: int
    switches: int
    median_dominance: Decimal | None
    min_tenure_days: int | None
    worst_roll_gap_atr: Decimal | None


def choose_front_month(session_date: str, rows) -> SessionChoice | None:
    """Highest-volume instrument in the session.

    `rows` is an iterable of (instrument_id, volume, close_price). Spreads are
    excluded by price magnitude rather than by sign: a calendar spread quotes the
    difference between two outrights, which is positive far more often than not.
    """
    totals: dict[int, list] = {}
    for instrument_id, volume, close in rows:
        entry = totals.setdefault(int(instrument_id), [0, None])
        entry[0] += int(volume)
        if close is not None:
            entry[1] = Decimal(close)
    if not totals:
        return None
    priced = {
        key: value for key, value in totals.items()
        if value[1] is not None and value[1] > 0
    }
    if not priced:
        return None
    # Keep only instruments quoting at outright levels. A spread priced at a few
    # hundred cannot be confused with a contract priced in the thousands, and
    # this catches the positive-priced spreads that a sign test misses.
    ceiling = max(value[1] for value in priced.values())
    positive = {
        key: value for key, value in priced.items()
        if value[1] >= ceiling * MIN_PRICE_SHARE_OF_MAX
    }
    if not positive:
        return None
    # Dominance is measured against outright volume only. Spreads are not
    # competing contracts, and on a roll day their volume spikes; counting them
    # in the denominator would make a perfectly clean front month look thin.
    session_volume = sum(volume for volume, _ in positive.values())
    # Ties break on the lower id so the selection is deterministic.
    best = min(positive.items(), key=lambda item: (-item[1][0], item[0]))
    return SessionChoice(
        session_date=session_date,
        instrument_id=best[0],
        volume=best[1][0],
        session_volume=session_volume,
        close_price=best[1][1],
    )


def third_friday(year: int, month: int) -> date:
    day = date(year, month, 1)
    fridays = 0
    while True:
        if day.weekday() == 4:
            fridays += 1
            if fridays == 3:
                return day
        day += timedelta(days=1)


def _nearest_quarterly_expiry(when: date) -> date:
    candidates = []
    for year in (when.year - 1, when.year, when.year + 1):
        for month in QUARTERLY_MONTHS:
            candidates.append(third_friday(year, month))
    return min(candidates, key=lambda d: abs((d - when).days))


def validate_selection(
    choices: list[SessionChoice], *, atr_by_session: dict[str, Decimal] | None = None
) -> SelectionReport:
    """Run the five checks. Any failure means the mapping is not usable.

    A report is produced even when checks fail, because *which* check failed
    says what is wrong: a dominance failure suggests the wrong instrument, a
    calendar failure suggests the roll is not quarterly, a continuity failure
    suggests spreads leaked into the selection.
    """
    failures: list[str] = []
    if len(choices) < 2:
        return SelectionReport(False, ("insufficient_sessions",), len(choices),
                               0, None, None, None)

    ordered = sorted(choices, key=lambda c: c.session_date)
    dominances = sorted(c.dominance for c in ordered)
    median_dominance = dominances[len(dominances) // 2]
    if median_dominance < MIN_DOMINANCE:
        failures.append("dominance")

    runs: list[tuple[int, str, str]] = []
    start = ordered[0]
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current.instrument_id != previous.instrument_id:
            runs.append((previous.instrument_id, start.session_date, previous.session_date))
            start = current
    runs.append((ordered[-1].instrument_id, start.session_date, ordered[-1].session_date))

    tenures = [
        (date.fromisoformat(end) - date.fromisoformat(begin)).days + 1
        for _, begin, end in runs
    ]
    # The first and last runs are truncated by the window, so they are excluded
    # from the tenure test rather than counted as short.
    interior = tenures[1:-1] if len(tenures) > 2 else []
    min_tenure = min(interior) if interior else None
    if interior and min_tenure < MIN_TENURE_DAYS:
        failures.append("tenure")

    switches = 0
    for _, begin, _ in runs[1:]:
        switches += 1
        when = date.fromisoformat(begin)
        if abs((_nearest_quarterly_expiry(when) - when).days) > MAX_EXPIRY_DISTANCE_DAYS:
            failures.append("calendar")
            break

    if any(c.close_price is not None and c.close_price <= 0 for c in ordered):
        failures.append("sign")

    worst_gap: Decimal | None = None
    if atr_by_session:
        by_session = {c.session_date: c for c in ordered}
        for _, begin, _ in runs[1:]:
            current = by_session[begin]
            index = ordered.index(current)
            if index == 0:
                continue
            previous = ordered[index - 1]
            atr = atr_by_session.get(begin)
            if (
                atr is None
                or not atr
                or current.close_price is None
                or previous.close_price is None
            ):
                continue
            gap = abs(current.close_price - previous.close_price) / atr
            if worst_gap is None or gap > worst_gap:
                worst_gap = gap
        if worst_gap is not None and worst_gap > MAX_ROLL_GAP_ATR:
            failures.append("continuity")

    return SelectionReport(
        verified=not failures,
        failures=tuple(dict.fromkeys(failures)),
        sessions=len(ordered),
        switches=switches,
        median_dominance=median_dominance,
        min_tenure_days=min_tenure,
        worst_roll_gap_atr=worst_gap,
    )
