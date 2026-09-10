#!/usr/bin/env python3
"""Validate that production prompts were instantiated and actually used."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from validate_design import validate as validate_design


VALID_STATUSES = {"prepared", "used", "completed", "failed"}
A_ROLL_MULTI_STATE_THRESHOLD_MS = 4000
A_ROLL_SEQUENCE_MODES = {"single-state", "state-sequence", "continuous-motion"}
B_ROLL_SEQUENCE_MODES = {
    "single-state",
    "state-sequence",
    "continuous-motion",
    "verified-media-sequence",
    "text-motion",
}


def required_a_roll_beat_count(duration_ms: int) -> int:
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("--production-prompts", required=True, type=Path)
    parser.add_argument("--stage", choices=["planning", "prepared", "produced"], required=True)
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


def resolve_project_path(project_dir: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else project_dir / candidate


def normalize_text(value: object) -> str:
    return "".join(str(value or "").split())


def validate_record(
    *,
    record_path: Path,
    project_dir: Path,
    expected_subject: str,
    required_prompt_ids: set[str],
    prompt_hash: str,
    stage: str,
    errors: list[str],
    checked: list[str],
    selection_report: str | None = None,
) -> None:
    label = record_path.relative_to(project_dir).as_posix()
    if not record_path.is_file():
        errors.append(f"缺少提示词实例：{label}")
        return
    try:
        record = load(record_path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"提示词实例不可读：{label}：{exc}")
        return

    checked.append(label)
    if record.get("subject_id") != expected_subject:
        errors.append(f"{label} subject_id 应为 {expected_subject}")
    prompt_ids = set(record.get("prompt_ids") or [])
    missing_ids = sorted(required_prompt_ids - prompt_ids)
    if missing_ids:
        errors.append(f"{label} 缺少 prompt_ids：{missing_ids}")
    if record.get("prompt_source") != "references/production-prompts.md":
        errors.append(f"{label} prompt_source 必须为 references/production-prompts.md")
    if record.get("prompt_source_sha256") != prompt_hash:
        errors.append(f"{label} 绑定的生产提示词 SHA-256 已过期或缺失")
    if record.get("inputs") in (None, {}, []):
        errors.append(f"{label} inputs 不能为空")
    if not str(record.get("resolved_prompt") or "").strip():
        errors.append(f"{label} resolved_prompt 不能为空")

    status = record.get("status")
    if status not in VALID_STATUSES:
        errors.append(f"{label} status 无效：{status}")
    if stage == "produced" and status != "completed":
        errors.append(f"{label} 尚未完成生产：status={status}")

    if selection_report is not None:
        if record.get("selection_report") != selection_report:
            errors.append(f"{label} selection_report 应为 {selection_report}")
        elif not resolve_project_path(project_dir, selection_report).is_file():
            errors.append(f"{label} 对应的 B-roll 选择报告不存在：{selection_report}")

    if stage == "produced" and status == "completed":
        artifacts = record.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            errors.append(f"{label} completed 但没有 artifacts")
        else:
            for value in artifacts:
                path_value = str(value.get("path") if isinstance(value, dict) else value)
                if not path_value or not resolve_project_path(project_dir, path_value).is_file():
                    errors.append(f"{label} 输出不存在：{path_value or '<empty>'}")


def validate_a_roll_sequence(
    *,
    record_path: Path,
    project_dir: Path,
    shot: dict,
    stage: str,
    errors: list[str],
) -> None:
    label = record_path.relative_to(project_dir).as_posix()
    if not record_path.is_file():
        return
    try:
        record = load(record_path)
    except (OSError, json.JSONDecodeError):
        return

    sequence = record.get("action_sequence")
    if not isinstance(sequence, dict):
        errors.append(f"{label} 缺少 action_sequence")
        return

    duration_ms = int(shot.get("end_ms", 0)) - int(shot.get("start_ms", 0))
    required_beats = required_a_roll_beat_count(duration_ms)
    mode = sequence.get("mode")
    if mode not in A_ROLL_SEQUENCE_MODES:
        errors.append(f"{label} action_sequence.mode 无效：{mode}")
    if mode == "single-state" and not str(sequence.get("static_reason") or "").strip():
        errors.append(f"{label} single-state 必须说明 static_reason")

    beats = sequence.get("beats")
    plan_beats = shot.get("narration_beats") or []
    if not isinstance(plan_beats, list) or not plan_beats:
        errors.append(f"{label} 对应视觉计划缺少 narration_beats")
        return
    if mode == "single-state" and len(plan_beats) != 1:
        errors.append(f"{label} single-state 只能落实一个计划节拍")
    if len(plan_beats) == 1:
        static_reason = str(shot.get("static_reason") or "").strip()
        if not static_reason or normalize_text(sequence.get("static_reason")) != normalize_text(static_reason):
            errors.append(f"{label} 单状态必须继承计划 static_reason")
    if not isinstance(beats, list) or len(beats) < required_beats:
        actual = len(beats) if isinstance(beats, list) else 0
        errors.append(f"{label} 至少需要 {required_beats} 个动作节拍，当前为 {actual} 个")
        return
    if len(beats) != len(plan_beats):
        errors.append(
            f"{label} action_sequence 必须落实全部计划节拍，"
            f"当前为 {len(beats)} / {len(plan_beats)}"
        )

    evidence_paths: list[str] = []
    evidence_times: list[int] = []
    for position, beat in enumerate(beats, start=1):
        beat_label = f"{label} beat-{position}"
        if not isinstance(beat, dict):
            errors.append(f"{beat_label} 必须为对象")
            continue
        at_ms = beat.get("at_ms")
        if not isinstance(at_ms, int) or not shot["start_ms"] <= at_ms <= shot["end_ms"]:
            errors.append(f"{beat_label} at_ms 超出镜头边界")
        for key in ("trigger_text", "visual_state", "implementation"):
            if not str(beat.get(key) or "").strip():
                errors.append(f"{beat_label} 缺少 {key}")
        if position <= len(plan_beats):
            planned = plan_beats[position - 1]
            if at_ms != planned.get("at_ms"):
                errors.append(f"{beat_label} at_ms 与视觉计划节拍不一致")
            if normalize_text(beat.get("trigger_text")) != normalize_text(planned.get("trigger_text")):
                errors.append(f"{beat_label} trigger_text 与视觉计划旁白短语不一致")

        if stage != "produced":
            continue
        evidence = beat.get("evidence")
        if not isinstance(evidence, dict):
            errors.append(f"{beat_label} 缺少 produced evidence")
            continue
        artifact = str(evidence.get("artifact") or "")
        if not artifact:
            errors.append(f"{beat_label} evidence.artifact 不能为空")
        elif not resolve_project_path(project_dir, artifact).is_file():
            errors.append(f"{beat_label} evidence.artifact 不存在：{artifact}")
        else:
            evidence_paths.append(artifact)
        artifact_time_ms = evidence.get("artifact_time_ms")
        if mode == "continuous-motion":
            if not isinstance(artifact_time_ms, int) or artifact_time_ms < 0:
                errors.append(f"{beat_label} continuous-motion 需要非负 artifact_time_ms")
            else:
                evidence_times.append(artifact_time_ms)

    if stage == "produced" and mode == "state-sequence":
        if len(set(evidence_paths)) < len(plan_beats):
            errors.append(f"{label} state-sequence 必须为每个动作状态提供不同的证据资产")
    if stage == "produced" and mode == "continuous-motion":
        if len(set(evidence_times)) < len(plan_beats):
            errors.append(f"{label} continuous-motion 必须为每个动作状态提供不同的证据时间点")


def validate_b_roll_sequence(
    *,
    record_path: Path,
    project_dir: Path,
    shot: dict,
    stage: str,
    errors: list[str],
) -> None:
    label = record_path.relative_to(project_dir).as_posix()
    if not record_path.is_file():
        return
    try:
        record = load(record_path)
    except (OSError, json.JSONDecodeError):
        return

    sequence = record.get("motion_sequence")
    if not isinstance(sequence, dict):
        errors.append(f"{label} 缺少 motion_sequence")
        return
    mode = sequence.get("mode")
    if mode not in B_ROLL_SEQUENCE_MODES:
        errors.append(f"{label} motion_sequence.mode 无效：{mode}")

    plan_beats = shot.get("narration_beats") or []
    beats = sequence.get("beats")
    if not isinstance(plan_beats, list) or not plan_beats:
        errors.append(f"{label} 对应视觉计划缺少 narration_beats")
        return
    if not isinstance(beats, list):
        errors.append(f"{label} motion_sequence.beats 必须为数组")
        return
    if len(beats) != len(plan_beats):
        errors.append(
            f"{label} motion_sequence 必须落实全部计划节拍，"
            f"当前为 {len(beats)} / {len(plan_beats)}"
        )
    if mode == "single-state":
        duration_ms = int(shot.get("end_ms", 0)) - int(shot.get("start_ms", 0))
        if len(plan_beats) != 1 or duration_ms >= A_ROLL_MULTI_STATE_THRESHOLD_MS:
            errors.append(f"{label} 仅单节拍且短于 4000ms 时允许 single-state")
        if not str(sequence.get("static_reason") or "").strip():
            errors.append(f"{label} single-state 必须说明 static_reason")

    evidence_paths: list[str] = []
    evidence_times: list[int] = []
    for position, beat in enumerate(beats, start=1):
        beat_label = f"{label} beat-{position}"
        if not isinstance(beat, dict):
            errors.append(f"{beat_label} 必须为对象")
            continue
        for key in ("trigger_text", "visual_state", "implementation"):
            if not str(beat.get(key) or "").strip():
                errors.append(f"{beat_label} 缺少 {key}")
        at_ms = beat.get("at_ms")
        if not isinstance(at_ms, int) or not shot["start_ms"] <= at_ms <= shot["end_ms"]:
            errors.append(f"{beat_label} at_ms 超出镜头边界")
        if position <= len(plan_beats):
            planned = plan_beats[position - 1]
            if at_ms != planned.get("at_ms"):
                errors.append(f"{beat_label} at_ms 与视觉计划节拍不一致")
            if normalize_text(beat.get("trigger_text")) != normalize_text(planned.get("trigger_text")):
                errors.append(f"{beat_label} trigger_text 与视觉计划旁白短语不一致")

        if stage != "produced":
            continue
        evidence = beat.get("evidence")
        if not isinstance(evidence, dict):
            errors.append(f"{beat_label} 缺少 produced evidence")
            continue
        artifact = str(evidence.get("artifact") or "")
        if not artifact:
            errors.append(f"{beat_label} evidence.artifact 不能为空")
        elif not resolve_project_path(project_dir, artifact).is_file():
            errors.append(f"{beat_label} evidence.artifact 不存在：{artifact}")
        else:
            evidence_paths.append(artifact)
        artifact_time_ms = evidence.get("artifact_time_ms")
        if mode in {"continuous-motion", "text-motion"}:
            if not isinstance(artifact_time_ms, int) or artifact_time_ms < 0:
                errors.append(f"{beat_label} {mode} 需要非负 artifact_time_ms")
            else:
                evidence_times.append(artifact_time_ms)

    if stage == "produced" and mode in {"state-sequence", "verified-media-sequence"}:
        if len(set(evidence_paths)) < len(plan_beats):
            errors.append(f"{label} {mode} 必须为每个节拍提供不同的证据资产")
    if stage == "produced" and mode in {"continuous-motion", "text-motion"}:
        if len(set(evidence_times)) < len(plan_beats):
            errors.append(f"{label} {mode} 必须为每个节拍提供不同的证据时间点")


def validate(project_dir: Path, prompts_path: Path, stage: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    checked: list[str] = []

    if not prompts_path.is_file():
        return {
            "schema_version": "0.1",
            "status": "fail",
            "stage": stage,
            "checked_records": [],
            "errors": [f"生产提示词不存在：{prompts_path}"],
            "warnings": [],
        }

    plan_path = project_dir / "planning" / "visual-plan.json"
    project_path = project_dir / "config" / "project.json"
    if not plan_path.is_file() or not project_path.is_file():
        missing = [str(path) for path in (plan_path, project_path) if not path.is_file()]
        return {
            "schema_version": "0.1",
            "status": "fail",
            "stage": stage,
            "checked_records": [],
            "errors": [f"缺少项目真源：{value}" for value in missing],
            "warnings": [],
        }

    plan = load(plan_path)
    project = load(project_path)
    design_report = validate_design(project_dir, stage)
    errors.extend(design_report["errors"])
    warnings.extend(design_report["warnings"])
    prompt_hash = sha256(prompts_path)

    validate_record(
        record_path=project_dir / "planning" / "visual-plan-prompt.json",
        project_dir=project_dir,
        expected_subject="visual-plan",
        required_prompt_ids={"visual-plan-v1"},
        prompt_hash=prompt_hash,
        stage="produced" if stage == "produced" else "prepared",
        errors=errors,
        checked=checked,
    )

    if stage != "planning":
        fixed_character = project.get("a_scene_mode") == "fixed-character-micro-scene"
        for shot in plan.get("shots") or []:
            shot_id = str(shot.get("id") or "unknown")
            if shot.get("screen_role") == "A":
                required = {"a-roll-image-v1", "a-roll-action-sequence-v1"}
                if fixed_character:
                    required.add("a-roll-view-v1")
                record_path = project_dir / "prompts" / "a-scenes" / f"{shot_id}.json"
                validate_record(
                    record_path=record_path,
                    project_dir=project_dir,
                    expected_subject=shot_id,
                    required_prompt_ids=required,
                    prompt_hash=prompt_hash,
                    stage=stage,
                    errors=errors,
                    checked=checked,
                )
                validate_a_roll_sequence(
                    record_path=record_path,
                    project_dir=project_dir,
                    shot=shot,
                    stage=stage,
                    errors=errors,
                )
            elif shot.get("screen_role") == "B":
                selection = f"planning/template-selection/{shot_id}.json"
                record_path = project_dir / "prompts" / "b-scenes" / f"{shot_id}.json"
                validate_record(
                    record_path=record_path,
                    project_dir=project_dir,
                    expected_subject=shot_id,
                    required_prompt_ids={"b-roll-motion-selection-v1"},
                    prompt_hash=prompt_hash,
                    stage=stage,
                    errors=errors,
                    checked=checked,
                    selection_report=selection,
                )
                validate_b_roll_sequence(
                    record_path=record_path,
                    project_dir=project_dir,
                    shot=shot,
                    stage=stage,
                    errors=errors,
                )

        bible_path = project_dir / "config" / "character-bible.json"
        if bible_path.is_file():
            bible = load(bible_path)
            if bible.get("generation_mode") == "generated-from-single-reference":
                validate_record(
                    record_path=project_dir / "prompts" / "character" / "turnaround.json",
                    project_dir=project_dir,
                    expected_subject="character-turnaround",
                    required_prompt_ids={"character-turnaround-v1"},
                    prompt_hash=prompt_hash,
                    stage=stage,
                    errors=errors,
                    checked=checked,
                )
            elif bible.get("generation_mode") not in {
                None,
                "user-supplied-turnaround",
                "not-required",
            }:
                warnings.append("character-bible.generation_mode 不是已知值")

    return {
        "schema_version": "0.1",
        "status": "pass" if not errors else "fail",
        "stage": stage,
        "production_prompts_sha256": prompt_hash,
        "checked_records": checked,
        "errors": errors,
        "warnings": warnings,
    }


def markdown(report: dict) -> str:
    records = report.get("checked_records") or ["无"]
    errors = report.get("errors") or ["无"]
    warnings = report.get("warnings") or ["无"]
    return "\n".join(
        [
            "# 生产提示词使用校验",
            "",
            f"- 状态：`{report['status']}`",
            f"- 阶段：`{report['stage']}`",
            "",
            "## 已检查实例",
            "",
            *(f"- {value}" for value in records),
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
        report = validate(args.project_dir, args.production_prompts, args.stage)
    except (OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "prompt-usage-validation.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json_path.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "out": str(json_path)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
