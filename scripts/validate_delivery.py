#!/usr/bin/env python3
"""Validate the final artifact, prompt evidence, timeline coverage, and review state as one delivery."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import subprocess
from pathlib import Path

import validate_prompt_usage
import validate_state
from media_evidence import probe_video, validate_scan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("--production-prompts", required=True, type=Path)
    parser.add_argument("--mode", choices=["review", "final"], default="review")
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(value: object) -> str:
    return "".join(str(value or "").split())


def project_path(project_dir: Path, value: object) -> Path:
    candidate = Path(str(value or ""))
    return candidate if candidate.is_absolute() else project_dir / candidate


def prompt_record_path(project_dir: Path, shot: dict) -> Path:
    directory = "a-scenes" if shot.get("screen_role") == "A" else "b-scenes"
    return project_dir / "prompts" / directory / f"{shot.get('id')}.json"


def final_artifact_from(document: dict, label: str, errors: list[str]) -> dict:
    value = document.get("final_artifact")
    if not isinstance(value, dict):
        errors.append(f"{label} 缺少 final_artifact")
        return {}
    required = ("path", "sha256", "bytes", "duration_ms", "timeline_id")
    for key in required:
        if value.get(key) in (None, ""):
            errors.append(f"{label}.final_artifact 缺少 {key}")
    return value


def validate(project_dir: Path, prompts_path: Path, mode: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    required_paths = {
        "project": project_dir / "config" / "project.json",
        "plan": project_dir / "planning" / "visual-plan.json",
        "preflight": project_dir / "planning" / "preflight-report.json",
        "timeline_audit": project_dir / "reports" / "timeline-audit.json",
        "qa": project_dir / "reports" / "qa-report.json",
        "manifest": project_dir / "reports" / "manifest.json",
    }
    missing = [f"{label}: {path}" for label, path in required_paths.items() if not path.is_file()]
    if missing:
        return {
            "schema_version": "0.3",
            "status": "fail",
            "mode": mode,
            "errors": [f"缺少交付真源：{value}" for value in missing],
            "warnings": [],
        }

    project = load(required_paths["project"])
    plan = load(required_paths["plan"])
    preflight = load(required_paths["preflight"])
    audit = load(required_paths["timeline_audit"])
    qa = load(required_paths["qa"])
    manifest = load(required_paths["manifest"])

    prompt_report = validate_prompt_usage.validate(project_dir, prompts_path, "produced")
    if prompt_report.get("status") != "pass":
        errors.extend(f"提示词生产证据：{value}" for value in prompt_report.get("errors") or [])

    project_artifact = final_artifact_from(project, "config/project.json", errors)
    qa_artifact = final_artifact_from(qa, "reports/qa-report.json", errors)
    manifest_artifact = final_artifact_from(manifest, "reports/manifest.json", errors)
    artifact_keys = set(project_artifact) | set(qa_artifact) | set(manifest_artifact)
    for key in artifact_keys:
        if any(value.get(key) != project_artifact.get(key) for value in (qa_artifact, manifest_artifact)):
            errors.append(f"final_artifact.{key} 在 project、QA 与 manifest 中不一致")

    final_path = project_path(project_dir, manifest_artifact.get("path"))
    if not final_path.is_file():
        errors.append(f"最终 MP4 不存在：{final_path}")
    else:
        actual_bytes = final_path.stat().st_size
        if actual_bytes <= 0:
            errors.append("最终 MP4 为空文件")
        if manifest_artifact.get("bytes") != actual_bytes:
            errors.append(
                f"final_artifact.bytes 与文件不一致：{manifest_artifact.get('bytes')} / {actual_bytes}"
            )
        actual_hash = sha256(final_path)
        if str(manifest_artifact.get("sha256") or "").lower() != actual_hash:
            errors.append("final_artifact.sha256 与最终 MP4 不一致")

    state_report = validate_state.validate(project_dir)
    errors.extend(f"状态依赖：{value}" for value in state_report["errors"])
    warnings.extend(state_report["warnings"])
    for gate in ("plan", "visual_baseline", "sample"):
        if (project.get("status") or {}).get(gate) != "approved":
            errors.append(f"交付前 {gate} 必须批准且依赖有效")

    duration_ms = manifest_artifact.get("duration_ms")
    audio_duration_ms = (preflight.get("audio") or {}).get("duration_ms")
    fps = (project.get("video") or {}).get("fps")
    if type(fps) not in (int, float) or not math.isfinite(fps) or fps <= 0:
        errors.append("project.video.fps 必须为正数")
        fps = 30
    frame_tolerance_ms = 1000 / fps
    tolerance_ms = max(frame_tolerance_ms, 50)
    if type(duration_ms) in (int, float) and type(audio_duration_ms) in (int, float) and all(math.isfinite(v) and v > 0 for v in (duration_ms, audio_duration_ms)):
        if abs(duration_ms - audio_duration_ms) > tolerance_ms:
            errors.append(
                f"成片与音频时长误差超过 {tolerance_ms}ms：{duration_ms} / {audio_duration_ms}"
            )
    else:
        errors.append("成片与预检音频 duration_ms 必须为正数")

    media = None
    if final_path.is_file():
        try:
            media = probe_video(final_path)
            for key in ("width", "height", "fps"):
                expected = (project.get("video") or {}).get(key)
                if type(expected) not in (int, float) or not math.isfinite(expected) or abs(media[key] - expected) > 0.001:
                    errors.append(f"实际视频 {key} 与项目规格不一致")
            for label, expected in (("登记时长", duration_ms), ("旁白时长", audio_duration_ms)):
                if type(expected) in (int, float) and abs(media["duration_ms"] - expected) > tolerance_ms:
                    errors.append(f"实际视频流时长与{label}不一致")
            if abs(media["decoded_frames"] * 1000 / fps - media["duration_ms"]) > frame_tolerance_ms:
                errors.append("实际解码帧数与项目帧率/视频时长不一致")
            if abs(media["start_ms"]) > frame_tolerance_ms:
                errors.append("视频流未从时间线零点开始")
            if not media["audio_streams"] or not media["audio_durations_ms"]:
                errors.append("成片缺少可验证时长的音频流")
            elif type(audio_duration_ms) in (int, float) and all(abs(v - audio_duration_ms) > tolerance_ms for v in media["audio_durations_ms"]):
                errors.append("实际音频流时长与旁白时长不一致")
            errors.extend(validate_scan(project_dir, qa.get("frame_scan"), final_path, media))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            errors.append(f"实际媒体验证失败：{exc}")

    if qa.get("status") != "pass":
        errors.append(f"QA 未通过：status={qa.get('status')}")
    if audit.get("status") != "pass":
        errors.append(f"时间线审计未通过：status={audit.get('status')}")
    if manifest.get("status") not in {"rendered-pending-user-review", "approved"}:
        errors.append(f"manifest.status 不是可交付状态：{manifest.get('status')}")

    chatcut = project.get("chatcut") or {}
    timeline = audit.get("timeline") or {}
    manifest_chatcut = manifest.get("chatcut") or {}
    expected_timeline_id = str(project_artifact.get("timeline_id") or "")
    if project.get("primary_timeline") == "chatcut":
        for label, value in (
            ("project.chatcut.timeline_id", chatcut.get("timeline_id")),
            ("timeline-audit.timeline.id", timeline.get("id")),
            ("manifest.chatcut.timeline_id", manifest_chatcut.get("timeline_id")),
        ):
            if str(value or "") != expected_timeline_id:
                errors.append(f"{label} 与 final_artifact.timeline_id 不一致")

    shots = plan.get("shots") or []
    audit_shots = {str(item.get("id")): item for item in audit.get("shots") or []}
    if len(audit_shots) != len(audit.get("shots") or []) or set(audit_shots) != {str(s.get("id")) for s in shots}:
        errors.append("时间线审计镜头 ID 重复或与计划集合不一致")
    for shot_index, shot in enumerate(shots):
        shot_id = str(shot.get("id") or "")
        audited = audit_shots.get(shot_id)
        if not audited:
            errors.append(f"时间线审计缺少镜头：{shot_id}")
            continue
        if audited.get("status") != "pass":
            errors.append(f"{shot_id} 时间线覆盖未通过：{audited.get('status')}")
        if audited.get("screen_role") != shot.get("screen_role"):
            errors.append(f"{shot_id} 时间线审计的 screen_role 与计划不一致")
        if audited.get("plan_range_ms") != [shot.get("start_ms"), shot.get("end_ms")]:
            errors.append(f"{shot_id} 时间线审计的 plan_range_ms 与计划不一致")

        # Display ranges are half-open and include the explicit gap-hold policy.
        def frame_at(ms: float) -> int:
            return math.floor(ms * fps / 1000 + 0.5)

        expected_start = 0 if shot_index == 0 else frame_at(shot["start_ms"])
        expected_end = (frame_at(shots[shot_index + 1]["start_ms"]) if shot_index + 1 < len(shots)
                        else media["decoded_frames"] if media else frame_at(audio_duration_ms or shot["end_ms"]))
        expected_range = [expected_start, expected_end]
        if audited.get("timeline_range_frames") != expected_range or expected_end <= expected_start:
            errors.append(f"{shot_id} timeline_range_frames 应为 {expected_range}（含空隙保持）")

        planned_beats = shot.get("narration_beats") or []
        audited_beats = audited.get("beats") or []
        if len(audited_beats) != len(planned_beats):
            errors.append(
                f"{shot_id} 时间线节拍覆盖不完整：{len(audited_beats)} / {len(planned_beats)}"
            )

        record_path = prompt_record_path(project_dir, shot)
        record = load(record_path) if record_path.is_file() else {}
        sequence_key = "action_sequence" if shot.get("screen_role") == "A" else "motion_sequence"
        produced_beats = (record.get(sequence_key) or {}).get("beats") or []
        for position, planned in enumerate(planned_beats, start=1):
            if position > len(audited_beats):
                break
            actual = audited_beats[position - 1]
            beat_label = f"{shot_id} beat-{position}"
            if actual.get("at_ms") != planned.get("at_ms"):
                errors.append(f"{beat_label} 审计时间与视觉计划不一致")
            if normalize_text(actual.get("trigger_text")) != normalize_text(planned.get("trigger_text")):
                errors.append(f"{beat_label} 审计短语与视觉计划不一致")
            if actual.get("status") != "covered":
                errors.append(f"{beat_label} 未标记为 covered")
            timeline_at_ms = actual.get("timeline_at_ms")
            if type(timeline_at_ms) is not int or abs(timeline_at_ms - int(planned.get("at_ms", 0))) > frame_tolerance_ms:
                errors.append(f"{beat_label} 未在一个时间线帧内绑定旁白节拍")
            evidence = actual.get("evidence") or {}
            timeline_items = evidence.get("timeline_items") or []
            if not timeline_items:
                errors.append(f"{beat_label} 缺少 timeline_items")
            for item in timeline_items:
                if not str(item.get("item_id") or "").strip():
                    errors.append(f"{beat_label} timeline item 缺少 item_id")
                if project.get("primary_timeline") == "chatcut" and not str(item.get("asset_id") or "").strip():
                    errors.append(f"{beat_label} ChatCut timeline item 缺少 asset_id")
                bounds = item.get("range_frames")
                valid = isinstance(bounds, list) and len(bounds) == 2 and all(type(v) is int for v in bounds)
                if not valid or not expected_start <= bounds[0] < bounds[1] <= expected_end:
                    errors.append(f"{beat_label} timeline item 帧范围无效或越过镜头范围")
                elif type(timeline_at_ms) is int and not bounds[0] <= frame_at(timeline_at_ms) < bounds[1]:
                    errors.append(f"{beat_label} timeline item 未覆盖实际节拍帧")
            if position <= len(produced_beats):
                produced_evidence = produced_beats[position - 1].get("evidence") or {}
                if evidence.get("artifact") != produced_evidence.get("artifact"):
                    errors.append(f"{beat_label} 时间线证据资产与提示词生产证据不一致")
                if evidence.get("artifact_time_ms") != produced_evidence.get("artifact_time_ms"):
                    errors.append(f"{beat_label} 时间线证据时间与提示词生产证据不一致")

    final_status = str((project.get("status") or {}).get("final") or "")
    if mode == "review":
        if final_status not in {"rendered-pending-user-review", "approved"}:
            errors.append(f"review 模式要求已渲染候选或已批准，当前 final={final_status}")
    else:
        if final_status != "approved":
            errors.append(f"final 模式要求 status.final=approved，当前为 {final_status}")
        approval = (project.get("approvals") or {}).get("final") or {}
        if str(approval.get("sha256") or "").lower() != str(manifest_artifact.get("sha256") or "").lower():
            errors.append("最终批准 SHA-256 与成片不一致")
        source = approval.get("review_source")
        if source not in {"user", "agent-qa-under-user-authorization"}:
            errors.append("最终批准缺少有效 review_source")
        if source == "agent-qa-under-user-authorization" and project.get("review_mode") != "continuous":
            errors.append("代理最终批准只允许用于 continuous review_mode")

    return {
        "schema_version": "0.3",
        "status": "pass" if not errors else "fail",
        "mode": mode,
        "project_id": project.get("project_id"),
        "timeline_id": expected_timeline_id,
        "final_artifact": manifest_artifact,
        "prompt_usage_status": prompt_report.get("status"),
        "checked_shots": len(plan.get("shots") or []),
        "errors": errors,
        "warnings": warnings,
    }


def markdown(report: dict) -> str:
    errors = report.get("errors") or ["无"]
    warnings = report.get("warnings") or ["无"]
    return "\n".join(
        [
            "# 最终交付闭环校验",
            "",
            f"- 状态：`{report['status']}`",
            f"- 模式：`{report['mode']}`",
            f"- 项目：`{report.get('project_id')}`",
            f"- 时间线：`{report.get('timeline_id')}`",
            f"- 已检查镜头：{report.get('checked_shots', 0)}",
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
        report = validate(args.project_dir, args.production_prompts, args.mode)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "delivery-validation-report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json_path.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "out": str(json_path)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
