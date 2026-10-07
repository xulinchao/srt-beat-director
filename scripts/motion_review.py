"""Motion plans and review evidence; metadata checks never judge visual meaning."""
from __future__ import annotations

import subprocess
from pathlib import Path

from media_evidence import digest, probe_still, probe_video, validate_source_time

POLICY = "evidence-first-v1"
MODES = {"single-state", "state-sequence", "continuous-motion", "verified-media-sequence", "text-motion"}
SCOPES = {"style-preview", "state-preview", "motion-baseline"}


def motion_mode(shot: dict) -> str | None:
    return (shot.get("visual_design") or {}).get("motion_mode")


def validate_motion_plan(plan: dict, project: dict) -> dict:
    errors, warnings = [], []
    policy = plan.get("motion_review_policy")
    expected = project.get("motion_review_policy")
    if expected not in {None, POLICY} or policy not in {None, POLICY}:
        errors.append("未知 motion_review_policy")
    if expected == POLICY and policy != POLICY:
        errors.append("新任务必须在计划声明 motion_review_policy=evidence-first-v1")
    if policy != POLICY:
        warnings.append("旧计划未接入动作证据检查；字段通过不代表动作设计已验证")
        return {"errors": errors, "warnings": warnings}
    shots = plan.get("shots") or []
    ids = {s.get("id") for s in shots}
    representatives = plan.get("baseline_shot_ids")
    if (not isinstance(representatives, list) or not representatives
            or any(not isinstance(s, str) or s not in ids for s in representatives)
            or len(set(representatives)) != len(representatives)):
        errors.append("baseline_shot_ids 必须明确选择不重复的现有代表镜头")
    for shot in shots:
        label = shot.get("id", "unknown")
        design = shot.get("visual_design") or {}
        mode = motion_mode(shot)
        if mode not in MODES:
            errors.append(f"{label} 缺少有效 visual_design.motion_mode")
            continue
        if mode == "single-state":
            if not str(shot.get("static_reason") or "").strip():
                errors.append(f"{label} single-state 必须说明 static_reason")
            continue
        check = design.get("motion_check") or {}
        for key in ("action", "visible_result"):
            if not str(check.get(key) or "").strip():
                errors.append(f"{label} motion_check 缺少 {key}")
        states = check.get("required_states")
        if not isinstance(states, list) or len(states) < 2:
            errors.append(f"{label} 非静止镜头须声明至少两个必要状态，不按旁白节拍数量判断静止")
            continue
        state_ids = set()
        for state in states:
            if not isinstance(state, dict):
                errors.append(f"{label} required_states 项必须为对象")
                continue
            sid, beat = state.get("id"), state.get("beat_index")
            if not isinstance(sid, str) or not sid.strip() or sid in state_ids:
                errors.append(f"{label} 必要状态 ID 为空或重复")
            else:
                state_ids.add(sid)
            if not str(state.get("description") or "").strip():
                errors.append(f"{label} 必要状态缺少可见画面描述")
            if type(beat) is not int or not 0 <= beat < len(shot.get("narration_beats") or []):
                errors.append(f"{label} 必要状态 beat_index 必须引用现有旁白节拍")
    return {"errors": errors, "warnings": warnings}


