"""Read the session histogram cache and present it as a profile.

The cache holds one `tick -> (volume, seconds)` map per exchange session. This
module merges the slices written per row group, then adapts a set of sessions
into the same `RollingProfile` shape the earlier stages used.

Adapting rather than rewriting is deliberate. Node detection, value area, TPO
extremes and the smoothing kernel are already written and fixture-tested against
that shape; pointing them at one-second histograms should change the *inputs*
they see, not the logic they apply. Anything else would confound "the data got
finer" with "the detector changed".

`seconds` maps onto the old `tpo` field. At one-second resolution the count of
bars touching a tick is the time spent there, which is what TPO always stood in
for.
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


def session_name(day_number: int) -> str:
    return (EPOCH + timedelta(days=day_number)).isoformat()


class HistogramStore:
    """All cached sessions, merged once and held by session date."""

    ARCHIVE = Path("outputs/stage_06_cache/histograms.tar.gz")

    def __init__(self, folder: Path, archive: Path | None = None):
        self.folder = Path(folder)
        self._rehydrate(archive if archive is not None else self.ARCHIVE)
        self._sessions: dict[str, dict] = {}
        self._load()

    def _rehydrate(self, archive: Path) -> None:
        """Unpack the committed archive when the expanded cache is missing.

        Building the cache costs several minutes of streaming; the archive costs
        seconds. Restoring automatically means a lost workspace is a pause, not
        a rebuild.
        """
        if self.folder.exists() and any(self.folder.glob("rg_*.json")):
            return
        if not archive.exists():
            return
        self.folder.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as handle:
            handle.extractall(self.folder.parent, filter="data")

    def _load(self) -> None:
        merged: dict[int, dict] = defaultdict(
            lambda: {"volume": defaultdict(Decimal), "seconds": defaultdict(int), "bars": 0}
        )
        for path in sorted(self.folder.glob("rg_*.json")):
            payload = json.loads(path.read_text())
            for day, entry in payload.items():
                target = merged[int(day)]
                for tick, volume in entry["volume"].items():
                    target["volume"][int(tick)] += Decimal(str(volume))
                for tick, seconds in entry["seconds"].items():
                    target["seconds"][int(tick)] += int(seconds)
                target["bars"] += int(entry["bars"])
        self._sessions = {session_name(day): value for day, value in merged.items()}

    @property
    def sessions(self) -> list[str]:
        return sorted(self._sessions)

    def __contains__(self, session: str) -> bool:
        return session in self._sessions

    def trailing(self, session: str, count: int) -> list[str]:
        """The `count` sessions ending at and including `session`."""
        available = self.sessions
        if session not in self._sessions:
            return []
        index = available.index(session)
        return available[max(0, index - count + 1) : index + 1]

    def profile(
        self, sessions: list[str] | tuple[str, ...], *, atr: Decimal, anchor: datetime
    ) -> RollingProfile | None:
        """Sum the named sessions into one profile on the shared tick grid."""
        volume: dict[int, Decimal] = {}
        seconds: dict[int, int] = {}
        bars = 0
        for name in sessions:
            entry = self._sessions.get(name)
            if entry is None:
                continue
            for tick, value in entry["volume"].items():
                volume[tick] = volume.get(tick, Decimal(0)) + value
            for tick, value in entry["seconds"].items():
                seconds[tick] = seconds.get(tick, 0) + value
            bars += entry["bars"]
        if not volume:
            return None
        low, high = min(volume), max(volume)
        for index in range(low, high + 1):
            volume.setdefault(index, Decimal(0))
            seconds.setdefault(index, 0)
        return RollingProfile(
            anchor_time=anchor,
            sessions=tuple(sorted(sessions)),
            low_index=low,
            high_index=high,
            volume=volume,
            tpo=seconds,
            bars_used=bars,
            atr_value=atr,
        )
