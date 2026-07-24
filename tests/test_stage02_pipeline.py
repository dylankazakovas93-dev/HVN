from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from hvn.models import Bar
from hvn.stage02_pipeline import ContractSelector, choose_contract, trading_dates

NY = ZoneInfo("America/New_York")


def test_pipeline_contract_selection_is_causal_and_deterministic():
    start = datetime(2025, 1, 6, 9, 30, tzinfo=NY)
    bars = (
        Bar("A", start - timedelta(minutes=1), Decimal(1), Decimal(1), Decimal(1), Decimal(1), Decimal(10), "NQH5"),
        Bar("B", start - timedelta(minutes=1), Decimal(1), Decimal(1), Decimal(1), Decimal(1), Decimal(20), "NQM5"),
    )
    assert choose_contract(bars, start) == "NQM5"
    grouped = {
        symbol: tuple(bar for bar in bars if bar.symbol == symbol)
        for symbol in ("NQH5", "NQM5")
    }
    assert ContractSelector(grouped).choose(start) == choose_contract(bars, start)


def test_trading_dates_require_substantial_rth_coverage():
    start = datetime(2025, 1, 6, 9, 30, tzinfo=NY)
    bars = tuple(
        Bar(
            str(index),
            start + timedelta(minutes=index + 1),
            Decimal(1),
            Decimal(1),
            Decimal(1),
            Decimal(1),
            Decimal(1),
            "NQH5",
        )
        for index in range(300)
    )
    assert trading_dates(bars) == (start.date(),)
