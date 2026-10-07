#!/usr/bin/env python3
"""Check a visual candidate's scope, state coverage and motion-review evidence."""
import argparse
import json
from pathlib import Path

from motion_review import validate_visual_review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--approve-baseline", action="store_true", help="Validate approval eligibility; never writes approval")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        def load(path):
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError(f"{path}: expected object")
            return value
        report = validate_visual_review(args.project_dir, load(args.project_dir / "planning/visual-plan.json"),
                                        load(args.project_dir / "config/project.json"), load(args.review),
                                        approve=args.approve_baseline)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report = {"status": "fail", "errors": [str(exc)], "warnings": []}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "out": str(args.out)}, ensure_ascii=False))
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
