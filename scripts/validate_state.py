#!/usr/bin/env python3
"""Validate approval hashes and stale-state consistency for one video project."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True, type=Path)
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


def validate(project_dir: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    project_path = project_dir / "config" / "project.json"
    visual_path = project_dir / "config" / "visual-style.json"
    project = load(project_path)
    visual = load(visual_path) if visual_path.is_file() else {}
    statuses = project.get("status") or {}
    approvals = project.get("approvals") or {}

    baseline_status = str(statuses.get("visual_baseline", ""))
    baseline_approval = approvals.get("visual_baseline") or {}
    approved_baseline_hash = baseline_approval.get("sha256")
    candidate = visual.get("candidate_review") or {}
    candidate_path = project_dir / str(candidate.get("path", "")) if candidate.get("path") else None
    if baseline_status == "approved":
        if not approved_baseline_hash:
            errors.append("视觉基线状态为 approved，但没有批准 SHA-256")
        if not candidate_path or not candidate_path.is_file():
            errors.append("视觉基线状态为 approved，但 candidate review 不存在")
        elif approved_baseline_hash and sha256(candidate_path) != approved_baseline_hash:
            errors.append("视觉基线批准 SHA-256 与 candidate review 不一致")
    elif approved_baseline_hash:
        warnings.append("视觉基线未批准，但仍保留非空批准 SHA-256")

    sample_status = str(statuses.get("sample", ""))
    sample_approval = approvals.get("sample") or {}
    sample_artifact = sample_approval.get("artifact")
    if sample_status == "approved":
        if baseline_status != "approved":
            errors.append("样片已批准，但当前视觉基线未批准")
        if not sample_approval.get("sha256") or not sample_artifact:
            errors.append("样片已批准，但缺少文件或 SHA-256")
        elif not (project_dir / sample_artifact).is_file():
            errors.append(f"样片文件不存在：{sample_artifact}")
        elif sha256(project_dir / sample_artifact) != sample_approval.get("sha256"):
            errors.append("样片批准 SHA-256 与文件不一致")

    manifests = list((project_dir / "hyperframes").glob("**/manifest.json")) if (project_dir / "hyperframes").exists() else []
    for manifest_path in manifests:
        manifest = load(manifest_path)
        manifest_hash = manifest.get("visual_baseline_review_sha256")
        if manifest_hash and manifest_hash != approved_baseline_hash:
            message = f"历史样片 {manifest_path.relative_to(project_dir)} 绑定旧视觉基线 {manifest_hash}"
            if sample_status == "stale":
                warnings.append(message)
            else:
                errors.append(message)

    bible_path = project_dir / "config" / "character-bible.json"
    if bible_path.is_file():
        bible = load(bible_path)
        if "approved" in str(bible.get("status", "")) and bible.get("review_required") is True:
            errors.append("人物状态含 approved，但 review_required=true")

    report = {
        "schema_version": "0.1",
        "status": "pass" if not errors else "fail",
        "project_id": project.get("project_id"),
        "current": {
            "character_identity": statuses.get("character_identity"),
            "plan": statuses.get("plan"),
            "visual_baseline": statuses.get("visual_baseline"),
            "sample": statuses.get("sample"),
            "final": statuses.get("final"),
        },
        "errors": errors,
        "warnings": warnings,
    }
    return report


def markdown(report: dict) -> str:
    errors = "\n".join(f"- {item}" for item in report["errors"]) or "- 无"
    warnings = "\n".join(f"- {item}" for item in report["warnings"]) or "- 无"
    return f"""# 项目状态校验

- 状态：`{report['status']}`
- 项目：`{report['project_id']}`

## 阻塞项

{errors}

## 历史与提醒

{warnings}
"""


def main() -> int:
    args = parse_args()
    try:
        report = validate(args.project_dir)
    except (OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "state-validation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.out_dir / "state-validation-report.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "out_dir": str(args.out_dir)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
