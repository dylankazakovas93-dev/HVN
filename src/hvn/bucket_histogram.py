"""Half-hour histograms, so every profile source reads one-second data.

Stage 6 cached one histogram per session. That was enough for the trailing
composite and nothing else, so the hourly VP, the developing profiles, the prior
RTH and the four VWAPs all fell back to one-minute bars with volume smeared
uniformly across each bar's range. Eight of the nine sources never saw the
one-second file, which made the whole comparison meaningless.

The fix is granularity, not a new detector. Bucketing at **thirty minutes**
makes every window this project uses an exact sum of buckets:

    composite            trailing 20 sessions up to the anchor
    single hour          two buckets
    globex developing    18:00 ET to the anchor
    cash developing      09:30 ET to the anchor   <- needs the half hour
    prior RTH            09:30 to 16:00 ET, previous session

An hourly grid would have forced 09:30 to 09:00 or 10:00 and quietly redefined
two of the five. Thirty minutes costs twice the buckets and redefines nothing.

Each bucket also carries the three volume-weighted price moments, so an anchored
VWAP and its dispersion over any window are a sum of buckets too. VWAP is then
computed from one-second typical prices rather than one-minute ones — the same
upgrade the profiles get, for the source where dispersion is the whole point.
"""

from __future__ import annotations

import json
import tarfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from .rolling_profile import RollingProfile

EPOCH = date(1970, 1, 1)
NANOS_PER_BUCKET = 30 * 60 * 1_000_000_000
BUCKETS_PER_DAY = 48
# The exchange session rolls at 17:00 Chicago. Shifting a Chicago timestamp
# forward seven hours puts that roll on midnight, so the shifted calendar date
# is the session date. Keying on the UTC day instead splits every overnight
# session in two, which is the bug Stage 6 had to rebuild for.
SESSION_ROLL_HOURS = 7


def bucket_of(ts_ns: int) -> int:
    """Half-hour bucket number since the epoch, UTC."""
    return ts_ns // NANOS_PER_BUCKET


def bucket_start(bucket: int) -> datetime:
    from datetime import UTC

    return datetime.fromtimestamp(bucket * NANOS_PER_BUCKET / 1e9, tz=UTC)


def session_of_bucket(bucket: int) -> str:
    """Session date owning a bucket, via the 17:00 Chicago roll."""
    from zoneinfo import ZoneInfo

    local = bucket_start(bucket).astimezone(ZoneInfo("America/Chicago"))
    shifted = local + timedelta(hours=SESSION_ROLL_HOURS)
    return shifted.date().isoformat()


def empty_bucket() -> dict:
    return {"v": {}, "s": {}, "n": 0, "vol": 0.0, "pv": 0.0, "p2v": 0.0}


def merge_into(target: dict, entry: dict) -> None:
    for tick, value in entry["v"].items():
        key = int(tick)
        target["v"][key] = target["v"].get(key, 0.0) + float(value)
    for tick, value in entry["s"].items():
        key = int(tick)
        target["s"][key] = target["s"].get(key, 0) + int(value)
    target["n"] += int(entry.get("n", 0))
    for field in ("vol", "pv", "p2v"):
        target[field] += float(entry.get(field, 0.0))


