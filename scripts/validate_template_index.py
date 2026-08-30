#!/usr/bin/env python3
"""Validate local B-roll template metadata, sources, licenses, and readiness states."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ALLOWED_STATUSES = {
    "styleframe-only",
    "implementation-required",
    "animation-verified",
    "superseded",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def validate(index_path: Path) -> dict:
    data = json.loads(index_path.read_text(encoding="utf-8"))
    project_dir = index_path.parent.parent
    errors: list[str] = []
    warnings: list[str] = []
    ids: set[str] = set()

    for position, template in enumerate(data.get("templates") or [], start=1):
        template_id = template.get("id") or f"template-{position}"
        if template_id in ids:
            errors.append(f"模板 ID 重复：{template_id}")
        ids.add(template_id)
        for key in ("semantic_structure", "item_range", "duration_ms", "aspect_ratios", "source_file", "source", "hyperframes_status"):
            if template.get(key) in (None, "", []):
                errors.append(f"{template_id} 缺少 {key}")

        status = str(template.get("hyperframes_status", ""))
        if status not in ALLOWED_STATUSES:
            errors.append(f"{template_id} 状态无效：{status}")
        source_file = template.get("source_file")
        if source_file and not (project_dir / source_file).resolve().is_file():
            errors.append(f"{template_id} source_file 不存在：{source_file}")
        source = template.get("source") or {}
        if not source.get("license"):
            errors.append(f"{template_id} 缺少 source.license")
        if status == "animation-verified" and str(source_file).lower().endswith(".svg"):
            warnings.append(f"{template_id} 标记 animation-verified，但 source_file 仍是静态 SVG")

    return {
        "schema_version": "0.1",
        "status": "pass" if not errors else "fail",
        "template_count": len(ids),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    args = parse_args()
    report = validate(args.index)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "out": str(args.out)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
