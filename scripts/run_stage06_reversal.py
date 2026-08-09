"""Stage 6: the frozen reversal test, on one-second data, session by session.

The test itself is unchanged from Stage 5 and is defined in
`research/hvn/STAGE_06_ONE_SECOND_SPEC.md`. Only the *inputs* change: the
composite profile now comes from one-second histograms, where a bar usually
touches one to three ticks, instead of one-minute bars smeared across twenty.

Confounding "the data got finer" with "the method changed" would make the whole
comparison meaningless, so the level detectors, the tap rule, the horizons and
the statistic are all carried over untouched.

Per session:

    composite   trailing 20 sessions of histograms, rebuilt daily
    intraday    hourly VP, Globex and cash developing, prior RTH, four VWAPs,
                all from this session's one-minute bars
    anchors     each hourly close
    outcome     tap, then state and two-sided excursion at 10, 30, 120 minutes

Work is written per session and skipped if already present, so a run interrupted
at any point resumes without repeating itself.
"""

from __future__ import annotations

import argparse
import json
from bisect import bisect_right
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pyarrow.compute as pc

from hvn.confluence import (
    ABOVE,
    MAX_CLUSTER_WIDTH_ATR,
    TOLERANCES_ATR,
    cluster_levels,
    nearest_barriers,
)
from hvn.histogram_store import HistogramStore
from hvn.models import Bar
from hvn.range_reader import HTTPRangeReader
from hvn.rolling_profile import Node, find_tap, reanchor_times
from hvn.stage4_levels import build_level_set

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "outputs" / "stage_06_reversal"
HISTOGRAMS = ROOT / "outputs" / "stage_06_histograms"
VALIDATION = ROOT / "outputs" / "stage_06_contract_validation"
FILE_ID = "1aop7eaNO56pM9kZKyxelMcD6Uf8fG-Yf"

IS_YEARS = (2010, 2011, 2012, 2019, 2021, 2023, 2025)
ROLLING_SESSIONS = 20
NANOS_PER_MINUTE = 60_000_000_000
PRICE_SCALE = 1_000_000_000
EPOCH = date(1970, 1, 1)

# Frozen interaction parameters, identical to Stage 5.
HORIZONS_MINUTES = (10, 30, 120)
TAP_SEARCH_BARS = 60
TAP_BAND_ATR = Decimal("0.5")
TAP_MIN_BARS = 3
LIVE_BARS = TAP_SEARCH_BARS + TAP_MIN_BARS + max(HORIZONS_MINUTES)
ATR_PERIOD = 24

REVERSED = "REVERSED"
BROKE_THROUGH = "BROKE_THROUGH"
INSIDE = "INSIDE"


