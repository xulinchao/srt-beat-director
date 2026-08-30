#!/usr/bin/env python3
"""Validate content analysis and visual-plan coverage against a preflight report."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


CANONICAL_SEMANTIC_STRUCTURES = {
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
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--content-analysis", required=True, type=Path)
    parser.add_argument("--visual-plan", required=True, type=Path)
    parser.add_argument("--template-index", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_units(
    label: str,
    units: list[dict],
    cues_by_id: dict[int, dict],
    expected_ids: list[int],
    errors: list[str],
) -> None:
    covered: list[int] = []
    previous_start = -1

    for position, unit in enumerate(units, start=1):
        unit_id = unit.get("id", f"{label}-{position}")
        cue_ids = unit.get("cue_ids") or []
        covered.extend(cue_ids)
        if not cue_ids:
            errors.append(f"{unit_id} 没有 cue_ids")
            continue
        missing = [cue_id for cue_id in cue_ids if cue_id not in cues_by_id]
        if missing:
            errors.append(f"{unit_id} 引用了不存在的 cue：{missing}")
            continue

        cues = [cues_by_id[cue_id] for cue_id in cue_ids]
        expected_start = cues[0]["start_ms"]
        expected_end = cues[-1]["end_ms"]
        expected_text = "\n".join(cue["text"] for cue in cues)
        if unit.get("start_ms") != expected_start:
            errors.append(f"{unit_id} start_ms 应为 {expected_start}")
        if unit.get("end_ms") != expected_end:
            errors.append(f"{unit_id} end_ms 应为 {expected_end}")
        if unit.get("verbatim_text") != expected_text:
            errors.append(f"{unit_id} verbatim_text 与 SRT 原文不一致")
        if expected_start < previous_start:
            errors.append(f"{unit_id} 顺序逆序")
        previous_start = expected_start

    counts = Counter(covered)
    missing_ids = [cue_id for cue_id in expected_ids if counts[cue_id] == 0]
    duplicate_ids = [cue_id for cue_id in expected_ids if counts[cue_id] > 1]
    if missing_ids:
        errors.append(f"{label} 丢失 cue：{missing_ids}")
    if duplicate_ids:
        errors.append(f"{label} 重复覆盖 cue：{duplicate_ids}")


def markdown(report: dict) -> str:
    errors = report["errors"]
    warnings = report["warnings"]
    error_lines = "\n".join(f"- {value}" for value in errors) if errors else "- 无"
    warning_lines = "\n".join(f"- {value}" for value in warnings) if warnings else "- 无"
    return f"""# 分镜校验报告

- 状态：`{report['status']}`
- SRT cue 数：{report['summary']['cue_count']}
- 语义段数：{report['summary']['segment_count']}
- 镜头数：{report['summary']['shot_count']}
- A/B 镜头：{report['summary']['a_shot_count']} / {report['summary']['b_shot_count']}
- 视觉计划 SHA-256：`{report['files']['visual_plan_sha256']}`

## 阻塞项

{error_lines}

## 提醒