class BucketStore:
    """Every cached half-hour bucket, merged once and held by bucket number."""

    ARCHIVE = Path("outputs/stage_07_cache/buckets.tar.gz")

    def __init__(self, folder: Path, archive: Path | None = None):
        self.folder = Path(folder)
        self._rehydrate(archive if archive is not None else self.ARCHIVE)
        self._buckets: dict[int, dict] = {}
        self._by_session: dict[str, list[int]] = defaultdict(list)
        self._load()

    def _rehydrate(self, archive: Path) -> None:
        """Unpack the committed archive unless the cache is already complete.

        Completeness is judged against the archive's member count. A workspace
        rollback can leave a handful of slices behind, and a cache that looks
        whole while holding a thirtieth of the data is worse than none at all —
        Stage 6 reported 54 sessions instead of 1,654 that way.
        """
        if not archive.exists():
            return
        with tarfile.open(archive, "r:gz") as handle:
            expected = sum(1 for name in handle.getnames() if name.endswith(".json"))
            if len(list(self.folder.glob("rg_*.json"))) >= expected:
                return
            self.folder.parent.mkdir(parents=True, exist_ok=True)
            handle.extractall(self.folder.parent, filter="data")
        restored = len(list(self.folder.glob("rg_*.json")))
        if restored < expected:
            raise RuntimeError(
                f"bucket cache incomplete after restore: {restored} of {expected}"
            )

    def _load(self) -> None:
        merged: dict[int, dict] = defaultdict(empty_bucket)
        for path in sorted(self.folder.glob("rg_*.json")):
            payload = json.loads(path.read_text())
            for bucket, entry in payload.items():
                merge_into(merged[int(bucket)], entry)
        self._buckets = dict(merged)
        for bucket in sorted(self._buckets):
            self._by_session[session_of_bucket(bucket)].append(bucket)

    @property
    def sessions(self) -> list[str]:
        return sorted(self._by_session)

    def __contains__(self, session: str) -> bool:
        return session in self._by_session

    def buckets(self, session: str) -> list[int]:
        return list(self._by_session.get(session, ()))

    def trailing(self, session: str, count: int) -> list[str]:
        """The `count` sessions ending at and including `session`."""
        available = self.sessions
        if session not in self._by_session:
            return []
        index = available.index(session)
        return available[max(0, index - count + 1) : index + 1]

    def range(self, start: int, end: int) -> list[int]:
        """Cached buckets in `[start, end)`, in order."""
        return [b for b in sorted(self._buckets) if start <= b < end]

    # -- windows -----------------------------------------------------------

    def profile(
        self, buckets, *, atr: Decimal, anchor: datetime, sessions=()
    ) -> RollingProfile | None:
        """Sum buckets into a profile on the shared tick grid.

        Adapting into `RollingProfile` rather than inventing a new shape is
        deliberate: node detection, value area, smoothing and the TPO logic are
        already written and fixture-tested against it. The inputs change; the
        detectors must not.
        """
        volume: dict[int, Decimal] = {}
        seconds: dict[int, int] = {}
        bars = 0
        for bucket in buckets:
            entry = self._buckets.get(bucket)
            if entry is None:
                continue
            for tick, value in entry["v"].items():
                volume[tick] = volume.get(tick, Decimal(0)) + Decimal(str(value))
            for tick, value in entry["s"].items():
                seconds[tick] = seconds.get(tick, 0) + value
            bars += entry["n"]
        if not volume:
            return None
        low, high = min(volume), max(volume)
        for index in range(low, high + 1):
            volume.setdefault(index, Decimal(0))
            seconds.setdefault(index, 0)
        return RollingProfile(
            anchor_time=anchor,
            sessions=tuple(sessions),
            low_index=low,
            high_index=high,
            volume=volume,
            tpo=seconds,
            bars_used=bars,
            atr_value=atr,
        )

    def moments(self, buckets) -> tuple[Decimal, Decimal, int] | None:
        """Volume-weighted mean, standard deviation and bar count over a window.

        Summed from per-bucket moments, so the VWAP of a nine-hour window costs
        eighteen additions rather than a pass over thirty thousand bars.
        """
        vol = pv = p2v = 0.0
        bars = 0
        for bucket in buckets:
            entry = self._buckets.get(bucket)
            if entry is None:
                continue
            vol += entry["vol"]
            pv += entry["pv"]
            p2v += entry["p2v"]
            bars += entry["n"]
        if vol <= 0:
            return None
        mean = pv / vol
        # Clamped at zero: the summed form is exact in real arithmetic but can
        # go a shade negative in floating point when dispersion is tiny.
        variance = max(0.0, p2v / vol - mean * mean)
        return Decimal(str(mean)), Decimal(str(variance ** 0.5)), bars


__all__ = [
    "BUCKETS_PER_DAY",
    "BucketStore",
    "NANOS_PER_BUCKET",
    "bucket_of",
    "bucket_start",
    "empty_bucket",
    "merge_into",
    "session_of_bucket",
]