def validate_visual_review(project_dir: Path, plan: dict, project: dict, review: dict,
                           *, approve: bool = False, require_representatives: bool = True) -> dict:
    """Inspect a partial candidate, or gate approval of selected baseline shots."""
    errors, warnings = [], []
    scope = review.get("scope")
    if review.get("policy") != POLICY or scope not in SCOPES:
        errors.append("视觉审阅须声明 evidence-first-v1 与有效 scope")
    if approve and scope != "motion-baseline":
        errors.append("画风或静帧预览不能批准为动作视觉基线")
    plan_check = validate_motion_plan(plan, project)
    errors.extend(plan_check["errors"])
    warnings.extend(plan_check["warnings"])
    if plan.get("motion_review_policy") != POLICY:
        errors.append("本检查需要已接入 evidence-first-v1 的计划")
    try:
        if review.get("plan_sha256") != digest(project_dir / "planning/visual-plan.json"):
            errors.append("视觉审阅绑定的计划哈希过期")
    except OSError as exc:
        errors.append(f"计划不可读取：{exc}")
    if review.get("design_ref") != plan.get("design_ref"):
        errors.append("视觉审阅 design_ref 与当前计划不一致")
    by_id = {s["id"]: s for s in plan.get("shots") or []}
    seen, cache = set(), {}

    def evidence(value: object, label: str) -> tuple[str, object] | None:
        if not isinstance(value, dict):
            errors.append(f"{label} 缺少证据对象")
            return None
        relative = value.get("artifact")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            errors.append(f"{label} artifact 必须为项目内相对路径")
            return None
        path = (project_dir / relative).resolve()
        if not path.is_relative_to(project_dir.resolve()) or not path.is_file():
            errors.append(f"{label} 证据不存在或越界")
            return None
        actual = digest(path)
        if value.get("sha256") != actual:
            errors.append(f"{label} 证据哈希不一致")
        at = value.get("artifact_time_ms")
        if at is not None:
            errors.extend(f"{label} {item}" for item in validate_source_time(path, at, cache))
        elif label.endswith("/dynamic_preview"):
            pass  # The video and audio streams are inspected below.
        else:
            key = ("still", path)
            if key not in cache:
                try:
                    probe_still(path)
                    cache[key] = None
                except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
                    cache[key] = str(exc)
            if cache[key]:
                errors.append(f"{label} {cache[key]}")
        return actual, at

    entries = review.get("shots")
    if not isinstance(entries, list) or not entries:
        errors.append("视觉审阅缺少镜头证据")
        entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("镜头审阅项必须为对象")
            continue
        sid = entry.get("shot_id")
        if not isinstance(sid, str) or sid not in by_id or sid in seen:
            errors.append("镜头审阅 ID 未登记或重复")
            continue
        seen.add(sid)
        shot = by_id[sid]
        mode = motion_mode(shot)
        states = ((shot.get("visual_design") or {}).get("motion_check") or {}).get("required_states") or []
        required = {s["id"] for s in states if isinstance(s, dict) and isinstance(s.get("id"), str)}
        if mode == "single-state":
            required = {"hold"}
        items = entry.get("state_evidence")
        if not isinstance(items, list) or not items:
            errors.append(f"{sid} 缺少实际状态证据")
            items = []
        covered, identities = set(), set()
        for item in items:
            state_id = item.get("state_id") if isinstance(item, dict) else None
            if not isinstance(state_id, str) or state_id not in required or state_id in covered:
                errors.append(f"{sid} 状态未登记或重复")
            else:
                covered.add(state_id)
            identity = evidence(item, f"{sid}/{state_id}")
            if identity:
                if identity in identities and mode != "single-state" and scope != "style-preview":
                    errors.append(f"{sid} 同一图片或同一视频时间点不能冒充不同状态")
                identities.add(identity)
        if scope != "style-preview" and covered != required:
            errors.append(f"{sid} 必要状态未覆盖：{sorted(required - covered)}")
        if scope == "motion-baseline":
            technical = entry.get("technical_review") or {}
            expression = entry.get("expression_review") or {}
            if technical.get("status") != "pass" or not str(technical.get("notes") or "").strip():
                errors.append(f"{sid} 技术检查未通过或缺少说明")
            if expression.get("status") != "pass":
                errors.append(f"{sid} 表达检查未通过，不能由技术检查代替")
            source = expression.get("review_source")
            if source not in {"user", "agent-qa-under-user-authorization"}:
                errors.append(f"{sid} 表达检查缺少真实审核来源")
            elif source == "agent-qa-under-user-authorization" and project.get("review_mode") != "continuous":
                errors.append(f"{sid} 代理审核需要 continuous 授权")
            for key in ("observed_action", "observed_result"):
                if not str(expression.get(key) or "").strip():
                    errors.append(f"{sid} 表达检查缺少 {key}")
            for key in ("action_matches", "result_matches", "narration_matches"):
                if expression.get(key) is not True:
                    errors.append(f"{sid} 表达检查 {key} 未通过")
            if mode != "single-state":
                preview = entry.get("dynamic_preview")
                if evidence(preview, f"{sid}/dynamic_preview"):
                    try:
                        media = probe_video(project_dir / preview["artifact"])
                        if media["audio_streams"] < 1:
                            errors.append(f"{sid} 动态审阅短片缺少音轨")
                        audio = (project.get("inputs") or {}).get("audio")
                        if not audio or entry.get("narration_sha256") != digest(project_dir / audio):
                            errors.append(f"{sid} 动态审阅未绑定当前原旁白")
                    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
                        errors.append(f"{sid} 动态短片不可验证：{exc}")
    if scope == "motion-baseline" and require_representatives:
        missing = set(plan.get("baseline_shot_ids") or []) - seen
        if missing:
            errors.append(f"视觉基线缺少代表镜头：{sorted(missing)}")
    return {"status": "fail" if errors else "pass", "scope": scope,
            "validation_scope": "evidence-integrity; visual meaning and listening require recorded human/authorized review",
            "errors": errors, "warnings": warnings}
