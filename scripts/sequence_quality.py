"""Check sequence-review evidence, not visual taste or user approval."""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

from broll_runtime import RUNTIMES
from delivery_evidence import load_timeline_snapshot, local_file
from media_evidence import digest, probe_still, probe_video
from motion_review import motion_mode
from visual_timing import display_ranges, validate_visual_cuts

POLICY = "sequence-quality-v1"
PROGRAMMATIC = RUNTIMES | {"chatcut-motion-graphics"}


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected object")
    return value


def scope_hash(plan: dict, shot_ids: list[str]) -> str:
    import hashlib
    selected = set(shot_ids)
    value = {"shared": {k: v for k, v in plan.items() if k != "shots"},
             "shots": [s for s in plan.get("shots", []) if s.get("id") in selected]}
    # An unselected next shot can still determine the selected shot's exit.
    shots = plan.get("shots", [])
    outgoing = [{"id": s.get("id"), "start_ms": s.get("start_ms"),
                 "visual_cut": s["transition"]["visual_cut"]}
                for i, s in enumerate(shots) if i > 0 and shots[i-1].get("id") in selected
                and s.get("id") not in selected
                and isinstance(s.get("transition"), dict) and "visual_cut" in s["transition"]]
    if outgoing:
        value["outgoing_visual_cuts"] = outgoing
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def needs_reference(shot: dict) -> bool:
    production = shot.get("production") or {}
    return (motion_mode(shot) != "single-state" and
            (production.get("primary_tool") in PROGRAMMATIC or production.get("custom_motion") is True))


def validate_plan(plan: dict, project: dict) -> dict:
    errors, warnings = [], []
    errors.extend(validate_visual_cuts(plan, (project.get("video") or {}).get("fps")))
    policy = project.get("sequence_review_policy")
    if policy is None:
        warnings.append("旧任务未接入连续镜头质量门；不自动迁移或声称已验证")
        return {"errors": errors, "warnings": warnings}
    if policy != POLICY:
        return {"errors": ["未知 sequence_review_policy"], "warnings": []}
    direction = plan.get("sequence_direction") or {}
    for key in ("visual_thread", "continuity", "layout_rules", "motion_language"):
        if not isinstance(direction, dict) or not isinstance(direction.get(key), str) or not direction[key].strip():
            errors.append(f"sequence_direction 缺少 {key}")
    for shot in plan.get("shots", []):
        production = shot.get("production") or {}
        if production.get("assembly_tool") != project.get("primary_timeline"):
            errors.append(f"{shot.get('id')} assembly_tool 与 primary_timeline 不一致")
        if needs_reference(shot) and not str(production.get("motion_reference_review") or "").strip():
            errors.append(f"{shot.get('id')} 自制动效缺少 motion_reference_review；照片或scene分类不能豁免")
    return {"errors": errors, "warnings": warnings}


def evidence(root: Path, value: object, label: str, errors: list[str], files: set[str]) -> Path | None:
    try:
        if not isinstance(value, dict):
            raise ValueError("缺少 path/sha256 对象")
        path = local_file(root, value.get("path", value.get("artifact")))
        files.add(path.relative_to(root.resolve()).as_posix())
        if digest(path) != value.get("sha256"):
            raise ValueError("SHA-256 与实际文件不一致")
        return path
    except (OSError, ValueError, TypeError) as exc:
        errors.append(f"{label} 不可验证：{exc}")
        return None


