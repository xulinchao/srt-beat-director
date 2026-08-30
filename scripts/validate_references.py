#!/usr/bin/env python3
"""Validate reference scopes and optional character identity locks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROLES = {
    "character-identity",
    "visual-style",
    "layout-reference",
    "motion-reference",
    "verified-media",
}
VISUAL_FIELDS = {
    "global-palette",
    "background",
    "b-scene-ui",
    "layout",
    "typography",
    "motion-language",
}
VISUAL_ROLE_BY_FIELD = {
    "global-palette": "visual-style",
    "background": "visual-style",
    "b-scene-ui": "visual-style",
    "typography": "visual-style",
    "layout": "layout-reference",
    "motion-language": "motion-reference",
}
IDENTITY_KEYS = {"hair_color", "hair_shape", "body_proportion", "wardrobe", "signature_elements"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--character-bible", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate(index_path: Path, character_bible_path: Path | None = None) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    data = load(index_path)
    references = data.get("references") or []
    project_dir = index_path.parent.parent.parent
    ids: set[str] = set()
    by_id: dict[str, dict] = {}

    for position, reference in enumerate(references, start=1):
        label = reference.get("id") or f"reference-{position}"
        if label in ids:
            errors.append(f"参考 ID 重复：{label}")
        ids.add(label)
        by_id[label] = reference
        roles = set(reference.get("roles") or [])
        unknown_roles = sorted(roles - ROLES)
        if not roles:
            errors.append(f"{label} 未声明 roles")
        if unknown_roles:
            errors.append(f"{label} 存在未知 roles：{unknown_roles}")
        path_value = reference.get("path")
        if not path_value:
            errors.append(f"{label} 缺少 path")
        elif not (project_dir / path_value).is_file():
            errors.append(f"{label} 文件不存在：{path_value}")
        if not reference.get("source"):
            errors.append(f"{label} 缺少 source")

        allowed = set(reference.get("allowed_influence") or [])
        forbidden = set(reference.get("forbidden_influence") or [])
        overlap = sorted(allowed & forbidden)
        if overlap:
            errors.append(f"{label} 同时允许和禁止：{overlap}")
        for field in sorted(allowed & VISUAL_FIELDS):
            needed_role = VISUAL_ROLE_BY_FIELD[field]
            if needed_role not in roles:
                errors.append(f"{label} 允许 {field}，但未声明 {needed_role}")

        if "character-identity" in roles:
            lock = reference.get("identity_lock")
            if not isinstance(lock, dict):
                errors.append(f"{label} 缺少 identity_lock")
            else:
                missing = sorted(IDENTITY_KEYS - set(lock))
                if missing:
                    errors.append(f"{label} identity_lock 缺少字段：{missing}")
                for key in IDENTITY_KEYS:
                    value = lock.get(key)
                    if value in (None, "", []):
                        errors.append(f"{label} identity_lock.{key} 不能为空")
            if roles == {"character-identity"}:
                missing_forbidden = sorted(VISUAL_FIELDS - forbidden)
                if missing_forbidden:
                    warnings.append(f"{label} 建议显式禁止视觉扩散：{missing_forbidden}")

    if character_bible_path:
        bible = load(character_bible_path)
        identity_source = bible.get("identity_source") or {}
        reference_id = identity_source.get("reference_id")
        if reference_id not in by_id:
            errors.append("character-bible.identity_source.reference_id 无效")
        else:
            expected_lock = by_id[reference_id].get("identity_lock")
            if identity_source.get("lock") != expected_lock:
                errors.append("character-bible 的 identity lock 与原始人物参考不一致")
        if "approved" in str(bible.get("status", "")) and errors:
            errors.append("人物身份存在阻塞项，不能保持 approved 状态")

    return {
        "schema_version": "0.1",
        "status": "pass" if not errors else "fail",
        "reference_count": len(references),
        "errors": errors,
        "warnings": warnings,
    }


def markdown(report: dict) -> str:
    errors = "\n".join(f"- {item}" for item in report["errors"]) or "- 无"
    warnings = "\n".join(f"- {item}" for item in report["warnings"]) or "- 无"
    return f"""# 参考范围校验

- 状态：`{report['status']}`
- 参考数量：{report['reference_count']}

## 阻塞项

{errors}

## 提醒

{warnings}
"""


def main() -> int:
    args = parse_args()
    try:
        report = validate(args.index, args.character_bible)
    except (OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "reference-validation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.out_dir / "reference-validation-report.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "out_dir": str(args.out_dir)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
