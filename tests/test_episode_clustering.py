from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from hvn.episode_clustering import EpisodeEvent, cluster_episodes

NY = ZoneInfo("America/New_York")
START = datetime(2025, 1, 6, 10, tzinfo=NY)


def event(event_id: str, minute: int, low: int, high: int, contract: str = "NQH5"):
    return EpisodeEvent(
        event_id,
        contract,
        "R02",
        date(2025, 1, 6),
        START + timedelta(minutes=minute),
        low,
        high,
        "APPROACH_FROM_BELOW",
    )


def test_economic_episode_clustering_and_transitivity():
    result = cluster_episodes(
        [event("A", 0, 100, 110), event("B", 4, 105, 115), event("C", 8, 110, 120)]
    )
    assert len(set(result.values())) == 1


def test_no_clustering_across_contracts():
    result = cluster_episodes([event("A", 0, 100, 110), event("B", 0, 100, 110, "NQM5")])
    assert result["A"] != result["B"]