def validate_reference(root: Path, shot: dict, errors: list[str], files: set[str]) -> None:
    if not needs_reference(shot):
        return
    label = f"{shot.get('id')} motion_reference_review"
    try:
        path = local_file(root, (shot.get("production") or {}).get("motion_reference_review"))
        files.add(path.relative_to(root.resolve()).as_posix())
        record = load(path)
        decision = record.get("decision")
        if decision not in {"reuse-native-source", "study-and-reimplement", "custom-after-external-review"}:
            raise ValueError("缺少有效参考决策")
        candidates = record.get("inspected_candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("没有实际查看的候选")
        ids = []
        for candidate in candidates:
            if not isinstance(candidate, dict) or not isinstance(candidate.get("id"), str) or not candidate["id"].strip():
                raise ValueError("候选ID无效")
            ids.append(candidate["id"])
            locator = candidate.get("source_locator") or candidate.get("shot_card")
            if not isinstance(locator, str) or not locator.strip():
                errors.append(f"{label} 候选 {candidate['id']} 缺少具体来源位置")
            preview = candidate.get("preview_evidence") or {}
            if preview.get("status") != "inspected":
                errors.append(f"{label} 候选 {candidate['id']} 未记录实际查看预览")
            preview_path = evidence(root, preview, f"{label} 候选预览", errors, files)
            if preview_path:
                if preview_path.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}:
                    probe_video(preview_path)
                else:
                    probe_still(preview_path)
            if not str(candidate.get("assessment") or "").strip():
                errors.append(f"{label} 候选 {candidate['id']} 缺少动作适配判断")
        if len(set(ids)) != len(ids):
            errors.append(f"{label} 候选ID重复")
        selected = record.get("selected_candidate")
        if decision == "custom-after-external-review":
            if selected is not None or not str(record.get("custom_reason") or "").strip():
                errors.append(f"{label} 自建须无选中来源并说明原因")
            if not record.get("borrowed_motion_principles") or any(not str(c.get("rejection_reason") or "").strip() for c in candidates):
                errors.append(f"{label} 自建缺少拒绝理由或可追溯运动原则")
        elif selected not in ids:
            errors.append(f"{label} 必须确认一个已查看的唯一来源")
        elif decision == "reuse-native-source":
            source = next(c for c in candidates if c["id"] == selected)
            if not str(source.get("license") or "").strip() or not source.get("implementation_files"):
                errors.append(f"{label} 原生复用缺少许可证或具体实现文件")
            evidence(root, source.get("license_evidence"), f"{label} 许可证依据", errors, files)
            repositories = load(root / "config/project.json").get("repositories_root")
            allowed_roots = [root.resolve()]
            if repositories:
                allowed_roots.append(Path(repositories).resolve())
            for name in source.get("implementation_files") or []:
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"{label} 实现文件路径无效")
                    continue
                paths = [(base / name).resolve() for base in allowed_roots]
                if repositories and source.get("repository"):
                    paths.append((Path(repositories) / source["repository"] / name).resolve())
                if not any(p.is_file() and any(p.is_relative_to(base) for base in allowed_roots) for p in paths):
                    errors.append(f"{label} 具体实现文件不可读取或越界：{name}")
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        errors.append(f"{label} 不可验证：{exc}")


def check_review(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, dict) or value.get("status") != "pass" or not str(value.get("notes") or "").strip():
        errors.append(f"{label} 未通过或缺少实际观察说明")


