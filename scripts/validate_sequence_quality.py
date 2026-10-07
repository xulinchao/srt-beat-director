#!/usr/bin/env python3
"""Validate motion-reference and continuous-sequence evidence without producing media."""
import argparse
import json
from pathlib import Path

from sequence_quality import validate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=["planning", "prepared", "sample", "expand", "delivery"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = validate(args.project_dir, args.stage)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "stage": args.stage, "out": str(args.out)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
