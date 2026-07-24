from __future__ import annotations

from hvn.ledger import write_records
from hvn.models import HvnNode, PeakCandidate


def test_empty_candidate_and_node_ledgers_preserve_headers(tmp_path):
    candidates = tmp_path / "candidates.csv"
    nodes = tmp_path / "nodes.csv"
    write_records((), candidates, record_type=PeakCandidate)
    write_records((), nodes, record_type=HvnNode)
    assert candidates.read_text().startswith("candidate_id,")
    assert nodes.read_text().startswith("hvn_id,")
