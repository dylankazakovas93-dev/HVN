import gzip
from decimal import Decimal

from hvn.stage02_ledger import deterministic_gzip_csv_bytes


def test_stage02_gzip_ledger_is_byte_identical_and_stably_sorted():
    rows = [
        {"event_id": "B", "value": Decimal("1.2500"), "flag": False},
        {"event_id": "A", "value": Decimal("2.000"), "flag": True},
    ]
    fields = ("event_id", "value", "flag")
    first = deterministic_gzip_csv_bytes(rows, fields, sort_by=("event_id",))
    second = deterministic_gzip_csv_bytes(reversed(rows), fields, sort_by=("event_id",))
    assert first == second
    assert gzip.decompress(first).decode() == (
        "event_id,value,flag\nA,2,true\nB,1.25,false\n"
    )
