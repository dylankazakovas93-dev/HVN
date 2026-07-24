#!/usr/bin/env python3
from pathlib import Path

from hvn.audit import generate_synthetic_audit_pack


if __name__ == "__main__":
    generate_synthetic_audit_pack(Path("outputs/stage_01/synthetic"))
