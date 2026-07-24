from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import ProfileFamily, ProfileWindow

NEW_YORK = ZoneInfo("America/New_York")


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=NEW_YORK)


def profile_window(family: ProfileFamily, session_date: date) -> ProfileWindow:
    """Build a window from an explicitly selected source/anchor session date.

    PRIOR_RTH takes the actual prior RTH source date; the other families take
    the current RTH date. Holiday/session selection belongs upstream.
    """
    if family == ProfileFamily.PRIOR_RTH:
        start, end = _at(session_date, 9, 30), _at(session_date, 16)
    elif family == ProfileFamily.FULL_OVERNIGHT:
        start, end = _at(session_date - timedelta(days=1), 18), _at(session_date, 9, 30)
    elif family == ProfileFamily.MIDNIGHT:
        start, end = _at(session_date, 0), _at(session_date, 9, 30)
    elif family == ProfileFamily.OPENING_HOUR:
        start, end = _at(session_date, 9, 30), _at(session_date, 10, 30)
    else:
        raise ValueError(f"unsupported profile family: {family}")
    return ProfileWindow(family, session_date.isoformat(), start, end, end)
