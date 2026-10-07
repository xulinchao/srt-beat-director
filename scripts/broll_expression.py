"""Small, explicit motion descriptors; this is not a prose/embedding matcher."""

from __future__ import annotations

from pathlib import Path
from broll_retrieval import CAPABILITIES, constraint_check


MATCHING_POLICY = "expression-first-v1"

REFERENCE_FRAMEWORKS = {
    "video-shotcraft": "remotion",
    "hyperframes-launches": "hyperframes",
    "hyperframes": "hyperframes",
    "remotion": "remotion",
    "remocn": "remotion",
    "motion-canvas": "motion-canvas",
    "motion-canvas-examples": "motion-canvas",
    "vibe-motion-skills": "remotion",
}


def validate_expression(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["expression_brief 必须为对象"]
    errors = []
    for key in ("element_relation", "main_motion"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            errors.append(f"expression_brief 缺少 {key}")
    for key, minimum in (("subjects", 1), ("phase_order", 2), ("invariants", 1),
                         ("motion_tags", 1), ("search_queries", 2)):
        items = value.get(key)
        if (not isinstance(items, list) or len(items) < minimum
                or any(not isinstance(item, str) or not item.strip() for item in items)):
            errors.append(f"expression_brief.{key} 至少需要 {minimum} 个非空字符串")
    requirements = value.get("requirements", {})
    if not isinstance(requirements, dict) or any(
        key not in CAPABILITIES or not isinstance(item, bool) for key, item in requirements.items()
    ):
        errors.append("expression_brief.requirements 只能包含约定的布尔型运动约束")
    return errors


def motion_matches(expression: dict | None, candidate: dict) -> list[str]:
    requested = {tag.strip().lower() for tag in (expression or {}).get("motion_tags", [])}
    provided = {tag.strip().lower() for tag in (candidate.get("motion_tags") or []) if isinstance(tag, str)}
    return sorted(requested & provided)


def validate_expanded_search(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["自建前缺少 expanded_search 搜索记录"]
    errors = []
    sources, queries = set(), set()
    for item in value:
        if not isinstance(item, dict):
            errors.append("expanded_search 每项必须为对象")
            continue
        if any(not isinstance(item.get(key), str) or not item[key].strip()
               for key in ("source", "query", "outcome")):
            errors.append("expanded_search 每项须有 source、query、outcome")
            continue
        sources.add(item["source"].strip())
        queries.add(item["query"].strip().lower())
        candidate_ids = item.get("candidate_ids")
        if (not isinstance(candidate_ids, list)
                or any(not isinstance(value, str) or not value.strip() for value in candidate_ids)):
            errors.append("expanded_search.candidate_ids 必须为非空 ID 字符串数组；无结果用空数组")
    if len(sources) < 2 or len(queries) < 2:
        errors.append("自建前必须用至少两种动作查询，覆盖至少两个搜索来源；目录拒绝不算扩大搜索")
    return errors


def validate_reference_confirmation(
    shot: dict, selector: dict, project_root: Path, repositories_root: Path | None,
) -> list[str]:
    """Check a reviewed local-repository source against the recalled candidate.

    This verifies the evidence chain, not whether the motion is artistically suitable.
    """
    errors: list[str] = []
    if selector.get("status") != "candidates-recalled":
        return ["参考仓库快路径要求 candidates-recalled 选择报告"]
    if selector.get("schema_version") != "0.2":
        errors.append("参考仓库快路径要求 0.2 版选择报告")
    if selector.get("selection_policy") != "single-source-per-shot":
        errors.append("参考仓库选择报告缺少 single-source-per-shot")
    if selector.get("matching_policy") != MATCHING_POLICY:
        errors.append("参考仓库选择报告缺少 expression-first-v1")
    errors.extend(validate_expression(selector.get("expression_brief")))
    query = selector.get("query") or {}
    if (query.get("semantic_structure") != shot.get("semantic_structure")
            or query.get("item_count") != shot.get("item_count")):
        errors.append("参考仓库选择报告与本镜的语义结构或信息项数量不一致")
    start_ms, end_ms = shot.get("start_ms"), shot.get("end_ms")
    if isinstance(start_ms, int) and isinstance(end_ms, int) and query.get("duration_ms") != end_ms - start_ms:
        errors.append("参考仓库选择报告的时长与镜头边界不一致")
    confirmation = selector.get("reference_confirmation")
    if not isinstance(confirmation, dict):
        return errors + ["参考仓库候选尚未确认：缺少 reference_confirmation"]
    source_id = confirmation.get("confirmed_source_id")
    file_path = confirmation.get("confirmed_file_path")
    if not isinstance(source_id, str) or not source_id.strip():
        errors.append("reference_confirmation 缺少 confirmed_source_id")
    if not isinstance(file_path, str) or not file_path.strip():
        errors.append("reference_confirmation 缺少 confirmed_file_path")
    elif not Path(file_path).is_absolute():
        errors.append("confirmed_file_path 必须是候选报告中的绝对路径")
    if shot.get("template_id") != f"external:{source_id}":
        errors.append("template_id 必须等于 external:<confirmed_source_id>")
    candidates = selector.get("reference_candidates") or []
    matches = [item for item in candidates if isinstance(item, dict)
               and item.get("id") == source_id and item.get("reference_path") == file_path]
    if len(matches) != 1:
        errors.append("确认的 ID 与文件路径必须唯一对应选择报告中的候选")
        candidate = None
    else:
        candidate = matches[0]
        conflicts = constraint_check(selector.get("expression_brief"), candidate)["conflicts"]
        if conflicts:
            errors.append(f"确认的候选与本镜显式运动约束冲突：{', '.join(conflicts)}；须重新选型或登记适配后重新预览")
    if not repositories_root or not Path(repositories_root).is_absolute() or not Path(repositories_root).is_dir():
        errors.append("参考仓库根目录未配置或不存在")
    elif candidate:
        root = Path(repositories_root).resolve()
        source = str(candidate.get("reference_source") or "")
        source_root = (root / source).resolve()
        resolved = Path(file_path).resolve()
        if source not in REFERENCE_FRAMEWORKS:
            errors.append(f"确认的来源仓库 '{source}' 未在框架映射表中登记")
        elif (not source_root.is_relative_to(root)
                or not resolved.is_relative_to(source_root)
                or not resolved.is_file()):
            errors.append("确认的参考文件不存在或不在配置的来源仓库内")
        expected_framework = candidate.get("framework")
        if expected_framework != REFERENCE_FRAMEWORKS.get(source):
            errors.append("候选 framework 与参考仓库来源不一致")
        if confirmation.get("native_framework") != expected_framework:
            errors.append("native_framework 必须与候选来源框架一致")
        if expected_framework not in {"hyperframes", "remotion"}:
            errors.append("该来源框架尚无原生制作路由，不能走参考仓库快路径")
        primary_tool = (shot.get("production") or {}).get("primary_tool")
        if primary_tool != expected_framework:
            errors.append("镜头 primary_tool 与确认的原生框架不一致")
        basis = confirmation.get("license_basis")
        if not isinstance(basis, dict) or not str(basis.get("license_id") or "").strip():
            errors.append("license_basis 缺少 license_id")
        else:
            evidence_path = basis.get("evidence_path")
            if not isinstance(evidence_path, str) or not evidence_path.strip() or Path(evidence_path).is_absolute():
                errors.append("license_basis.evidence_path 须为来源仓库内的相对文件路径")
            else:
                evidence = (source_root / evidence_path).resolve()
                if not evidence.is_relative_to(source_root) or not evidence.is_file():
                    errors.append("许可证依据文件不存在或越过来源仓库")
    for key in ("motion_adaptation_reason", "phase_adaptation_reason"):
        if not isinstance(confirmation.get(key), str) or not confirmation[key].strip():
            errors.append(f"reference_confirmation 缺少 {key}")
    preview_path = confirmation.get("preview_path")
    if not isinstance(preview_path, str) or not preview_path.strip() or Path(preview_path).is_absolute():
        errors.append("preview_path 须为项目内相对文件路径")
    else:
        project = project_root.resolve()
        preview = (project / preview_path).resolve()
        if not preview.is_relative_to(project) or not preview.is_file():
            errors.append("预览证据文件不存在或越过项目目录")
    return errors
