#!/usr/bin/env python3
"""Validate that production prompts were instantiated and actually used."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


VALID_STATUSES = {"prepared", "used", "completed", "failed"}
ACTIVE_STATUSES = {"used", "completed"}


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
    if stage == "produced" and status not in ACTIVE_STATUSES:
        errors.append(f"{label} 尚未实际使用：status={status}")

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
                required = {"a-roll-image-v1"}
                if fixed_character:
                    required.add("a-roll-view-v1")
                validate_record(
                    record_path=project_dir / "prompts" / "a-scenes" / f"{shot_id}.json",
                    project_dir=project_dir,
                    expected_subject=shot_id,
                    required_prompt_ids=required,
                    prompt_hash=prompt_hash,
                    stage=stage,
                    errors=errors,
                    checked=checked,
                )
            elif shot.get("screen_role") == "B":
                selection = f"planning/template-selection/{shot_id}.json"
                validate_record(
                    record_path=project_dir / "prompts" / "b-scenes" / f"{shot_id}.json",
                    project_dir=project_dir,
                    expected_subject=shot_id,
                    required_prompt_ids={"b-roll-motion-selection-v1"},
                    prompt_hash=prompt_hash,
                    stage=stage,
                    errors=errors,
                    checked=checked,
                    selection_report=selection,
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
