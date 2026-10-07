#!/usr/bin/env python3
"""Validate local B-roll template metadata, sources, licenses, and readiness states."""

from __future__ import annotations

import argparse
import json
import hashlib
import math
from pathlib import Path

from broll_runtime import RUNTIMES, template_runtime, template_status
from media_evidence import digest
from broll_retrieval import validate_capabilities


def template_digest(template: dict) -> str:
    return hashlib.sha256(json.dumps(template, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def validate_evidence(project_dir: Path, template: dict) -> list[str]:
    """Check a certification record against the exact source, preview and supporting files."""
    errors = []
    label = template.get("id")
    try:
        evidence_path = (project_dir / template["validation_evidence"]).resolve()
        if Path(template["validation_evidence"]).is_absolute() or not evidence_path.is_relative_to(project_dir.resolve()):
            raise ValueError("认证报告须在项目内")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if evidence.get("schema_version") != "1.0" or evidence.get("template_id") != label or evidence.get("status") != "pass":
            errors.append(f"{label} 认证报告版本、模板 ID 或状态无效")
        if "template_sha256" in evidence and evidence["template_sha256"] != template_digest(template):
            errors.append(f"{label} 模板元数据与认证绑定不一致")
        files = evidence.get("files") or []
        indexed = {item["path"]: item["sha256"] for item in files}
        if len(indexed) != len(files) or len({(project_dir / p).resolve() for p in indexed}) != len(indexed):
            errors.append(f"{label} 认证文件重复")
        required = [template["source_file"], template["preview"]]
        font = (template.get("text_capacity") or {}).get("font_path")
        if not font:
            errors.append(f"{label} text_capacity 缺少实际 font_path")
        else:
            required.append(font)
        for value in required:
            if value not in indexed:
                errors.append(f"{label} 认证报告未绑定文件：{value}")
        for value, expected in indexed.items():
            path = (project_dir / value).resolve()
            if Path(value).is_absolute() or not path.is_relative_to(project_dir.resolve()) or digest(path) != expected:
                errors.append(f"{label} 认证文件越界或哈希过期：{value}")
        for key in ("render", "seek_safe", "chinese_capacity", "visual"):
            if (evidence.get("checks") or {}).get(key) != "pass":
                errors.append(f"{label} 未通过 {key} 验证")
        for key in ("width", "height", "fps"):
            value = (evidence.get("video") or {}).get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                errors.append(f"{label} 认证报告缺少有效 video.{key}")
        times = evidence.get("seek_times_ms")
        if (not isinstance(times, list) or any(type(v) is not int or v < 0 for v in times)
                or len(set(times)) < 3):
            errors.append(f"{label} 至少记录三个不同的 seek 验证时间")
        review = evidence.get("review") or {}
        if review.get("source") not in {"user", "agent-qa-under-user-authorization"} or review.get("evidence") not in indexed:
            errors.append(f"{label} 缺少真实审核来源与绑定的审阅证据")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.append(f"{label} 认证证据不可验证：{exc}")
    return errors


ALLOWED_STATUSES = {
    "styleframe-only",
    "implementation-required",
    "animation-verified",
    "superseded",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def validate(index_path: Path) -> dict:
    data = json.loads(index_path.read_text(encoding="utf-8"))
    project_dir = index_path.parent.parent
    errors: list[str] = []
    warnings: list[str] = []
    ids: set[str] = set()

    for position, template in enumerate(data.get("templates") or [], start=1):
        template_id = template.get("id") or f"template-{position}"
        if template_id in ids:
            errors.append(f"模板 ID 重复：{template_id}")
        ids.add(template_id)
        if not validate_capabilities(template.get("capabilities", {})):
            errors.append(f"{template_id} capabilities 须为约定的布尔型能力字段")
        for key in ("semantic_structure", "item_range", "duration_ms", "aspect_ratios", "source_file", "source"):
            if template.get(key) in (None, "", []):
                errors.append(f"{template_id} 缺少 {key}")

        status = template_status(template)
        if template_runtime(template) not in RUNTIMES:
            errors.append(f"{template_id} runtime 必须为 hyperframes 或 remotion")
        if status not in ALLOWED_STATUSES:
            errors.append(f"{template_id} 状态无效：{status}")
        source_file = template.get("source_file")
        if source_file and not (project_dir / source_file).resolve().is_file():
            errors.append(f"{template_id} source_file 不存在：{source_file}")
        source = template.get("source") or {}
        if not source.get("license"):
            errors.append(f"{template_id} 缺少 source.license")
        if status == "animation-verified":
            if template.get("metadata_version") == "1.0":
                for key in ("element_relation", "text_capacity", "replaceable_fields", "validation_evidence"):
                    if not template.get(key):
                        errors.append(f"{template_id} 缺少 {key}")
                for key in ("preview", "validation_evidence"):
                    if not template.get(key) or not (project_dir / template[key]).is_file():
                        errors.append(f"{template_id} {key} 文件不存在")
                if template.get("validation_evidence"):
                    errors.extend(validate_evidence(project_dir, template))
            else:
                warnings.append(f"{template_id} 旧模板未验证中文容量和渲染证据扩展字段")
            if str(source_file).lower().endswith(".svg"):
                errors.append(f"{template_id} 标记 animation-verified，但 source_file 仍是静态 SVG")
            if not template.get("preview"):
                errors.append(f"{template_id} 标记 animation-verified，但缺少 preview")
            phases = template.get("animation_phases")
            if not isinstance(phases, list) or len(phases) < 3:
                errors.append(f"{template_id} 标记 animation-verified，但 animation_phases 少于三个")

    return {
        "schema_version": "0.1",
        "status": "pass" if not errors else "fail",
        "template_count": len(ids),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    args = parse_args()
    report = validate(args.index)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "out": str(args.out)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