{warning_lines}
"""


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    warnings: list[str] = []

    try:
        preflight = load(args.preflight)
        project = load(args.project)
        content = load(args.content_analysis)
        plan = load(args.visual_plan)
        template_index = load(args.template_index) if args.template_index else None
    except (OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    cues = preflight.get("srt", {}).get("cues", [])
    cues_by_id = {cue["id"]: cue for cue in cues}
    expected_ids = [cue["id"] for cue in cues]
    segments = content.get("semantic_segments", [])
    shots = plan.get("shots", [])

    validate_units("content-analysis", segments, cues_by_id, expected_ids, errors)
    validate_units("visual-plan", shots, cues_by_id, expected_ids, errors)

    template_ids = {
        template.get("id")
        for template in (template_index or {}).get("templates", [])
        if "superseded" not in str(template.get("hyperframes_status", "")).lower()
    }
    role_run: list[str] = []

    for index, shot in enumerate(shots, start=1):
        expected_id = f"S{index:03d}"
        if shot.get("id") != expected_id:
            errors.append(f"镜头编号应连续：位置 {index} 应为 {expected_id}")
        role = shot.get("screen_role")
        if role not in {"A", "B"}:
            errors.append(f"{shot.get('id')} screen_role 只能是 A 或 B")
        role_run.append(role)
        if role == "A" and project.get("a_scene_mode") == "fixed-character-micro-scene":
            if shot.get("a_view") not in {"presenter", "protagonist", "supporting", "first-person"}:
                errors.append(f"{shot.get('id')} 缺少有效 a_view")
        if role == "B" and shot.get("screen_subtype") not in {
            "verified-media",
            "diagram",
            "text-only",
        }:
            errors.append(f"{shot.get('id')} 的 B 子类型无效")
        if role == "B":
            if shot.get("material_type") not in {"verified-media", "no-material", "text-only"}:
                errors.append(f"{shot.get('id')} 缺少有效 material_type")
            if shot.get("presentation_type") not in {"verified-media", "infographic", "text-motion"}:
                errors.append(f"{shot.get('id')} 缺少有效 presentation_type")
            semantic_structure = shot.get("semantic_structure")
            if semantic_structure not in CANONICAL_SEMANTIC_STRUCTURES:
                errors.append(f"{shot.get('id')} semantic_structure 必须使用七类标准结构")
            item_count = shot.get("item_count")
            if not isinstance(item_count, int) or item_count <= 0:
                errors.append(f"{shot.get('id')} item_count 必须为正整数")
            template_id = shot.get("template_id")
            if template_id and not str(template_id).startswith(("new:", "external-research:")):
                if template_index and template_id not in template_ids:
                    errors.append(f"{shot.get('id')} template_id 不存在或已过期：{template_id}")
        if not shot.get("viewer_takeaway"):
            errors.append(f"{shot.get('id')} 缺少 viewer_takeaway")
        design = shot.get("visual_design") or {}
        if not design.get("final_state"):
            errors.append(f"{shot.get('id')} 缺少 final_state")
        if not shot.get("changes"):
            errors.append(f"{shot.get('id')} 缺少有效变化")
        for change in shot.get("changes", []):
            at_ms = change.get("at_ms")
            if not isinstance(at_ms, int) or not shot["start_ms"] <= at_ms <= shot["end_ms"]:
                errors.append(f"{shot.get('id')} 的变化时间 {at_ms} 超出镜头语义边界")

    policy = project.get("timeline_policy") or {}
    expected_policy = {
        "initial_gap": "show-first-shot",
        "inter_shot_gap": "hold-previous-shot",
        "tail_gap": "hold-last-shot",
    }
    for key, value in expected_policy.items():
        if policy.get(key) != value:
            errors.append(f"timeline_policy.{key} 应为 {value}")

    audio_duration = preflight.get("audio", {}).get("duration_ms")
    sample = project.get("sample") or {}
    if isinstance(audio_duration, int) and sample.get("end_ms", 0) > audio_duration:
        errors.append("样片结束时间超过音频时长")
    if isinstance(audio_duration, int) and audio_duration <= 60000:
        if sample.get("start_ms") != 0 or sample.get("end_ms") != audio_duration:
            warnings.append("全片不超过 60 秒，建议低成本样片覆盖完整音频")

    a_count = sum(1 for shot in shots if shot.get("screen_role") == "A")
    b_count = sum(1 for shot in shots if shot.get("screen_role") == "B")
    if a_count == 0 or b_count == 0:
        warnings.append("样片没有同时包含 A 与 B 画面")

    run_exceptions = plan.get("roll_run_exceptions") or []
    run_start = 0
    for position in range(1, len(role_run) + 1):
        if position == len(role_run) or role_run[position] != role_run[run_start]:
            run_length = position - run_start
            if run_length >= 3:
                start_id = shots[run_start].get("id")
                end_id = shots[position - 1].get("id")
                role = role_run[run_start]
                exception = next(
                    (
                        item
                        for item in run_exceptions
                        if item.get("start_shot_id") == start_id
                        and item.get("end_shot_id") == end_id
                        and item.get("screen_role") == role
                    ),
                    None,
                )
                if not exception or not str(exception.get("reason", "")).strip():
                    warnings.append(
                        f"镜头 {run_start + 1}-{position} 连续 {run_length} 个 {role}-roll；请在 roll_run_exceptions 写明语义理由和内部变化"
                    )
            run_start = position

    report = {
        "schema_version": "0.1",
        "status": "pass" if not errors else "fail",
        "files": {
            "project_sha256": sha256(args.project),
            "content_analysis_sha256": sha256(args.content_analysis),
            "visual_plan_sha256": sha256(args.visual_plan),
        },
        "summary": {
            "cue_count": len(cues),
            "segment_count": len(segments),
            "shot_count": len(shots),
            "a_shot_count": a_count,
            "b_shot_count": b_count,
            "audio_duration_ms": audio_duration,
        },
        "errors": errors,
        "warnings": warnings,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "plan-validation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.out_dir / "plan-validation-report.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "out_dir": str(args.out_dir)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    sys.exit(main())
