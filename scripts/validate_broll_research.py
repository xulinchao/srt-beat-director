#!/usr/bin/env python3
"""Validate mandatory external-skeleton research before custom B-roll implementation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from broll_runtime import RUNTIMES, template_runtime, template_status
from broll_expression import (MATCHING_POLICY, validate_expression,
                              validate_expanded_search, validate_reference_confirmation)


DECISIONS = {
    "reuse-native-source",
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
        and template_status(template) == "animation-verified"
        and template_runtime(template) in RUNTIMES
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
    global_catalog = {key: value for catalog in catalogs.values() for key, value in catalog.items()}
    if plan.get("broll_matching_policy") not in (None, MATCHING_POLICY):
        errors.append("broll_matching_policy 无效，不能降级绕过表达选型")

    for shot in plan.get("shots") or []:
        if not (
            shot.get("screen_role") == "B"
            and shot.get("material_type") == "no-material"
            and shot.get("presentation_type") == "infographic"
        ):
            continue

        shot_id = str(shot.get("id") or "unknown")
        template_id = str(shot.get("template_id") or "")
        structure = str(shot.get("semantic_structure") or "")
        expected_selector = f"planning/template-selection/{shot_id}.json"
        selector_path = research_dir.parent.parent / expected_selector
        try:
            initial_selector = load(selector_path) if selector_path.is_file() else {}
        except (OSError, json.JSONDecodeError):
            initial_selector = {}
        if initial_selector.get("matching_policy") not in (None, MATCHING_POLICY):
            errors.append(f"{shot_id} matching_policy 无效")
        if initial_selector and initial_selector.get("status") not in {
                "local-match", "candidates-recalled", "external-research-required"}:
            errors.append(f"{shot_id} 模板选择报告状态无效：{initial_selector.get('status')}")
        record_path = research_dir / f"{shot_id}.json"
        if template_id in local_ids:
            errors.extend(f"{shot_id} {message}" for message in validate_expression(initial_selector.get("expression_brief")))
            selected_local = initial_selector.get("selected") or {}
            if (initial_selector.get("matching_policy") != MATCHING_POLICY
                    or initial_selector.get("status") != "local-match"
                    or selected_local.get("template_id") != template_id
                    or not selected_local.get("qualified_for_reuse")
                    or not selected_local.get("capacity_fit")
                    or not selected_local.get("matched_motion_tags")):
                errors.append(f"{shot_id} 本地认证 ID 不能绕过当前表达与容量选型；须有对应合格选择报告")
            continue

        if (initial_selector.get("status") == "candidates-recalled"
                and template_id.startswith("external:") and not record_path.is_file()):
            checked_shots.append(shot_id)
            if shot.get("broll_research_record"):
                errors.append(f"{shot_id} 参考仓库快路径不能声明不存在的 broll_research_record")
            project_config_path = research_dir.parent.parent / "config/project.json"
            try:
                project_config = load(project_config_path)
            except (OSError, json.JSONDecodeError):
                project_config = {}
            configured_root = project_config.get("repositories_root")
            errors.extend(f"{shot_id} {message}" for message in validate_reference_confirmation(
                shot, initial_selector, research_dir.parent.parent,
                Path(configured_root) if configured_root else None))
            continue

        if not record_path.is_file():
            errors.append(f"{shot_id} 缺少外部骨架研究记录：{record_path}")
            continue
        try:
            record = load(record_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{shot_id} 研究记录不可读：{exc}")
            continue

        checked_shots.append(shot_id)
        discovered = record.get("discovered_candidates") or []
        searched_ids: set[str] = set()
        available = dict(global_catalog)
        if not isinstance(discovered, list):
            errors.append(f"{shot_id} discovered_candidates 必须为数组")
            discovered = []
        for item in discovered:
            if not isinstance(item, dict) or not item.get("id"):
                errors.append(f"{shot_id} 新发现候选缺少 id")
                continue
            if item["id"] in available:
                errors.append(f"{shot_id} 新发现候选不得覆盖目录 ID：{item['id']}")
                continue
            if any(not str(item.get(k) or "").strip()
                   for k in ("repository", "path", "license", "status", "source_url")):
                errors.append(f"{shot_id} 新发现候选缺少来源、路径、许可证或状态：{item['id']}")
                continue
            if not str(item["source_url"]).startswith(("https://", "http://")):
                errors.append(f"{shot_id} 新发现候选 source_url 必须是原始来源链接")
            if item["status"] not in {"available", "port-required", "reference-only", "structure-study-only"}:
                errors.append(f"{shot_id} 新发现候选 status 无效")
            available[item["id"]] = item
        for search in record.get("expanded_search") or []:
            if isinstance(search, dict) and isinstance(search.get("candidate_ids"), list):
                searched_ids.update(value for value in search["candidate_ids"] if isinstance(value, str) and value.strip())
        for candidate_id in searched_ids:
            if candidate_id not in available:
                errors.append(f"{shot_id} 搜索返回候选缺少目录或发现记录：{candidate_id}")
        expression = initial_selector.get("expression_brief")
        errors.extend(f"{shot_id} {message}" for message in validate_expression(expression))
        if record.get("expression_brief") != expression:
            errors.append(f"{shot_id} 研究记录的 expression_brief 必须与选择报告一致")
        if initial_selector.get("matching_policy") != MATCHING_POLICY:
            errors.append(f"{shot_id} 新选型必须声明 matching_policy={MATCHING_POLICY}")
        if record.get("shot_id") != shot_id:
            errors.append(f"{shot_id} 研究记录 shot_id 不一致")
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
                    if selector.get("selection_policy") != "single-source-per-shot":
                        errors.append(f"{shot_id} 模板选择报告必须声明 selection_policy=single-source-per-shot")
                    if selector.get("status") not in {"external-research-required", "candidates-recalled"}:
                        errors.append(f"{shot_id} 模板选择报告未进入候选召回或外部研究状态")
                    if (selector.get("query") or {}).get("semantic_structure") != structure:
                        errors.append(f"{shot_id} 模板选择报告的 semantic_structure 不一致")
                    if selector.get("status") == "external-research-required" and not selector.get("research_record_required_before_implementation"):
                        errors.append(f"{shot_id} 模板选择报告没有开启外部研究门")
                    if selector.get("status") == "candidates-recalled" and not selector.get("reference_confirmation_or_research_required_before_implementation"):
                        errors.append(f"{shot_id} 参考仓库候选报告没有开启确认或研究门")
                    selector_candidate_ids = {
                        str(item.get("id")) for item in selector.get("external_candidates") or []
                    }
                    selector_candidate_ids.update(str(item["id"]) for item in discovered if isinstance(item, dict) and item.get("id"))
                    selector_candidate_ids.update(searched_ids)
        decision = record.get("decision")
        if decision not in DECISIONS:
            errors.append(f"{shot_id} 缺少有效 decision")
        if record.get("source_policy") != "single-source":
            errors.append(f"{shot_id} 必须声明 source_policy=single-source")

        inspected = record.get("inspected_candidates")
        if not isinstance(inspected, list):
            errors.append(f"{shot_id} inspected_candidates 必须为数组")
            inspected = []
        required_count = 1 if decision != "custom-after-external-review" else 0
        if len(inspected) < required_count:
            errors.append(f"{shot_id} 至少检查 {required_count} 个外部候选")

        inspected_ids: set[str] = set()
        for position, item in enumerate(inspected, start=1):
            candidate_id = str(item.get("id") or "")
            prefix = f"{shot_id} 候选 {position}"
            if not candidate_id or candidate_id not in available:
                errors.append(f"{prefix} 不在可核对的外部候选目录或发现记录中：{candidate_id}")
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
            if (not source_root.resolve().is_relative_to(repositories_root.resolve())
                    or not shot_card.resolve().is_relative_to(source_root.resolve())):
                errors.append(f"{prefix} 仓库或镜头卡路径越界")
                continue
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
            if expected.get("status") in ("port-required", "available"):
                if not isinstance(implementation_files, list) or not implementation_files:
                    errors.append(f"{prefix} status 为 {expected.get('status')}，但没有 implementation_files")
                else:
                    for relative in implementation_files:
                        implementation = source_root / str(relative)
                        if not implementation.resolve().is_relative_to(source_root.resolve()):
                            errors.append(f"{prefix} 实现文件路径越界：{relative}")
                        elif not implementation.is_file():
                            errors.append(f"{prefix} 实现文件不存在：{implementation}")

        for candidate_id in searched_ids - inspected_ids:
            errors.append(f"{shot_id} 扩大搜索发现的相关候选尚未评估：{candidate_id}")

        skeleton = record.get("extracted_skeleton") or {}
        for key in ("element_relation", "main_motion"):
            if not str(skeleton.get(key) or "").strip():
                errors.append(f"{shot_id} extracted_skeleton 缺少 {key}")
        phases = skeleton.get("phase_order")
        if not isinstance(phases, list) or len([value for value in phases if str(value).strip()]) < 3:
            errors.append(f"{shot_id} extracted_skeleton.phase_order 至少需要三个阶段")

        selected = record.get("selected_candidate")
        if decision in {"reuse-native-source", "study-and-reimplement"}:
            if not selected or selected not in inspected_ids:
                errors.append(f"{shot_id} 决策为 {decision}，但 selected_candidate 未被检查")
            if selected and template_id != f"external:{selected}":
                errors.append(f"{shot_id} template_id 应为 external:{selected}")
            selected_items = [item for item in inspected if item.get("fit") == "selected"]
            if len(selected_items) != 1 or selected_items[0].get("id") != selected:
                errors.append(f"{shot_id} 必须且只能有一个 fit=selected，且必须等于 selected_candidate")
            if len(selected_items) == 1:
                preview = selected_items[0].get("preview_evidence") or {}
                if preview.get("status") != "inspected" or not str(preview.get("artifact") or "").strip():
                    errors.append(f"{shot_id} 选中来源必须记录实际预览 preview_evidence，不只读源码")
                else:
                    project_root = research_dir.parent.parent.resolve()
                    artifact = project_root / str(preview["artifact"])
                    if Path(str(preview["artifact"])).is_absolute() or not artifact.resolve().is_relative_to(project_root):
                        errors.append(f"{shot_id} 预览证据须为项目内相对路径")
                    elif not artifact.is_file():
                        errors.append(f"{shot_id} 选中来源的预览证据文件不存在")
            for item in inspected:
                if item.get("id") != selected and not str(item.get("rejection_reason") or "").strip():
                    errors.append(f"{shot_id} 未选候选必须写明 rejection_reason：{item.get('id')}")
            source = record.get("implementation_source") or {}
            if source.get("candidate_id") != selected:
                errors.append(f"{shot_id} implementation_source.candidate_id 必须等于 selected_candidate")
            if decision == "reuse-native-source":
                runtime = (shot.get("production") or {}).get("primary_tool")
                runtime_decision = (shot.get("production") or {}).get("runtime_decision") or {}
                if runtime not in RUNTIMES or source.get("runtime") != runtime:
                    errors.append(f"{shot_id} 原生研究来源 runtime 必须等于 primary_tool")
                if runtime_decision.get("mode") != "native-reuse" or runtime_decision.get("source_runtime") != runtime:
                    errors.append(f"{shot_id} 原生研究决策必须与 runtime_decision 一致")
        elif decision == "custom-after-external-review":
            errors.extend(f"{shot_id} {message}" for message in validate_expanded_search(record.get("expanded_search")))
            if initial_selector.get("status") == "candidates-recalled":
                reviews = record.get("reference_candidate_reviews")
                recalled = {str(item.get("id")) for item in initial_selector.get("reference_candidates") or []
                            if isinstance(item, dict) and item.get("id")}
                if not isinstance(reviews, list) or not reviews:
                    errors.append(f"{shot_id} 自建前须记录实际检查的参考仓库候选及拒绝理由")
                else:
                    seen_reviews: set[str] = set()
                    for review in reviews:
                        if not isinstance(review, dict):
                            errors.append(f"{shot_id} reference_candidate_reviews 每项须为对象")
                            continue
                        candidate_id = review.get("candidate_id")
                        if not isinstance(candidate_id, str):
                            errors.append(f"{shot_id} 参考仓库拒绝记录缺少 candidate_id")
                            continue
                        if candidate_id not in recalled or candidate_id in seen_reviews:
                            errors.append(f"{shot_id} 参考仓库拒绝记录的候选 ID 无效或重复：{candidate_id}")
                        seen_reviews.add(candidate_id)
                        if not str(review.get("rejection_reason") or "").strip():
                            errors.append(f"{shot_id} 参考仓库候选缺少实际拒绝理由：{candidate_id}")
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
                if item.get("fit") != "rejected":
                    errors.append(f"{shot_id} 自建前不能保留 selected 或 partial 候选，须先完成适配评估")
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
