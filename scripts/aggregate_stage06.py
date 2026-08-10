"""Stage 6 aggregation: the frozen reversal test, read off the one-second run.

Deliberately identical in logic to `aggregate_reversal_study.py`, which produced
the Stage 5 numbers. Only the input format differs — per-session JSON instead of
a CSV ledger — because the comparison is "did the result survive better volume",
and changing the analysis at the same time as the data would make that question
unanswerable.

The three guards from Stage 5 are carried over intact:

  width strata   stacks are wider on average, and width alone shifts reversal
                 rates, so degree is only ever compared inside a width band
  year agreement counted over years carrying data in BOTH arms; a missing cell
                 did not disagree
  first touch    one barrier per price region per session
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "outputs" / "stage_06_reversal"
HORIZONS = (10, 30, 120)
WIDTH_BINS = (
    (Decimal("0.0"), Decimal("0.7")),
    (Decimal("0.7"), Decimal("1.2")),
    (Decimal("1.2"), Decimal("2.0")),
    (Decimal("2.0"), Decimal("3.1")),
)
MIN_EVENTS = 50
REVERSED = "REVERSED"
BROKE_THROUGH = "BROKE_THROUGH"


def load(folder: Path) -> list[dict]:
    """Tapped rows, reduced to one barrier per price region per session."""
    kept: list[dict] = []
    for path in sorted(folder.glob("*.json")):
        rows = [r for r in json.loads(path.read_text()) if r.get("tapped")]
        rows.sort(key=lambda r: (r["anchor_time"], r["band_low"]))
        spent: dict[tuple, list[tuple[Decimal, Decimal]]] = defaultdict(list)
        for row in rows:
            key = (row["tolerance_atr"], row["direction"])
            low, high = Decimal(row["band_low"]), Decimal(row["band_high"])
            if any(low < b and a < high for a, b in spent[key]):
                continue
            spent[key].append((low, high))
            kept.append(row)
    return kept


def resolved_rate(rows, horizon: int):
    """Reversal share among *resolved* outcomes.

    Events still inside the band at the horizon have not resolved either way and
    are excluded rather than folded into the denominator.
    """
    resolved = [
        r for r in rows
        if r.get(f"evaluated_{horizon}m")
        and r.get(f"state_{horizon}m") in (REVERSED, BROKE_THROUGH)
    ]
    if not resolved:
        return None, 0
    hits = sum(1 for r in resolved if r[f"state_{horizon}m"] == REVERSED)
    return Decimal(100 * hits) / Decimal(len(resolved)), len(resolved)


def mean(values):
    return sum(values) / Decimal(len(values)) if values else None


def build(events: list[dict]) -> list[dict]:
    out = []
    years = sorted({e["year"] for e in events})
    for tolerance in sorted({e["tolerance_atr"] for e in events}, key=Decimal):
        pool = [e for e in events if e["tolerance_atr"] == tolerance]
        for low, high in WIDTH_BINS:
            stratum = [e for e in pool if low <= Decimal(e["width_atr"]) < high]
            reference = [e for e in stratum if e["level_kinds"] == 1]
            for horizon in HORIZONS:
                base, base_n = resolved_rate(reference, horizon)
                if base is None or base_n < MIN_EVENTS:
                    continue
                for count in (1, 2, 3, 4):
                    rows = (
                        [e for e in stratum if e["level_kinds"] == count]
                        if count < 4
                        else [e for e in stratum if e["level_kinds"] >= 4]
                    )
                    rate, n = resolved_rate(rows, horizon)
                    if rate is None or n < MIN_EVENTS:
                        continue
                    difference = rate - base
                    agreeing = testable = 0
                    for year in years:
                        a, an = resolved_rate(
                            [r for r in rows if r["year"] == year], horizon
                        )
                        b, bn = resolved_rate(
                            [r for r in reference if r["year"] == year], horizon
                        )
                        if a is None or b is None or an < 20 or bn < 20:
                            continue
                        testable += 1
                        if (a - b) * difference > 0:
                            agreeing += 1
                    fav = mean([
                        Decimal(str(r[f"favourable_{horizon}m"])) for r in rows
                        if r.get(f"favourable_{horizon}m") is not None
                    ])
                    adv = mean([
                        Decimal(str(r[f"adverse_{horizon}m"])) for r in rows
                        if r.get(f"adverse_{horizon}m") is not None
                    ])
                    out.append({
                        "tolerance_atr": tolerance,
                        "width_bin": f"{low}-{high}",
                        "level_kinds": "4+" if count == 4 else count,
                        "horizon_min": horizon,
                        "resolved": n,
                        "reversal_pct": rate.quantize(Decimal("0.01")),
                        "vs_single_kind_pp": difference.quantize(Decimal("0.01")),
                        "mean_favourable": fav.quantize(Decimal("0.001")) if fav else None,
                        "mean_adverse": adv.quantize(Decimal("0.001")) if adv else None,
                        "years_agreeing": f"{agreeing}/{testable}",
                        "years_testable": testable,
                    })
    return out


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="aggregate_stage06.py")
    parser.add_argument("--dir", type=Path, default=DEFAULT_IN)
    args = parser.parse_args(argv)

    events = load(args.dir)
    rows = build(events)
    output = args.dir / "aggregate"
    output.mkdir(parents=True, exist_ok=True)
    (output / "reversal_by_stack.json").write_text(
        json.dumps([{k: str(v) for k, v in r.items()} for r in rows], indent=1) + "\n"
    )

    stacked = [r for r in rows if r["level_kinds"] != 1 and r["years_testable"] >= 3]
    positive = [r for r in stacked if r["vs_single_kind_pp"] > 0]
    summary = {
        "first_touch_events": len(events),
        "years": sorted({e["year"] for e in events}),
        "cells": len(rows),
        "stacked_cells_testable": len(stacked),
        "stacked_cells_positive": len(positive),
        "sign_test_p": (
            round(sum(comb(len(stacked), i)
                      for i in range(len(positive), len(stacked) + 1)) / 2 ** len(stacked), 6)
            if stacked else None
        ),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))

    print(f"\n{'tol':>6}{'width':>10}{'kinds':>7}{'horizon':>9}{'n':>7}"
          f"{'reversal':>10}{'vs 1':>8}{'fav':>8}{'adv':>8}{'years':>8}")
    for r in rows:
        print(f"{r['tolerance_atr']:>6}{r['width_bin']:>10}{str(r['level_kinds']):>7}"
              f"{r['horizon_min']:>9}{r['resolved']:>7}{r['reversal_pct']:>9}%"
              f"{r['vs_single_kind_pp']:>8}{str(r['mean_favourable']):>8}"
              f"{str(r['mean_adverse']):>8}{r['years_agreeing']:>8}")


if __name__ == "__main__":
    main()
