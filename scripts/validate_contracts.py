"""Run the front-month checks over the whole scanned history, year by year.

The mapping is an inference and is reported as such. Validating per year rather
than once over sixteen years is deliberate: an early period with thin volume or
a different ID convention should fail on its own, not be carried by the liquid
years around it. Any year that fails is excluded from the study rather than
patched.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from hvn.contract_selection import choose_front_month, validate_selection

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "outputs" / "stage_06_contract_validation"
EPOCH = date(1970, 1, 1)


def load_sessions(folder: Path) -> dict[str, list[tuple[int, int, float]]]:
    per_day: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(lambda: [0, None]))
    for path in sorted(folder.glob("rg_*.json")):
        for row in json.loads(path.read_text()):
            day = (EPOCH + timedelta(days=row["day"])).isoformat()
            entry = per_day[day][row["instrument_id"]]
            entry[0] += row["volume"]
            if row["close"] is not None:
                entry[1] = row["close"]
    return {
        day: [(i, v, c) for i, (v, c) in instruments.items()]
        for day, instruments in per_day.items()
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="validate_contracts.py")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args(argv)

    sessions = load_sessions(args.dir / "sessions")
    choices = []
    for day in sorted(sessions):
        choice = choose_front_month(day, sessions[day])
        if choice is not None:
            choices.append(choice)

    by_year: dict[int, list] = defaultdict(list)
    for choice in choices:
        by_year[int(choice.session_date[:4])].append(choice)

    report = {"overall": {}, "years": {}}
    print(f"{'year':>6}{'sessions':>10}{'switches':>10}{'dominance':>11}{'tenure':>8}  verdict")
    for year in sorted(by_year):
        result = validate_selection(by_year[year])
        report["years"][year] = {
            "sessions": result.sessions,
            "switches": result.switches,
            "median_dominance": str(result.median_dominance),
            "min_tenure_days": result.min_tenure_days,
            "verified": result.verified,
            "failures": list(result.failures),
        }
        dominance = (
            f"{float(result.median_dominance):.3f}" if result.median_dominance else "-"
        )
        tenure = result.min_tenure_days if result.min_tenure_days is not None else "-"
        verdict = "OK" if result.verified else ",".join(result.failures)
        print(
            f"{year:>6}{result.sessions:>10}{result.switches:>10}"
            f"{dominance:>11}{str(tenure):>8}  {verdict}"
        )

    whole = validate_selection(choices)
    report["overall"] = {
        "sessions": whole.sessions,
        "switches": whole.switches,
        "median_dominance": str(whole.median_dominance),
        "verified": whole.verified,
        "failures": list(whole.failures),
        "first_session": choices[0].session_date,
        "last_session": choices[-1].session_date,
    }
    passing = [y for y, r in report["years"].items() if r["verified"]]
    report["years_verified"] = sorted(passing)
    report["years_failed"] = sorted(set(report["years"]) - set(passing))
    (args.dir / "validation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(f"\nsessions {whole.sessions}  {choices[0].session_date} .. {choices[-1].session_date}")
    print(f"years verified: {report['years_verified']}")
    print(f"years failed:   {report['years_failed']}")


if __name__ == "__main__":
    main()
