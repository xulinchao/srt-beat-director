#!/usr/bin/env python3
"""Check versioned DESIGN references, parameters and narration-bound interactions."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spec(path: Path) -> dict:
    blocks = re.findall(r"^```design-spec\s*\n(.*?)^```", path.read_text(encoding="utf-8"), re.M | re.S)
    if len(blocks) != 1:
        raise ValueError(f"{path}: 必须只有一个 design-spec 块")
    value = json.loads(blocks[0])
    if not isinstance(value, dict) or value.get("schema_version") != "1.0" or not value.get("version"):
        raise ValueError(f"{path}: 无效设计版本")
    if not isinstance(value.get("rules"), dict):
        raise ValueError(f"{path}: rules 必须为对象")
    return value


def validate(project_dir: Path, stage: str = "planning", check_records: bool = True) -> dict:
    errors, warnings = [], []
    try:
        project = load(project_dir / "config/project.json")
        visual_path = project_dir / "config/visual-style.json"
        visual = load(visual_path) if visual_path.is_file() else {}
        plan_path = project_dir / "planning/visual-plan.json"
        plan = load(plan_path) if plan_path.is_file() else {}
        enabled = project.get("design_contract_version")
        if enabled is None and not visual.get("design_ref") and not plan.get("design_ref"):
            return {"status": "pass", "errors": [], "warnings": ["旧任务尚未接入 DESIGN；不代表设计已验证"]}
        if enabled != "1.0":
            errors.append("design_contract_version 必须为 1.0")
        ref = visual.get("design_ref")
        if not isinstance(ref, dict) or not all(ref.get(k) for k in ("path", "version", "sha256")):
            if stage == "planning":
                warnings.append("设计引用待补齐，仅可作为草稿")
            else:
                errors.append("缺少完整 design_ref")
        else:
            path = project_dir / ref["path"]
            film = spec(path)
            if film.get("scope") != "film":
                errors.append("单片 DESIGN scope 必须为 film")
            if digest(path) != ref["sha256"] or film["version"] != ref["version"]:
                errors.append("单片 DESIGN 引用版本或哈希过期")
            rules, font_root = {}, path.parent
            documents = [(path, film)]
            account = film.get("account")
            if account:
                account_path = path.parent / account["path"]
                base = spec(account_path)
                if base.get("scope") != "account" or base.get("account"):
                    errors.append("账号规范必须为 account 且不递归继承")
                if digest(account_path) != account.get("sha256") or base["version"] != account.get("version"):
                    errors.append("账号 DESIGN 引用版本或哈希过期")
                rules.update(base["rules"])
                font_root = account_path.parent
                documents.append((account_path, base))
            if "fonts" in film["rules"]:
                font_root = path.parent
            rules.update(film["rules"])
            if plan.get("design_ref") != ref:
                errors.append("计划 design_ref 与视觉规范不一致")
            if visual.get("resolved_design") != rules:
                errors.append("resolved_design 与 DESIGN 合并结果不一致")
            review = visual.get("design_review") or {}
            if stage != "planning" or review.get("status") == "approved":
                if review.get("status") != "approved" or review.get("sha256") != ref["sha256"]:
                    errors.append("当前 DESIGN 未批准或审批过期")
                source = review.get("review_source")
                if source not in {"user", "agent-qa-under-user-authorization"}:
                    errors.append("design_review 缺少有效审核来源")
                if source == "agent-qa-under-user-authorization" and project.get("review_mode") != "continuous":
                    errors.append("manual 模式不能使用代理批准")
                if not review.get("evidence") or not (project_dir / review["evidence"]).is_file():
                    errors.append("缺少设计审阅证据文件")
            required = ("video", "fonts", "font_sizes", "max_chars_per_line", "max_lines", "margin_fraction", "subtitle_bottom_fraction", "colors", "graphic_language", "character_direction", "scene_density", "motion")
            if stage != "planning":
                for key in required:
                    if rules.get(key) in (None, "", [], {}):
                        errors.append(f"DESIGN 缺少 {key}")
                if not any(d.get("samples") for _, d in documents):
                    errors.append("DESIGN 缺少可比对样张")
            for doc_path, doc in documents:
                for sample in doc.get("samples", []):
                    sample_path = doc_path.parent / sample["path"]
                    if not sample_path.is_file() or digest(sample_path) != sample.get("sha256"):
                        errors.append(f"样张缺失或哈希不符：{sample_path}")
            if "video" in rules and any(rules["video"].get(k) != project.get("video", {}).get(k) for k in ("width", "height", "fps", "aspect_ratio")):
                errors.append("DESIGN video 与 project 不一致")
            if "subtitle_bottom_fraction" in rules and rules["subtitle_bottom_fraction"] != project.get("subtitle_safe_area", {}).get("bottom_fraction"):
                errors.append("DESIGN 字幕区与 project 不一致")
            for key in ("margin_fraction", "subtitle_bottom_fraction"):
                if key in rules and (type(rules[key]) not in (int, float) or not 0 <= rules[key] < 1):
                    errors.append(f"{key} 必须在 [0,1) 内")
            for key in ("max_chars_per_line", "max_lines"):
                if key in rules and (type(rules[key]) is not int or rules[key] <= 0):
                    errors.append(f"{key} 必须为正整数")
            for size in rules.get("font_sizes", {}).values():
                if type(size) not in (int, float) or size <= 0:
                    errors.append("font_sizes 必须为正数")
            for font in rules.get("fonts", []):
                if not font.get("family") or not font.get("path") or not (font_root / font["path"]).is_file():
                    errors.append("字体名称或文件缺失")
            records = [project_dir / "planning/visual-plan-prompt.json"]
            if stage != "planning":
                for shot in plan.get("shots", []):
                    folder = "a-scenes" if shot.get("screen_role") == "A" else "b-scenes"
                    records.append(project_dir / "prompts" / folder / f"{shot['id']}.json")
                    if shot.get("screen_role") == "B":
                        records.append(project_dir / "planning/template-selection" / f"{shot['id']}.json")
            for record in records if check_records else []:
                if not record.is_file() or load(record).get("design_ref") != ref:
                    errors.append(f"提示词/选型设计引用缺失或不一致：{record}")
        for shot in plan.get("shots", []):
            design = shot.get("visual_design", {})
            for key in ("function", "relation", "carrier", "character_role"):
                if not isinstance(design.get(key), str) or not design[key].strip():
                    errors.append(f"{shot.get('id')} 缺少 visual_design.{key}")
            interaction = design.get("interaction")
            if interaction is None:
                continue
            for key in ("participants", "layout", "occlusion", "events", "fallback"):
                if not interaction.get(key):
                    errors.append(f"{shot.get('id')} interaction 缺少 {key}")
            beats = shot.get("narration_beats", [])
            for event in interaction.get("events", []):
                index = event.get("beat_index")
                offset, duration = event.get("offset_ms"), event.get("duration_ms")
                if type(index) is not int or not 0 <= index < len(beats):
                    errors.append(f"{shot.get('id')} interaction 无效 beat_index")
                    continue
                limit = beats[index + 1]["at_ms"] if index + 1 < len(beats) else shot["end_ms"]
                if type(offset) is not int or type(duration) is not int or offset < 0 or duration < 0 or beats[index]["at_ms"] + offset + duration > limit:
                    errors.append(f"{shot.get('id')} interaction 越过旁白节拍边界")
                for key in ("action", "contact", "reaction"):
                    if not event.get(key):
                        errors.append(f"interaction event 缺少 {key}")
                if any(event.get(k) not in interaction.get("participants", []) for k in ("actor", "target")):
                    errors.append("interaction actor/target 未登记")
            if stage == "produced":
                if not interaction.get("assets"):
                    errors.append("interaction 缺少实际资产")
                for asset in interaction.get("assets", []):
                    if not asset.get("path") or not (project_dir / asset["path"]).is_file():
                        errors.append("interaction 资产文件不存在")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        errors.append(f"DESIGN 数据不可检查：{exc}")
    return {"status": "fail" if errors else "pass", "errors": errors, "warnings": warnings}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=("planning", "prepared", "produced"), default="planning")
    args = parser.parse_args()
    report = validate(args.project_dir, args.stage)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(2 if report["errors"] else 0)
