from __future__ import annotations

import csv
import hashlib

from hvn.audit import generate_synthetic_audit_pack
from hvn.models import AllocationMethod, ProfileFamily


def test_synthetic_audit_pack_is_complete_conservative_and_deterministic(tmp_path):
    first = generate_synthetic_audit_pack(tmp_path)
    first_bytes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in tmp_path.iterdir()
    }
    second = generate_synthetic_audit_pack(tmp_path)
    second_bytes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in tmp_path.iterdir()
    }
    assert first == second
    assert first_bytes == second_bytes
    assert len(first) == len(ProfileFamily) * len(AllocationMethod)
    for family in ProfileFamily:
        for method in AllocationMethod:
            stem = f"{family.value}__{method.value}"
            for suffix in ("profile.csv", "candidates.csv", "nodes.csv", "audit.svg"):
                assert (tmp_path / f"{stem}__{suffix}").exists()
            with (tmp_path / f"{stem}__profile.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            assert rows
            if method == AllocationMethod.UNIFORM_VOLUME:
                assert rows[0]["source_total_volume"] == rows[0]["allocated_total_volume"]
            assert all(row["data_partition"] == "synthetic" for row in rows)