def validate(root: Path, stage: str, *, plan: dict | None = None, project: dict | None = None) -> dict:
    errors, warnings, files = [], [], set()
    result = {"policy": POLICY, "stage": stage, "errors": errors, "warnings": warnings, "files": []}
    try:
        root = root.resolve()
        project = project if project is not None else load(root / "config/project.json")
        plan = plan if plan is not None else load(root / "planning/visual-plan.json")
        report = validate_plan(plan, project)
        errors.extend(report["errors"])
        warnings.extend(report["warnings"])
        if project.get("sequence_review_policy") != POLICY or stage == "planning":
            return result
        shots = plan.get("shots") or []
        if stage == "prepared":
            for shot in shots:
                validate_reference(root, shot, errors, files)
            return result
        key = "full" if stage == "delivery" else "sample"
        review_path = local_file(root, (project.get("sequence_review") or {}).get(key))
        files.add(review_path.relative_to(root).as_posix())
        review = load(review_path)
        if review.get("policy") != POLICY or review.get("scope") != key:
            errors.append("连续镜头审阅 policy/scope 与本次检查不一致")
        bounds = review.get("range_ms")
        if (not isinstance(bounds, list) or len(bounds) != 2 or
                any(type(v) is not int for v in bounds) or not 0 <= bounds[0] < bounds[1]):
            raise ValueError("range_ms 必须为非空半开毫秒区间")
        if key == "sample" and bounds != [project.get("sample", {}).get("start_ms"), project.get("sample", {}).get("end_ms")]:
            errors.append("连续镜头审阅范围与配置样片区间不一致")
        ranges = display_ranges(shots, max(shots[-1]["end_ms"], bounds[1]) if shots else bounds[1])
        selected = [s for s, (start, end) in zip(shots, ranges) if start < bounds[1] and end > bounds[0]]
        ids = [s["id"] for s in selected]
        rows = review.get("shots")
        if not isinstance(rows, list) or [r.get("shot_id") for r in rows if isinstance(r, dict)] != ids or not ids:
            raise ValueError("审阅必须按时间顺序覆盖范围内全部镜头，不能只选孤立好镜头")
        if key == "full" and (bounds[0] != 0 or ids != [s["id"] for s in shots]):
            errors.append("整片审阅没有从零覆盖全部镜头")
        if review.get("plan_scope_sha256") != scope_hash(plan, ids):
            errors.append("连续镜头审阅绑定的计划范围已过期")
        captured_plan = evidence(root, review.get("plan_snapshot"), "审阅时计划快照", errors, files)
        captured_hash = None
        if captured_plan:
            captured_hash = digest(captured_plan)
            if scope_hash(load(captured_plan), ids) != scope_hash(plan, ids):
                errors.append("审阅时计划快照与当前范围不一致")
        if review.get("design_ref") != plan.get("design_ref"):
            errors.append("连续镜头审阅 design_ref 已过期")
        evidence(root, plan.get("design_ref"), "当前DESIGN", errors, files)
        for field, binding in (("audio", "narration_sha256"), ("srt", "srt_sha256")):
            path = local_file(root, project.get("inputs", {}).get(field))
            files.add(path.relative_to(root).as_posix())
            if review.get(binding) != digest(path):
                errors.append(f"连续镜头审阅未绑定当前 {field}")
        artifact = evidence(root, review.get("artifact"), "连续镜头视频", errors, files)
        media = probe_video(artifact) if artifact else None
        if media:
            video = project.get("video") or {}
            if any(media[k] != video.get(k) for k in ("width", "height", "fps")):
                errors.append("连续镜头视频规格与项目不一致")
            tolerance = max(50, 1000 / media["fps"])
            if abs(media["duration_ms"] - (bounds[1] - bounds[0])) > tolerance or not media["audio_streams"]:
                errors.append("连续镜头视频时长与审阅范围不一致或缺少旁白音轨")
        if key == "full" and any((review.get("artifact") or {}).get(k) != (project.get("final_artifact") or {}).get(k) for k in ("path", "sha256")):
            errors.append("整片质量审阅未绑定实际 final_artifact")
        if key == "sample" and (project.get("status") or {}).get("sample") == "approved":
            approval = (project.get("approvals") or {}).get("sample") or {}
            if ((review.get("artifact") or {}).get("path") != approval.get("artifact") or
                    (review.get("artifact") or {}).get("sha256") != approval.get("sha256")):
                errors.append("连续镜头审阅未绑定已批准的实际样片")
        if review.get("normal_speed_viewed") is not True:
            errors.append("缺少带原旁白的正常速度连看记录")
        source = review.get("review_source")
        if source not in {"user", "agent-self-check", "agent-qa-under-user-authorization"}:
            errors.append("连续镜头审阅缺少真实 review_source")
        if source == "agent-qa-under-user-authorization" and project.get("review_mode") != "continuous":
            errors.append("continuous 自检来源不能用于manual；普通内部检查使用agent-self-check，不写审批")
        checks = review.get("sequence_checks") or {}
        for name in ("visual_continuity", "ppt_feel", "reading_rhythm"):
            check_review(checks.get(name), f"连续镜头 {name}", errors)
        timeline = review.get("timeline") or {}
        if timeline.get("runtime") != project.get("primary_timeline"):
            errors.append("审阅实际主时间线与 primary_timeline 不一致；候选也不能改换主工程")
        if project.get("primary_timeline") == "chatcut":
            chatcut = project.get("chatcut") or {}
            if (not timeline.get("project_id") or not timeline.get("timeline_id") or
                    timeline.get("project_id") != chatcut.get("project_id") or timeline.get("timeline_id") != chatcut.get("timeline_id")):
                errors.append("连续镜头审阅缺少匹配的实际ChatCut项目/时间线ID")
            if timeline.get("exporter") != "chatcut-local-export":
                errors.append("ChatCut候选须由ChatCut导出，不能用本地整片代替")
        snapshot_project = dict(project, final_artifact={"timeline_id": timeline.get("timeline_id")})
        snapshot_items, snapshot_errors = load_timeline_snapshot(root, timeline.get("source_snapshot"), snapshot_project,
            (review.get("artifact") or {}).get("sha256", ""), files, expected_plan_sha256=captured_hash)
        errors.extend(snapshot_errors)
        for shot, row in zip(selected, rows):
            sid = shot["id"]
            if row.get("actual_tool") != (shot.get("production") or {}).get("primary_tool"):
                errors.append(f"{sid} 实际制作工具与计划不同，须回写路由并复核")
            validate_reference(root, shot, errors, files)
            for name in ("explanation_review", "layout_review"):
                check_review(row.get(name), f"{sid} {name}", errors)
            item_ids = row.get("item_ids")
            if not isinstance(item_ids, list) or not item_ids or any(i not in snapshot_items for i in item_ids):
                errors.append(f"{sid} 缺少实际时间线实例映射")
            elif media:
                index = shots.index(shot)
                a, b = ranges[index]
                first = math.floor((max(a, bounds[0]) - bounds[0]) * media["fps"] / 1000 + 0.5)
                end = math.floor((min(b, bounds[1]) - bounds[0]) * media["fps"] / 1000 + 0.5)
                intervals = sorted(snapshot_items[i]["range_frames"] for i in item_ids)
                covered = first
                for left, right in intervals:
                    if left <= covered:
                        covered = max(covered, right)
                if covered < end:
                    errors.append(f"{sid} 实际时间线实例未覆盖审阅镜头范围")
                if not any(first <= left < right <= end for left, right in intervals):
                    errors.append(f"{sid} 缺少独立镜头实例，不能把整片合成文件作为所有镜头的唯一素材")
            if (shot.get("production") or {}).get("primary_tool") in PROGRAMMATIC:
                sources = (shot.get("production") or {}).get("source_files")
                if not isinstance(sources, list) or not sources:
                    errors.append(f"{sid} 程序化镜头缺少source_files实际源工程")
                else:
                    for value in sources:
                        path = local_file(root, value)
                        files.add(path.relative_to(root).as_posix())
            states = row.get("state_evidence") or []
            required = {"hold"} if motion_mode(shot) == "single-state" else {"start", "change", "result"}
            if not isinstance(states, list) or not required.issubset({s.get("phase") for s in states if isinstance(s, dict)}):
                errors.append(f"{sid} 缺少运动开始/中间变化/落定证据；静止镜头使用hold")
                continue
            for state in states:
                path = evidence(root, state, f"{sid} 布局静帧", errors, files)
                if path:
                    probe_still(path)
                at = state.get("artifact_time_ms")
                index = shots.index(shot)
                start = max(ranges[index][0], bounds[0]) - bounds[0]
                end = min(ranges[index][1], bounds[1]) - bounds[0]
                if type(at) is not int or not start <= at < end:
                    errors.append(f"{sid} 静帧时间点不在本次视频的镜头范围内")
            if motion_mode(shot) != "single-state" and len({s.get("artifact_time_ms") for s in states}) < 3:
                errors.append(f"{sid} 运动布局证据须覆盖不同时间点")
        transitions = review.get("transitions") or []
        pairs = [(ids[i], ids[i+1]) for i in range(len(ids)-1)]
        if not isinstance(transitions, list) or [(t.get("from"), t.get("to")) for t in transitions if isinstance(t, dict)] != pairs:
            errors.append("相邻镜头衔接审阅缺失、重复或顺序错误")
        else:
            for transition in transitions:
                check_review(transition, "镜头衔接", errors)
                path = evidence(root, transition.get("evidence"), "转场中间态或接缝证据", errors, files)
                if path:
                    probe_still(path)
                at = transition.get("artifact_time_ms")
                pair = [s for s in selected if s["id"] in {transition.get("from"), transition.get("to")}]
                first_range = ranges[shots.index(pair[0])]
                last_range = ranges[shots.index(pair[-1])]
                if type(at) is not int or not max(first_range[0], bounds[0])-bounds[0] <= at < min(last_range[1], bounds[1])-bounds[0]:
                    errors.append("衔接证据时间不在本次视频的相邻镜头范围内")
        if stage == "expand":
            for shot in shots:
                validate_reference(root, shot, errors, files)
        if source == "agent-self-check":
            warnings.append("内部视觉自检记录不等于用户批准；现有manual/continuous审核门继续适用")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError) as exc:
        errors.append(f"连续镜头质量证据不可验证：{exc}")
    finally:
        result["files"] = sorted(files)
        result["status"] = "pass" if not errors else "fail"
    return result
