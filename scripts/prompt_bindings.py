"""Capture immutable production prompt sources and per-section bindings."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from media_evidence import digest


def section_hashes(path: Path) -> dict:
    return hashes_from_text(path.read_text(encoding="utf-8"))


def hashes_from_text(text: str) -> dict:
    sections = [[]]
    section_ids = [[]]
    fence = None
    for line in text.replace("\r\n", "\n").splitlines(keepends=True):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line.rstrip())
        if fence is None and line.startswith("## "):
            sections.append([])
            section_ids.append([])
        if fence is None:
            prompt_id = re.fullmatch(r"`prompt_id: ([a-z0-9-]+)`\s*", line)
            if prompt_id:
                section_ids[-1].append(prompt_id[1])
        sections[-1].append(line)
        if marker:
            token, suffix = marker.groups()
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not suffix.strip():
                fence = None
    if fence:
        raise ValueError("生产提示词代码围栏未闭合")
    prompts, shared = {}, []
    for lines, ids in zip(sections, section_ids):
        content = "".join(lines)
        if not ids:
            shared.append(content)
            continue
        if len(ids) != 1 or ids[0] in prompts:
            raise ValueError("生产提示词章节 ID 重复或不唯一")
        prompts[ids[0]] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if not prompts:
        raise ValueError("生产提示词缺少 prompt_id 章节")
    return {"common_sha256": hashlib.sha256("".join(shared).encode("utf-8")).hexdigest(),
            "prompts": prompts}


def selected_hashes(path: Path, prompt_ids: list[str]) -> dict:
    return select_hashes(section_hashes(path), prompt_ids)


def select_hashes(values: dict, prompt_ids: list[str]) -> dict:
    if (not isinstance(prompt_ids, list) or not prompt_ids
            or any(not isinstance(value, str) or not value for value in prompt_ids)
            or len(set(prompt_ids)) != len(prompt_ids)):
        raise ValueError("prompt_ids 必须非空且不重复")
    missing = set(prompt_ids) - values["prompts"].keys()
    if missing:
        raise ValueError(f"未知 prompt_ids：{sorted(missing)}")
    return {"common_sha256": values["common_sha256"],
            "prompts": {key: values["prompts"][key] for key in sorted(prompt_ids)}}


def validate_binding(root: Path, record: dict, current_source: Path) -> list[str]:
    try:
        binding = record["prompt_binding"]
        if not isinstance(binding, dict) or binding.get("policy") != "per-prompt-v1":
            raise ValueError("未知 prompt_binding.policy")
        reference = binding["source_snapshot"]
        root = root.resolve()
        archived = (root / reference["path"]).resolve()
        if Path(reference["path"]).is_absolute() or not archived.is_relative_to(root):
            raise ValueError("提示词原文快照必须位于项目内")
        if digest(archived) != reference["sha256"] or reference["sha256"] != record.get("prompt_source_sha256"):
            raise ValueError("执行时提示词原文快照哈希不一致")
        captured = {key: binding.get(key) for key in ("common_sha256", "prompts")}
        if captured != selected_hashes(archived, record["prompt_ids"]):
            raise ValueError("提示词分区绑定与执行时原文不一致")
        if captured != selected_hashes(current_source, record["prompt_ids"]):
            raise ValueError("所用提示词章节或共用规则已过期；需真实复核与重新执行")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [f"提示词分区绑定无法验证：{exc}"]
    return []


def capture(root: Path, source: Path, prompt_ids: list[str], archive: str, out: str) -> dict:
    raw = source.read_bytes()
    values = select_hashes(hashes_from_text(raw.decode("utf-8")), prompt_ids)
    root = root.resolve()
    paths = [(root / value).resolve() for value in (archive, out)]
    if any(Path(value).is_absolute() or not path.is_relative_to(root)
           for value, path in zip((archive, out), paths)):
        raise ValueError("输出必须是项目内相对路径")
    if paths[0] == paths[1] or any(path.exists() for path in paths):
        raise ValueError("输出已存在或重名；使用新文件名，不覆盖历史")
    source_hash = hashlib.sha256(raw).hexdigest()
    result = {"prompt_ids": prompt_ids, "prompt_source": "references/production-prompts.md",
              "prompt_source_sha256": source_hash,
              "prompt_binding": {"policy": "per-prompt-v1", **values,
                                 "source_snapshot": {"path": archive, "sha256": source_hash}}}
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    with paths[0].open("xb") as handle:
        handle.write(raw)
    with paths[1].open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--prompt-id", action="append", required=True)
    parser.add_argument("--archive", required=True, help="Project-relative immutable source copy")
    parser.add_argument("--out", required=True, help="Project-relative new binding JSON")
    args = parser.parse_args()
    try:
        capture(args.project_dir, args.source, args.prompt_id, args.archive, args.out)
        print(json.dumps({"out": args.out, "approval_changed": False}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
