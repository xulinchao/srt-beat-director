#!/usr/bin/env python3
"""Validate the article-derived semantic-to-template mapping catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CANONICAL_STRUCTURES = {
    "comparison",
    "aggregation",
    "filtering",
    "hierarchy",
    "causality",
    "replacement",
    "expansion",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--repositories-root", required=True, type=Path)
    parser.add_argument("--template-index", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def validate(mapping_path: Path, repositories_root: Path, template_index_path: Path | None = None) -> dict:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    template_ids: set[str] = set()
    if template_index_path:
        template_index = json.loads(template_index_path.read_text(encoding="utf-8"))
        template_ids = {str(item.get("id")) for item in template_index.get("templates") or []}

    errors: list[str] = []
    warnings: list[str] = []
    structures = mapping.get("structures") or []
    structure_ids = [str(item.get("id")) for item in structures]
    present = set(structure_ids)

    if len(structure_ids) != len(present):
        errors.append("语义结构 ID 重复")
    missing = sorted(CANONICAL_STRUCTURES - present)
    extra = sorted(present - CANONICAL_STRUCTURES)
    if missing:
        errors.append(f"缺少标准语义结构：{missing}")
    if extra:
        errors.append(f"出现非标准主语义结构：{extra}")

    candidate_ids: set[str] = set()
    candidate_count = 0
    for structure in structures:
        structure_id = str(structure.get("id"))
        if not str(structure.get("question", "")).strip():
            errors.append(f"{structure_id} 缺少判定问题")
        for template_id in structure.get("local_template_ids") or []:
            if template_ids and template_id not in template_ids:
                errors.append(f"{structure_id} 引用了不存在的本地模板：{template_id}")
        candidates = structure.get("external_candidates") or []
        if len(candidates) < 2:
            warnings.append(f"{structure_id} 的外部候选少于 2 个")
        for candidate in candidates:
            candidate_count += 1
            candidate_id = str(candidate.get("id"))
            if candidate_id in candidate_ids:
                errors.append(f"外部候选 ID 重复：{candidate_id}")
            candidate_ids.add(candidate_id)
            for key in ("repository", "path", "semantic_fit", "skeleton", "license", "status"):
                if candidate.get(key) in (None, "", [], {}):
                    errors.append(f"{candidate_id} 缺少 {key}")
            source_path = repositories_root / str(candidate.get("repository")) / str(candidate.get("path"))
            if not source_path.is_file():
                errors.append(f"{candidate_id} 的参考路径不存在：{source_path}")
            skeleton = candidate.get("skeleton") or {}
            for key in ("element_relation", "main_motion", "phase_order"):
                if skeleton.get(key) in (None, "", []):
                    errors.append(f"{candidate_id} 的 skeleton 缺少 {key}")

    return {
        "schema_version": "0.1",
        "status": "pass" if not errors else "fail",
        "summary": {
            "structure_count": len(present),
            "candidate_count": candidate_count,
            "local_template_reference_count": sum(
                len(item.get("local_template_ids") or []) for item in structures
            ),
        },
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    args = parse_args()
    try:
        report = validate(args.mapping, args.repositories_root, args.template_index)
    except (OSError, json.JSONDecodeError) as exc:
        print(str(exc))
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "out": str(args.out)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
