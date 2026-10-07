"""Check or copy one certified portable template without rewriting its evidence."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from media_evidence import digest, probe_video
from validate_template_index import template_digest, validate


def check(source_root: Path, target_root: Path, template_id: str) -> dict:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", template_id):
        raise ValueError("模板 ID 必须为小写字母、数字及连字符")
    source_root, target_root = source_root.resolve(), target_root.resolve()
    source_index = source_root / "templates/template-index.json"
    report = validate(source_index)
    if report["errors"]:
        raise ValueError("来源索引校验失败：" + "；".join(report["errors"]))
    entries = json.loads(source_index.read_text(encoding="utf-8"))["templates"]
    matches = [entry for entry in entries if entry.get("id") == template_id]
    if len(matches) != 1:
        raise ValueError("来源索引中未找到唯一模板")
    template = matches[0]
    if template.get("metadata_version") != "1.0" or template.get("animation_status") != "animation-verified":
        raise ValueError("只接受具有扩展证据的已认证模板，不能提升旧条目或草稿")
    prefix = Path("templates/library") / template_id
    package = source_root / prefix
    if (not package.is_dir() or package.is_symlink()
            or (hasattr(package, "is_junction") and package.is_junction())
            or not package.resolve().is_relative_to(source_root)):
        raise ValueError("缺少真实可移植模板目录")
    files = {}
    for path in package.rglob("*"):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("模板包不能包含链接或目录联接")
        if not path.resolve().is_relative_to(package.resolve()):
            raise ValueError("模板包路径越界")
        if any(part in {"node_modules", ".git", "__pycache__", ".cache"} for part in path.relative_to(package).parts):
            raise ValueError("模板包含安装目录或缓存")
        if path.is_file():
            files[path.relative_to(source_root).as_posix()] = digest(path)
    evidence_ref = template["validation_evidence"]
    if evidence_ref not in files:
        raise ValueError("认证报告必须在同一个模板包内")
    evidence = json.loads((source_root / evidence_ref).read_text(encoding="utf-8"))
    if evidence.get("template_sha256") != template_digest(template):
        raise ValueError("入库须有真实认证时的 template_sha256 元数据绑定，不补写旧证据")
    if (evidence.get("checks") or {}).get("portable") != "pass":
        raise ValueError("入库须完成可移植依赖与离开原工作区后的实际复现检查")
    bound = {item["path"]: item["sha256"] for item in evidence["files"]}
    expected = {key: value for key, value in files.items() if key != evidence_ref}
    if bound != expected:
        raise ValueError("模板包全部文件须精确绑定认证；缺失依赖、包外引用或额外文件不能入库")
    license_ref = (template.get("source") or {}).get("license_evidence")
    if license_ref not in bound:
        raise ValueError("缺少包内并绑定哈希的 source.license_evidence 分发依据")
    media = probe_video(source_root / template["preview"])
    video = evidence["video"]
    if any(abs(media[key] - video[key]) > 0.001 for key in ("width", "height", "fps")):
        raise ValueError("认证报告规格与实际预览不一致")
    if any(at_ms >= media["duration_ms"] for at_ms in evidence["seek_times_ms"]):
        raise ValueError("seek 验证时间超出真实预览时长")
    target_index = target_root / "templates/template-index.json"
    if not target_index.resolve().is_relative_to(target_root) or not (target_root / prefix).resolve().is_relative_to(target_root):
        raise ValueError("目标索引或模板目录越界")
    target_data = json.loads(target_index.read_text(encoding="utf-8"))
    if validate(target_index)["errors"]:
        raise ValueError("目标索引校验未通过")
    if any(item.get("id") == template_id for item in target_data.get("templates", [])) or (target_root / prefix).exists():
        raise ValueError("目标 ID 或目录已存在，不能覆盖")
    return {"template": template, "files": files, "package": prefix.as_posix(), "media": media,
            "target_index_sha256": digest(target_index)}


def promote(source_root: Path, target_root: Path, template_id: str, apply: bool = False) -> dict:
    report = check(source_root, target_root, template_id)
    if apply:
        index = target_root / "templates/template-index.json"
        data = json.loads(index.read_text(encoding="utf-8"))
        if digest(index) != report["target_index_sha256"]:
            raise ValueError("目标索引已变化，重新预检")
        data["templates"].append(report["template"])
        package = report["package"]
        # Preserve every byte and relative reference; do not regenerate certification hashes.
        shutil.copytree(source_root / package, target_root / package, symlinks=True)
        copied = {p.relative_to(target_root).as_posix(): digest(p)
                  for p in (target_root / package).rglob("*") if p.is_file() and not p.is_symlink()}
        if copied != report["files"] or any(p.is_symlink() for p in (target_root / package).rglob("*")):
            raise ValueError("复制后哈希不一致，未登记索引；保留目录供检查")
        if digest(index) != report["target_index_sha256"]:
            raise ValueError("复制期间目标索引已变化，未登记；保留目录供检查")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=index.parent,
                                         prefix="template-index-", suffix=".tmp", delete=False) as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            temporary = Path(handle.name)
        os.replace(temporary, index)
    return {"status": "pass", "applied": apply, "template_id": template_id,
            "package": report["package"], "files": len(report["files"]), "media": report["media"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-project", type=Path, required=True)
    parser.add_argument("--target-project", type=Path, required=True)
    parser.add_argument("--template-id", required=True)
    parser.add_argument("--apply", action="store_true", help="Copy verified package and append index; default is read-only")
    args = parser.parse_args()
    try:
        print(json.dumps(promote(args.source_project, args.target_project, args.template_id, args.apply), ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
