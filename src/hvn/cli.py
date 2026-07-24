from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import generate_synthetic_audit_pack


def main() -> None:
    parser = argparse.ArgumentParser(description="NQ HVN Stage 1 utilities")
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("synthetic-audit")
    audit.add_argument("--output", type=Path, default=Path("outputs/stage_01/synthetic"))
    audit.add_argument("--code-sha", default="UNCOMMITTED")
    args = parser.parse_args()
    if args.command == "synthetic-audit":
        result = generate_synthetic_audit_pack(args.output, code_sha=args.code_sha)
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