def minute_bars(parquet, day_numbers, instrument_by_day) -> list[Bar]:
    """One-minute bars for the named session days, front month only."""
    import pyarrow as pa

    from build_histograms import session_day

    low_ns = min(day_numbers) * 86_400_000_000_000 - 86_400_000_000_000
    high_ns = (max(day_numbers) + 1) * 86_400_000_000_000
    out: list[Bar] = []
    for index in range(parquet.metadata.num_row_groups):
        stats = parquet.metadata.row_group(index).column(0).statistics
        if stats is not None and stats.has_min_max:
            if int(stats.max) < low_ns or int(stats.min) > high_ns:
                continue
        table = parquet.read_row_group(
            index,
            columns=["ts_event", "instrument_id", "open", "high", "low", "close", "volume"],
        )
        days = session_day(table.column("ts_event"))
        table = table.append_column("day", days)
        keep = pc.is_in(table.column("day"), value_set=pa.array(sorted(day_numbers)))
        table = table.filter(keep)
        if table.num_rows == 0:
            continue
        wanted = pa.array(
            [instrument_by_day.get(int(d), -1) for d in table.column("day").to_pylist()]
        )
        table = table.filter(pc.equal(table.column("instrument_id"), wanted))
        if table.num_rows == 0:
            continue
        minute = pc.multiply(
            pc.divide(table.column("ts_event"), NANOS_PER_MINUTE), NANOS_PER_MINUTE
        )
        table = table.append_column("minute", minute)
        grouped = table.group_by(["minute"], use_threads=False).aggregate(
            [("open", "first"), ("high", "max"), ("low", "min"),
             ("close", "last"), ("volume", "sum")]
        )
        for ts, o, h, low_price, c, v in zip(
            grouped.column("minute").to_pylist(),
            grouped.column("open_first").to_pylist(),
            grouped.column("high_max").to_pylist(),
            grouped.column("low_min").to_pylist(),
            grouped.column("close_last").to_pylist(),
            grouped.column("volume_sum").to_pylist(),
            strict=True,
        ):
            close_time = datetime.fromtimestamp(
                (ts + NANOS_PER_MINUTE) / 1e9, tz=__import__("datetime").UTC
            )
            out.append(
                Bar(
                    source_row_id=f"NQ|{ts}",
                    close_time=close_time,
                    open=Decimal(o) / PRICE_SCALE,
                    high=Decimal(h) / PRICE_SCALE,
                    low=Decimal(low_price) / PRICE_SCALE,
                    close=Decimal(c) / PRICE_SCALE,
                    volume=Decimal(v or 0),
                    symbol="NQ",
                )
            )
    out.sort(key=lambda b: b.close_time)
    return out


def measure(forward, cluster, *, atr, direction, base) -> dict:
    """Tap the cluster, then state and two-sided excursion at each horizon."""
    low, high = cluster.low, cluster.high
    node = Node(
        node_class="BARRIER", low_index=0, high_index=0,
        node_low=low, node_high=high, peak_index=0,
        peak_price=(low + high) / 2, smoothed_activity=Decimal(0),
        activity_percentile=Decimal(0), anchor_time=base["anchor_time_dt"],
    )
    tap = find_tap(
        forward[:TAP_SEARCH_BARS], node, atr=atr,
        max_distance_atr=TAP_BAND_ATR, min_bars_within=TAP_MIN_BARS,
    )
    row = {k: v for k, v in base.items() if k != "anchor_time_dt"}
    row |= {
        "direction": direction,
        "degree": cluster.degree,
        "level_kinds": len(set(cluster.kinds)),
        "kinds": "|".join(cluster.kinds),
        "band_low": str(low),
        "band_high": str(high),
        "width_atr": str((high - low) / atr),
        "tapped": tap.valid,
    }
    if not tap.valid or tap.first_index is None:
        return row

    start = tap.first_index + TAP_MIN_BARS
    window = forward[start : start + max(HORIZONS_MINUTES)]
    mid = float((low + high) / 2)
    scale = float(atr)
    up = direction == ABOVE
    favourable = adverse = None
    snapshots: dict[int, tuple] = {}
    for index, bar in enumerate(window, start=1):
        bar_low, bar_high, bar_close = float(bar.low), float(bar.high), float(bar.close)
        if up:
            fav, adv = (mid - bar_low) / scale, (bar_high - mid) / scale
        else:
            fav, adv = (bar_high - mid) / scale, (mid - bar_low) / scale
        favourable = fav if favourable is None or fav > favourable else favourable
        adverse = adv if adverse is None or adv > adverse else adverse
        if index in HORIZONS_MINUTES:
            snapshots[index] = (favourable, adverse, bar_close)

    for horizon in HORIZONS_MINUTES:
        if horizon not in snapshots:
            row[f"evaluated_{horizon}m"] = False
            continue
        fav, adv, close = snapshots[horizon]
        if (up and close < float(low)) or (not up and close > float(high)):
            state = REVERSED
        elif (up and close >= float(high)) or (not up and close <= float(low)):
            state = BROKE_THROUGH
        else:
            state = INSIDE
        row[f"evaluated_{horizon}m"] = True
        row[f"favourable_{horizon}m"] = fav
        row[f"adverse_{horizon}m"] = adv
        row[f"state_{horizon}m"] = state
    return row


