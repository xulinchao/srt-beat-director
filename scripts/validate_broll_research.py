#!/usr/bin/env python3
"""Validate mandatory external-skeleton research before custom B-roll implementation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DECISIONS = {
    "port-external-skeleton",
    "study-and-reimplement",
    "custom-after-external-review",
}
FITS = {"selected", "partial", "rejected"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visual-plan", required=True, type=Path)
    parser.add_argument("--template-index", required=True, type=Path)
    parser.add_argument("--semantic-map", required=True, type=Path)
    parser.add_argument("--research-dir", required=True, type=Path)
    parser.add_argument("--repositories-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def candidate_catalog(mapping: dict) -> dict[str, dict[str, dict]]:
    return {
        str(structure.get("id")): {
            str(candidate.get("id")): candidate
            for candidate in structure.get("external_candidates") or []
        }
        for structure in mapping.get("structures") or []
    }


def qualified_local_ids(index: dict) -> set[str]:
    return {
        str(template.get("id"))
        for template in index.get("templates") or []
        if template.get("id")
        and str(template.get("hyperframes_status")) == "animation-verified"
        and not str(template.get("source_file", "")).lower().endswith(".svg")
    }


def validate(
    plan: dict,
    template_index: dict,
    semantic_map: dict,
    research_dir: Path,
    repositories_root: Path,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    checked_shots: list[str] = []
    local_ids = qualified_local_ids(template_index)
    catalogs = candidate_catalog(semantic_map)

    for shot in plan.get("shots") or []:
        if not (
            shot.get("screen_role") == "B"
            and shot.get("material_type") == "no-material"
            and shot.get("presentation_type") == "infographic"
        ):
            continue

        shot_id = str(shot.get("id") or "unknown")
        template_id = str(shot.get("template_id") or "")
        if template_id in local_ids:
            continue

        structure = str(shot.get("semantic_structure") or "")
        available = catalogs.get(structure, {})
        if not available:
            warnings.append(f"{shot_id} 的 {structure} 没有登记外部候选，允许单独说明后自建")
            continue

        record_path = research_dir / f"{shot_id}.json"
        if not record_path.is_file():
            errors.append(f"{shot_id} 缺少外部骨架研究记录：{record_path}")
            continue
        try:
            record = load(record_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{shot_id} 研究记录不可读：{exc}")
            continue

        checked_shots.append(shot_id)
        if record.get("shot_id") != shot_id:
            errors.append(f"{shot_id} 研究记录 shot_id 不一致")
        expected_selector = f"planning/template-selection/{shot_id}.json"
        if record.get("selector_report") != expected_selector:
            errors.append(f"{shot_id} selector_report 应为 {expected_selector}")
            selector_candidate_ids: set[str] = set()
        else:
            selector_path = research_dir.parent.parent / expected_selector
            if not selector_path.is_file():
                errors.append(f"{shot_id} 缺少模板选择报告：{selector_path}")
                selector_candidate_ids = set()
            else:
                try:
                    selector = load(selector_path)
                except (OSError, json.JSONDecodeError) as exc:
                    errors.append(f"{shot_id} 模板选择报告不可读：{exc}")
                    selector_candidate_ids = set()
                else:
                    if selector.get("status") != "external-research-required":
                        errors.append(f"{shot_id} 模板选择报告未进入 external-research-required")
                    if (selector.get("query") or {}).get("semantic_structure") != structure:
                        errors.append(f"{shot_id} 模板选择报告的 semantic_structure 不一致")
                    if not selector.get("research_record_required_before_implementation"):
                        errors.append(f"{shot_id} 模板选择报告没有开启外部研究门")
                    selector_candidate_ids = {
                        str(item.get("id")) for item in selector.get("external_candidates") or []
                    }
        decision = record.get("decision")
        if decision not in DECISIONS:
            errors.append(f"{shot_id} 缺少有效 decision")

        inspected = record.get("inspected_candidates")
        if not isinstance(inspected, list):
            errors.append(f"{shot_id} inspected_candidates 必须为数组")
            inspected = []
        required_count = min(2, len(available))
        if len(inspected) < required_count:
            errors.append(f"{shot_id} 至少检查 {required_count} 个外部候选")

        inspected_ids: set[str] = set()
        for position, item in enumerate(inspected, start=1):
            candidate_id = str(item.get("id") or "")
            prefix = f"{shot_id} 候选 {position}"
            if not candidate_id or candidate_id not in available:
                errors.append(f"{prefix} 不在 {structure} 的外部候选目录中：{candidate_id}")
                continue
            if candidate_id not in selector_candidate_ids:
                errors.append(f"{prefix} 不在逐镜模板选择报告中：{candidate_id}")
            if candidate_id in inspected_ids:
                errors.append(f"{shot_id} 重复检查候选：{candidate_id}")
            inspected_ids.add(candidate_id)
            expected = available[candidate_id]
            if item.get("repository") != expected.get("repository"):
                errors.append(f"{prefix} repository 与目录不一致")
            if item.get("shot_card") != expected.get("path"):
                errors.append(f"{prefix} shot_card 与目录不一致")
            source_root = repositories_root / str(expected.get("repository"))
            shot_card = source_root / str(expected.get("path"))
            if not shot_card.is_file():
                errors.append(f"{prefix} 镜头卡不存在：{shot_card}")
            if item.get("license") != expected.get("license"):
                errors.append(f"{prefix} license 与目录不一致")
            fit = item.get("fit")
            if fit not in FITS:
                errors.append(f"{prefix} 缺少有效 fit")
            if not str(item.get("assessment") or "").strip():
                errors.append(f"{prefix} 缺少 assessment")
            implementation_files = item.get("implementation_files")
            if expected.get("status") == "port-required":
                if not isinstance(implementation_files, list) or not implementation_files:
                    errors.append(f"{prefix} 为 port-required，但没有 implementation_files")
                else:
                    for relative in implementation_files:
                        implementation = source_root / str(relative)
                        if not implementation.is_file():
                            errors.append(f"{prefix} 实现文件不存在：{implementation}")

        skeleton = record.get("extracted_skeleton") or {}
        for key in ("element_relation", "main_motion"):
            if not str(skeleton.get(key) or "").strip():
                errors.append(f"{shot_id} extracted_skeleton 缺少 {key}")
        phases = skeleton.get("phase_order")
        if not isinstance(phases, list) or len([value for value in phases if str(value).strip()]) < 3:
            errors.append(f"{shot_id} extracted_skeleton.phase_order 至少需要三个阶段")

        selected = record.get("selected_candidate")
        if decision in {"port-external-skeleton", "study-and-reimplement"}:
            if not selected or selected not in inspected_ids:
                errors.append(f"{shot_id} 决策为 {decision}，但 selected_candidate 未被检查")
            if selected and template_id != f"external:{selected}":
                errors.append(f"{shot_id} template_id 应为 external:{selected}")
        elif decision == "custom-after-external-review":
            if selected is not None:
                errors.append(f"{shot_id} 自建决策的 selected_candidate 必须为 null")
            if not template_id.startswith("new:"):
                errors.append(f"{shot_id} 自建决策的 template_id 必须以 new: 开头")
            if not str(record.get("custom_reason") or "").strip():
                errors.append(f"{shot_id} 自建决策缺少 custom_reason")
            principles = record.get("borrowed_motion_principles")
            if not isinstance(principles, list) or not any(str(value).strip() for value in principles):
                errors.append(f"{shot_id} 自建决策缺少 borrowed_motion_principles")
            for item in inspected:
                if not str(item.get("rejection_reason") or "").strip():
                    errors.append(f"{shot_id} 自建前必须逐项写明 rejection_reason：{item.get('id')}")

    return {
        "schema_version": "0.1",
        "status": "pass" if not errors else "fail",
        "summary": {"checked_shot_count": len(checked_shots), "checked_shots": checked_shots},
        "errors": errors,
        "warnings": warnings,
    }


def markdown(report: dict) -> str:
    errors = report["errors"] or ["无"]
    warnings = report["warnings"] or ["无"]
    return "\n".join(
        [
            "# B-roll 外部骨架研究校验",
            "",
            f"- 状态：`{report['status']}`",
            f"- 已检查镜头：{', '.join(report['summary']['checked_shots']) or '无'}",
            "",
            "## 阻塞项",
            "",
            *(f"- {value}" for value in errors),
            "",
            "## 提醒",
            "",
            *(f"- {value}" for value in warnings),
            "",
        ]
    )


def main() -> int:
    args = parse_args()
    try:
        report = validate(
            load(args.visual_plan),
            load(args.template_index),
            load(args.semantic_map),
            args.research_dir,
            args.repositories_root,
        )
    except (OSError, json.JSONDecodeError) as exc:
        print(str(exc))
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "out": str(args.out)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
