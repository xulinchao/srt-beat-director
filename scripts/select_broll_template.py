#!/usr/bin/env python3
"""Rank local B-roll templates and expose licensed external fallbacks on a miss."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--semantic-structure", required=True)
    parser.add_argument("--semantic-pattern")
    parser.add_argument("--item-count", required=True, type=int)
    parser.add_argument("--duration-ms", required=True, type=int)
    parser.add_argument("--aspect-ratio", required=True)
    parser.add_argument("--material-type", choices=("verified-media", "no-material", "text-only"))
    parser.add_argument("--presentation-type", choices=("verified-media", "infographic", "text-motion"))
    parser.add_argument("--semantic-map", type=Path)
    parser.add_argument("--external-sources", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def readiness(status: str) -> tuple[int, bool, bool]:
    value = status.lower()
    if "superseded" in value or value == "stale":
        return (-1000, True, False)
    if "animation-verified" in value or value == "verified":
        return (30, False, True)
    if "implementation-required" in value:
        return (10, True, False)
    return (0, True, False)


def resolve_structure(mapping: dict | None, value: str) -> dict | None:
    if not mapping:
        return None
    normalized = value.strip().lower()
    for structure in mapping.get("structures") or []:
        names = {str(structure.get("id", "")).lower()}
        names.update(str(alias).lower() for alias in structure.get("aliases") or [])
        if normalized in names:
            return structure
    return None


def select(
    index: dict,
    semantic_structure: str,
    item_count: int,
    duration_ms: int,
    aspect_ratio: str,
    external_sources: dict | None = None,
    semantic_mapping: dict | None = None,
    material_type: str | None = None,
    presentation_type: str | None = None,
    semantic_pattern: str | None = None,
) -> dict:
    mapped_structure = resolve_structure(semantic_mapping, semantic_structure)
    mapped_template_ids = set((mapped_structure or {}).get("local_template_ids") or [])
    candidates: list[dict] = []
    for template in index.get("templates") or []:
        exact_pattern_match = bool(semantic_pattern) and template.get("semantic_structure") == semantic_pattern
        exact_semantic_match = template.get("semantic_structure") == semantic_structure
        mapped_template_match = template.get("id") in mapped_template_ids
        if not exact_pattern_match and not exact_semantic_match and not mapped_template_match:
            continue
        item_range = template.get("item_range") or [0, 0]
        duration_range = template.get("duration_ms") or [0, 0]
        aspect_ratios = template.get("aspect_ratios") or []
        if not (item_range[0] <= item_count <= item_range[1]):
            continue
        if not (duration_range[0] <= duration_ms <= duration_range[1]):
            continue
        if aspect_ratio not in aspect_ratios:
            continue
        bonus, implementation_required, status_qualified = readiness(
            str(template.get("hyperframes_status", ""))
        )
        if bonus <= -1000:
            continue
        animation_phases = template.get("animation_phases") or []
        source_file = str(template.get("source_file") or "")
        qualified_for_reuse = (
            status_qualified
            and bool(template.get("preview"))
            and len(animation_phases) >= 3
            and not source_file.lower().endswith(".svg")
        )
        span_penalty = (item_range[1] - item_range[0]) + (duration_range[1] - duration_range[0]) / 10000
        semantic_bonus = 60 if exact_pattern_match else (40 if exact_semantic_match else 15)
        score = round(100 + semantic_bonus + bonus - span_penalty, 3)
        candidates.append(
            {
                "template_id": template.get("id"),
                "score": score,
                "implementation_required": implementation_required,
                "qualified_for_reuse": qualified_for_reuse,
                "hyperframes_status": template.get("hyperframes_status"),
                "source_file": template.get("source_file"),
                "animation_phases": animation_phases,
                "known_limits": template.get("known_limits") or [],
            }
        )
    candidates.sort(key=lambda candidate: (-candidate["score"], candidate["template_id"] or ""))
    qualified_candidates = [candidate for candidate in candidates if candidate["qualified_for_reuse"]]

    if qualified_candidates:
        status = "local-match"
        selected = qualified_candidates[0]
        external = []
        external_candidates = []
    else:
        status = "external-research-required"
        selected = None
        external = []
        external_candidates = []
        for candidate in (mapped_structure or {}).get("external_candidates") or []:
            material_types = candidate.get("material_types") or []
            presentation_types = candidate.get("presentation_types") or []
            if material_type and material_types and material_type not in material_types:
                continue
            if presentation_type and presentation_types and presentation_type not in presentation_types:
                continue
            external_candidates.append(candidate)
        if external_sources:
            for source in external_sources.get("sources") or []:
                external.append(
                    {
                        "id": source.get("id"),
                        "url": source.get("url"),
                        "license": source.get("license"),
                        "usage_policy": source.get("usage_policy"),
                        "original_framework": source.get("original_framework"),
                    }
                )

    required_reviews = min(2, len(external_candidates))

    return {
        "schema_version": "0.1",
        "selection_policy": "single-source-per-shot",
        "status": status,
        "query": {
            "semantic_structure": semantic_structure,
            "semantic_pattern": semantic_pattern,
            "item_count": item_count,
            "duration_ms": duration_ms,
            "aspect_ratio": aspect_ratio,
            "material_type": material_type,
            "presentation_type": presentation_type,
            "canonical_structure": (mapped_structure or {}).get("id"),
        },
        "selected": selected,
        "local_candidates": candidates,
        "external_sources": external,
        "external_candidates": external_candidates,
        "required_external_candidate_reviews": required_reviews,
        "custom_build_allowed": status == "external-research-required" and not external_candidates,
        "research_record_required_before_implementation": status == "external-research-required" and bool(external_candidates),
        "confirmation_required_before_implementation": True,
    }


def markdown(report: dict) -> str:
    if report["selected"]:
        selected = report["selected"]
        result = (
            f"- 模板：`{selected['template_id']}`\n"
            f"- 需要实现动画：`{str(selected['implementation_required']).lower()}`\n"
            f"- 状态：`{selected['hyperframes_status']}`"
        )
    else:
        prototype_lines = [
            f"- `{item['template_id']}`：`{item['hyperframes_status']}`（仅设计候选，不能阻断外部研究）"
            for item in report.get("local_candidates") or []
            if not item.get("qualified_for_reuse")
        ]
        candidate_lines = [
            f"- `{item['id']}`：`{item['repository']}/{item['path']}`（{item['status']}）"
            for item in report.get("external_candidates") or []
        ]
        source_lines = [
            f"- `{item['id']}`：{item['license']} / {item['usage_policy']}"
            for item in report["external_sources"]
        ]
        fallback = candidate_lines or source_lines or ["- 未配置外部来源"]
        gate = (
            f"- 实现前至少检查 {report['required_external_candidate_reviews']} 个候选并生成逐镜研究记录\n"
            "- 候选比较后只能选一个最终来源，其他候选只保留拒绝理由\n"
            "- 有目录候选时禁止直接使用 `new:` 或自行制作静态 SVG\n"
            if report.get("research_record_required_before_implementation")
            else "- 目录无外部候选；记录检索结果后才可自建\n"
        )
        prototypes = "\n## 本地未完成候选\n\n" + "\n".join(prototype_lines) if prototype_lines else ""
        result = "- 本地无合格匹配\n" + "\n".join(fallback) + "\n" + gate + prototypes
    return f"""# B-roll 模板选择

- 状态：`{report['status']}`
- 语义结构：`{report['query']['semantic_structure']}`
- 信息项：{report['query']['item_count']}
- 时长：{report['query']['duration_ms']} ms
- 画幅：`{report['query']['aspect_ratio']}`

## 结果

{result}
"""


def main() -> int:
    args = parse_args()
    if args.item_count <= 0 or args.duration_ms <= 0:
        print("item-count 和 duration-ms 必须为正整数", file=sys.stderr)
        return 2
    try:
        index = load(args.index)
        external = load(args.external_sources) if args.external_sources else None
        semantic_mapping = load(args.semantic_map) if args.semantic_map else None
    except (OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    report = select(
        index,
        args.semantic_structure,
        args.item_count,
        args.duration_ms,
        args.aspect_ratio,
        external,
        semantic_mapping,
        args.material_type,
        args.presentation_type,
        args.semantic_pattern,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "out": str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