def run_session(session: str, store: HistogramStore, parquet, instrument_by_day) -> list[dict]:
    """Every anchor in one session, against levels knowable at that anchor."""
    from hvn.atr import wilder_atr
    from hvn.stage02_pipeline import AtrSelector

    window = store.trailing(session, ROLLING_SESSIONS + 1)
    if len(window) < ROLLING_SESSIONS + 1:
        return []
    # The composite is rebuilt daily and excludes the developing session, so it
    # is knowable in full at the session's open.
    composite_sessions = window[:-1]

    day = (date.fromisoformat(session) - EPOCH).days
    bars = minute_bars(parquet, {day - 1, day}, instrument_by_day)
    if len(bars) < 400:
        return []
    atrs = AtrSelector(wilder_atr(tuple(bars), period=ATR_PERIOD))
    times = [b.close_time for b in bars]

    rows: list[dict] = []
    for anchor in reanchor_times(bars, minutes=60):
        try:
            atr = atrs.before(anchor).value
        except (ValueError, IndexError):
            continue
        if atr <= 0:
            continue
        composite = store.profile(composite_sessions, atr=atr, anchor=anchor)
        if composite is None:
            continue
        level_set = build_level_set(bars, anchor, atr=atr, rolling_profile=composite)
        level_set.assert_causal()
        if not level_set.levels:
            continue
        index = bisect_right(times, anchor)
        forward = bars[index : index + LIVE_BARS]
        if len(forward) < LIVE_BARS:
            continue
        price = bars[index - 1].close

        for tolerance in TOLERANCES_ATR:
            clusters = cluster_levels(
                level_set.levels,
                tolerance=tolerance * atr,
                max_width=MAX_CLUSTER_WIDTH_ATR * atr,
            )
            for direction, cluster in nearest_barriers(clusters, price).items():
                if cluster is None:
                    continue
                rows.append(
                    measure(
                        forward, cluster, atr=atr, direction=direction,
                        base={
                            "session": session,
                            "year": int(session[:4]),
                            "anchor_time": anchor.isoformat(),
                            "anchor_time_dt": anchor,
                            "atr": str(atr),
                            "tolerance_atr": str(tolerance),
                            "distance_atr": str(
                                (cluster.low - price) / atr
                                if direction == ABOVE
                                else (price - cluster.high) / atr
                            ),
                        },
                    )
                )
    return rows


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="run_stage06_reversal.py")
    parser.add_argument("--limit", type=int, default=0, help="sessions this run")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    import pyarrow.parquet as pq

    from scan_contracts import resolved_url
    from build_histograms import front_month_by_day, front_month_by_session

    args.out.mkdir(parents=True, exist_ok=True)
    store = HistogramStore(HISTOGRAMS)
    instrument_by_day = front_month_by_session(front_month_by_day())
    parquet = pq.ParquetFile(HTTPRangeReader(resolved_url(FILE_ID)))

    todo = [
        s for s in store.sessions
        if int(s[:4]) in IS_YEARS and not (args.out / f"{s}.json").exists()
    ]
    if args.limit:
        todo = todo[: args.limit]

    done = 0
    for session in todo:
        rows = run_session(session, store, parquet, instrument_by_day)
        (args.out / f"{session}.json").write_text(json.dumps(rows, separators=(",", ":")))
        done += 1
        tapped = sum(1 for r in rows if r.get("tapped"))
        print(f"{session}: {len(rows)} barriers, {tapped} tapped", flush=True)

    remaining = sum(
        1 for s in store.sessions
        if int(s[:4]) in IS_YEARS and not (args.out / f"{s}.json").exists()
    )
    print(json.dumps({"sessions_written": done, "remaining": remaining}))


if __name__ == "__main__":
    main()
