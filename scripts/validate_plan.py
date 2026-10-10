#!/usr/bin/env python3
"""Validate content analysis and visual-plan coverage against a preflight report."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from broll_expression import validate_reference_confirmation
from broll_runtime import template_status, validate_runtime_decision
from motion_review import motion_mode, validate_motion_plan
from preflight import validate_preflight
from sequence_quality import validate_plan as validate_sequence_plan
from visual_timing import validate_visual_cuts


CANONICAL_SEMANTIC_STRUCTURES = {
    "comparison",
    "aggregation",
    "filtering",
    "hierarchy",
    "causality",
    "replacement",
    "expansion",
}

GENERIC_VISUAL_STRUCTURES = {
    "card",
    "cards",
    "list",
    "infographic",
    "darkui",
    "卡片",
    "三卡",
    "列表",
    "信息图",
    "深色ui",
}


def required_a_roll_change_count(duration_ms: int) -> int:
    """Duration alone does not determine meaningful narrative states."""
    return 1


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


def normalize_text(value: object) -> str:
    return "".join(str(value or "").split())


def normalize_structure(value: object) -> str:
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def validate_broll_structure_variety(
    shots: list[dict],
    exceptions: object,
    errors: list[str],
    warnings: list[str] | None = None,
) -> None:
    """Require concrete structures; flag reuse for semantic QA, not rejection."""
    if warnings is None:
        warnings = []
    if not isinstance(exceptions, list):
        errors.append("broll_structure_exceptions 必须为数组")
        exceptions = []

    previous_brolls: list[dict] = []
    for shot in shots:
        if shot.get("screen_role") != "B":
            continue

        shot_id = str(shot.get("id") or "unknown")
        raw_structure = str(shot.get("visual_structure") or "").strip()
        structure = normalize_structure(raw_structure)
        if not structure:
            errors.append(f"{shot_id} 缺少具体 visual_structure")
        elif structure in GENERIC_VISUAL_STRUCTURES:
            errors.append(f"{shot_id} visual_structure 过于笼统：{raw_structure}")

        design = shot.get("visual_design") or {}
        composition = normalize_structure(design.get("composition"))
        semantic_pattern = normalize_structure(shot.get("semantic_pattern"))
        template_id = normalize_structure(shot.get("template_id"))

        for previous in previous_brolls[-3:]:
            same_structure = bool(structure and structure == previous["structure"])
            same_template_composition = bool(
                template_id
                and composition
                and template_id == previous["template_id"]
                and composition == previous["composition"]
            )
            same_pattern_composition = bool(
                semantic_pattern
                and composition
                and semantic_pattern == previous["semantic_pattern"]
                and composition == previous["composition"]
            )
            if not (same_structure or same_template_composition or same_pattern_composition):
                continue

            exception = next(
                (
                    item
                    for item in exceptions
                    if isinstance(item, dict)
                    and item.get("shot_id") == shot_id
                    and item.get("compared_shot_id") == previous["shot_id"]
                ),
                None,
            )
            if exception and str(exception.get("semantic_reason") or "").strip() and str(
                exception.get("visible_difference") or ""
            ).strip():
                continue
            warnings.append(
                f"{shot_id} 与最近三个 B-roll 中的 {previous['shot_id']} 复用了同一视觉结构；"
                "请审查解释收益，并在 broll_structure_exceptions 记录 semantic_reason 和 visible_difference；无需强制改布局"
            )

        previous_brolls.append(
            {
                "shot_id": shot_id,
                "structure": structure,
                "composition": composition,
                "semantic_pattern": semantic_pattern,
                "template_id": template_id,
            }
        )


def validate_narration_binding(
    *,
    shot: dict,
    changes: list[dict],
    cues_by_id: dict[int, dict],
    errors: list[str],
) -> None:
    shot_id = str(shot.get("id") or "unknown")
    beats = shot.get("narration_beats") or []
    if not isinstance(beats, list) or not beats:
        errors.append(f"{shot_id} 缺少 narration_beats，无法绑定旁白内部节奏")
        return
    if len(beats) != len(changes):
        errors.append(
            f"{shot_id} changes 与 narration_beats 必须一一对应，"
            f"当前为 {len(changes)} / {len(beats)}"
        )

    previous_at_ms = -1
    shot_cue_ids = set(shot.get("cue_ids") or [])
    for position, beat in enumerate(beats, start=1):
        beat_label = f"{shot_id} narration_beat-{position}"
        if not isinstance(beat, dict):
            errors.append(f"{beat_label} 必须为对象")
            continue
        cue_ids = beat.get("cue_ids") or []
        if not isinstance(cue_ids, list) or not cue_ids:
            errors.append(f"{beat_label} 缺少 cue_ids")
            continue
        if any(cue_id not in shot_cue_ids for cue_id in cue_ids):
            errors.append(f"{beat_label} cue_ids 必须属于当前镜头")
        missing = [cue_id for cue_id in cue_ids if cue_id not in cues_by_id]
        if missing:
            errors.append(f"{beat_label} 引用了不存在的 cue：{missing}")
            continue
        beat_cues = [cues_by_id[cue_id] for cue_id in cue_ids]
        at_ms = beat.get("at_ms")
        expected_at_ms = beat_cues[0]["start_ms"]
        if at_ms != expected_at_ms:
            errors.append(f"{beat_label} at_ms 应绑定首个 cue 起点 {expected_at_ms}")
        if isinstance(at_ms, int) and at_ms <= previous_at_ms:
            errors.append(f"{beat_label} at_ms 必须严格递增")
        if isinstance(at_ms, int):
            previous_at_ms = at_ms
        expected_text = "\n".join(cue["text"] for cue in beat_cues)
        actual = normalize_text(beat.get("trigger_text"))
        expected = normalize_text(expected_text)
        # 允许：完全等于 cue 全文拼接，或者是 cue 全文的连续子串；空值不算片段
        if not actual or (actual != expected and actual not in expected):
            errors.append(f"{beat_label} trigger_text 与绑定 cue 原文不一致（须为 cue 全文或其连续片段）")
        for key in ("information_change", "state_after"):
            if not str(beat.get(key) or "").strip():
                errors.append(f"{beat_label} 缺少 {key}")
        if position <= len(changes):
            change_at_ms = changes[position - 1].get("at_ms")
            if change_at_ms != at_ms:
                errors.append(
                    f"{shot_id} change-{position} 与 narration_beat-{position} "
                    f"时间不一致：{change_at_ms} / {at_ms}"
                )


def validate_units(
    label: str,
    units: list[dict],
    cues_by_id: dict[int, dict],
    expected_ids: list[int],
    errors: list[str],
) -> None:
    covered: list[int] = []
    previous_start = -1
    previous_end = -1
    cue_positions = {cue_id: index for index, cue_id in enumerate(expected_ids)}

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

        positions = [cue_positions[cue_id] for cue_id in cue_ids]
        if positions != list(range(positions[0], positions[0] + len(positions))):
            errors.append(f"{unit_id} cue_ids 必须按原始顺序连续覆盖，不能跳号或逆序")

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
        if expected_end <= expected_start:
            errors.append(f"{unit_id} 语义区间无效")
        if expected_start < previous_end:
            errors.append(f"{unit_id} 与前一个语义区间重叠")
        previous_start = expected_start
        previous_end = expected_end

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

    errors.extend(validate_preflight(preflight, project, args.project.parent.parent))
    cues = preflight.get("srt", {}).get("cues", [])
    cues_by_id = {cue["id"]: cue for cue in cues}
    expected_ids = [cue["id"] for cue in cues]
    segments = content.get("semantic_segments", [])
    shots = plan.get("shots", [])
    motion_report = validate_motion_plan(plan, project)
    errors.extend(motion_report["errors"])
    warnings.extend(motion_report["warnings"])

    sequence_report = validate_sequence_plan(plan, project)
    errors.extend(sequence_report["errors"])
    warnings.extend(sequence_report["warnings"])

    validate_units("content-analysis", segments, cues_by_id, expected_ids, errors)
    validate_units("visual-plan", shots, cues_by_id, expected_ids, errors)

    template_ids = {
        template.get("id")
        for template in (template_index or {}).get("templates", [])
        if "superseded" not in template_status(template).lower()
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
        if role == "A":
            if shot.get("a_view") not in {"presenter", "protagonist", "supporting", "first-person"}:
                errors.append(f"{shot.get('id')} 缺少有效 a_view")
        if role == "B" and shot.get("screen_subtype") not in {
            "verified-media",
            "diagram",
            "text-only",
            "scene",
        }:
            errors.append(f"{shot.get('id')} 的 B 子类型无效")
        if role == "B":
            if shot.get("material_type") not in {"verified-media", "no-material", "text-only"}:
                errors.append(f"{shot.get('id')} 缺少有效 material_type")
            if shot.get("presentation_type") not in {"verified-media", "infographic", "text-motion", "scene"}:
                errors.append(f"{shot.get('id')} 缺少有效 presentation_type")
            if shot.get("presentation_type") == "scene" and (
                shot.get("material_type") != "no-material" or shot.get("screen_subtype") != "scene"
            ):
                errors.append(f"{shot.get('id')} 生成场景必须使用 no-material + scene，不能标为真实证据")
            semantic_structure = shot.get("semantic_structure")
            if semantic_structure not in CANONICAL_SEMANTIC_STRUCTURES:
                errors.append(f"{shot.get('id')} semantic_structure 必须使用七类标准结构")
            item_count = shot.get("item_count")
            if not isinstance(item_count, int) or item_count <= 0:
                errors.append(f"{shot.get('id')} item_count 必须为正整数")
            template_id = str(shot.get("template_id") or "")
            if shot.get("material_type") == "no-material" and shot.get("presentation_type") == "infographic" and not template_id:
                errors.append(f"{shot.get('id')} 的无素材信息动效缺少 template_id")
            if template_id and not template_id.startswith(("new:", "external-research:", "external:")):
                if template_index and template_id not in template_ids:
                    errors.append(f"{shot.get('id')} template_id 不存在或已过期：{template_id}")
            if template_id.startswith("external-research:"):
                production = shot.get("production") or {}
                if production.get("asset_status") in {"in-progress", "ready"}:
                    errors.append(f"{shot.get('id')} 外部研究尚未完成，不能标记为 {production.get('asset_status')}")
            expected_record = f"planning/broll-research/{shot.get('id')}.json"
            if template_id.startswith("new:"):
                research_path = args.project.parent.parent / expected_record
                if shot.get("broll_research_record") != expected_record or not research_path.is_file():
                    errors.append(f"{shot.get('id')} 自建前必须有 broll_research_record={expected_record} 及实际研究文件")
            if template_id.startswith("external:"):
                selector_path = args.project.parent.parent / f"planning/template-selection/{shot.get('id')}.json"
                research_path = args.project.parent.parent / expected_record
                try:
                    selector_report = load(selector_path) if selector_path.is_file() else {}
                except (OSError, json.JSONDecodeError):
                    selector_report = {}
                if selector_report.get("status") == "candidates-recalled" and not research_path.is_file():
                    if shot.get("broll_research_record"):
                        errors.append(f"{shot.get('id')} 参考仓库快路径不能声明不存在的 broll_research_record")
                    errors.extend(f"{shot.get('id')} {message}" for message in validate_reference_confirmation(
                        shot, selector_report, args.project.parent.parent,
                        Path(project["repositories_root"]) if project.get("repositories_root") else None))
                elif shot.get("broll_research_record") == expected_record and research_path.is_file():
                    pass
                else:
                    errors.append(f"{shot.get('id')} 使用 {template_id} 前必须填写 broll_research_record={expected_record}")
        if not shot.get("viewer_takeaway"):
            errors.append(f"{shot.get('id')} 缺少 viewer_takeaway")
        design = shot.get("visual_design") or {}
        if not design.get("final_state"):
            errors.append(f"{shot.get('id')} 缺少 final_state")
        changes = shot.get("changes") or []
        if not changes:
            errors.append(f"{shot.get('id')} 缺少有效变化")
        validate_narration_binding(
            shot=shot,
            changes=changes,
            cues_by_id=cues_by_id,
            errors=errors,
        )
        if role == "A":
            duration_ms = shot.get("end_ms", 0) - shot.get("start_ms", 0)
            required_changes = required_a_roll_change_count(duration_ms)
            if motion_mode(shot) == "single-state" and not str(shot.get("static_reason") or "").strip():
                errors.append(f"{shot.get('id')} 单状态 A-roll 必须填写 static_reason")
            if len(changes) < required_changes:
                errors.append(
                    f"{shot.get('id')} 时长 {duration_ms}ms 的 A-roll 至少需要 "
                    f"{required_changes} 个内容驱动的动作状态，当前为 {len(changes)} 个"
                )
            narration_beats = shot.get("narration_beats") or []
            if len(narration_beats) < required_changes:
                errors.append(
                    f"{shot.get('id')} 至少需要 {required_changes} 个 narration_beats，"
                    f"用于把 A-roll 动作绑定到旁白短语"
                )
        for change in changes:
            at_ms = change.get("at_ms")
            if not isinstance(at_ms, int) or not shot["start_ms"] <= at_ms <= shot["end_ms"]:
                errors.append(f"{shot.get('id')} 的变化时间 {at_ms} 超出镜头语义边界")
            if not str(change.get("event") or change.get("description") or "").strip():
                errors.append(f"{shot.get('id')} 的变化 {at_ms} 缺少事件描述")
        if not shot.get("materials"):
            errors.append(f"{shot.get('id')} 缺少 materials")
        production = shot.get("production") or {}
        if not str(production.get("primary_tool") or "").strip():
            errors.append(f"{shot.get('id')} 缺少 production.primary_tool")
        if (
            role == "B"
            and shot.get("material_type") == "no-material"
            and shot.get("presentation_type") == "infographic"
            and production.get("primary_tool") not in {
                "hyperframes",
                "remotion",
                "chatcut-motion-graphics",
                "comfyui-minimax-h3-fl2v",
                "comfyui-minimax-h3-i2v",
                "comfyui-minimax-h3-r2v",
                "comfyui-minimax-h3-multi-reference",
            }
        ):
            errors.append(f"{shot.get('id')} 的无素材信息动画必须选择可用的逐镜动效工具")
        errors.extend(validate_runtime_decision(shot, args.project.parent.parent, template_index))
        fallback_tools = production.get("fallback_tools")
        if not isinstance(fallback_tools, list):
            errors.append(f"{shot.get('id')} production.fallback_tools 必须为数组")
        asset_status = production.get("asset_status")
        if asset_status not in {
            "available",
            "to-generate",
            "in-progress",
            "ready",
            "failed",
            "gap",
        }:
            errors.append(f"{shot.get('id')} 缺少有效 production.asset_status")
        if asset_status in {"failed", "gap"} and not str(production.get("asset_gap") or "").strip():
            errors.append(f"{shot.get('id')} 的素材状态为 {asset_status}，但没有说明 asset_gap")

    structure_exceptions = plan.get("broll_structure_exceptions", [])
    if structure_exceptions is None:
        structure_exceptions = []
    validate_broll_structure_variety(shots, structure_exceptions, errors, warnings)

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
    errors.extend(validate_visual_cuts(plan, (project.get("video") or {}).get("fps"), audio_duration))
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
