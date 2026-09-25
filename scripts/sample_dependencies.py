"""Capture sample inputs without changing approvals or historical evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from media_evidence import digest
from validate_design import spec


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def current_dependencies(root: Path) -> dict:
    root = root.resolve()
    project = load(root / "config/project.json")
    plan = load(root / "planning/visual-plan.json")
    visual = load(root / "config/visual-style.json")
    paths = set()

    def add(value: str | Path) -> Path:
        path = (root / value).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"样片依赖不在项目内或不存在：{value}")
        paths.add(path.relative_to(root).as_posix())
        return path

    for value in ("planning/visual-plan.json", "config/visual-style.json"):
        add(value)
    for key in ("srt", "audio"):
        value = (project.get("inputs") or {}).get(key)
        if not value:
            raise ValueError(f"样片缺少 inputs.{key}")
        add(value)
    candidate = (visual.get("candidate_review") or {}).get("path")
    if not candidate:
        raise ValueError("样片缺少视觉基线 candidate_review.path")
    add(candidate)
    for value in ("config/character-bible.json", "input/references/index.json"):
        if (root / value).is_file():
            add(value)
    ref = visual.get("design_ref")
    if ref:
        design = add(ref["path"])
        documents = [(design, spec(design))]
        account = documents[0][1].get("account")
        if account:
            account_path = add(design.parent / account["path"])
            documents.append((account_path, spec(account_path)))
        for path, document in documents:
            for item in document.get("samples", []) + document.get("rules", {}).get("fonts", []):
                add(path.parent / item["path"])

    sample = project.get("sample") or {}
    start, end = sample.get("start_ms"), sample.get("end_ms")
    if type(start) is not int or type(end) is not int or not 0 <= start < end:
        raise ValueError("样片区间无效")
    selected = []
    shots = plan.get("shots") or []
    for index, shot in enumerate(shots):
        display_start = 0 if index == 0 else shot["start_ms"]
        display_end = shots[index + 1]["start_ms"] if index + 1 < len(shots) else end
        if display_start >= end or display_end <= start:
            continue
        selected.append(shot["id"])
        folder = "a-scenes" if shot["screen_role"] == "A" else "b-scenes"
        record_path = add(f"prompts/{folder}/{shot['id']}.json")
        record = load(record_path)
        assets = list(record.get("artifacts") or [])
        sequence = record.get("action_sequence" if shot["screen_role"] == "A" else "motion_sequence") or {}
        assets.extend((b.get("evidence") or {}).get("artifact") for b in sequence.get("beats", []))
        if not assets or any(not isinstance(v, str) or not v for v in assets):
            raise ValueError(f"{shot['id']} 样片资产证据不完整")
        for value in assets:
            add(value)
    if not selected:
        raise ValueError("样片区间未覆盖镜头")
    return {
        "settings": {key: project.get(key) for key in ("inputs", "video", "sample", "timeline_policy", "subtitle_safe_area", "a_scene_mode", "primary_timeline")},
        "shot_ids": selected,
        "files": [{"path": value, "sha256": digest(root / value)} for value in sorted(paths)],
    }


def validate_snapshot(root: Path, approval: dict) -> list[str]:
    reference = approval.get("dependencies")
    if not isinstance(reference, dict) or not reference.get("path") or not reference.get("sha256"):
        return ["样片审批缺少 dependencies 快照；复核样片后创建快照，不得补写旧批准冒充复核"]
    try:
        path = root / reference["path"]
        if digest(path) != reference["sha256"]:
            return ["样片依赖快照哈希不一致"]
        snapshot = load(path)
        if snapshot.get("schema_version") != "1.0":
            return ["样片依赖快照版本无效"]
        if snapshot.get("dependencies") != current_dependencies(root):
            return ["样片上游输入、计划、设计或资产已改变；标记 stale 并复核受影响内容"]
        if snapshot.get("sample_sha256") != approval.get("sha256") or snapshot.get("sample_artifact") != approval.get("artifact"):
            return ["样片依赖快照未绑定当前批准的样片"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"样片依赖无法验证：{exc}"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--sample", required=True, help="Project-relative sample artifact")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("快照已存在；使用新文件名保留历史证据")
    try:
        sample = (args.project_dir / args.sample).resolve()
        if not sample.is_relative_to(args.project_dir.resolve()):
            raise ValueError("样片必须位于项目内")
        report = {"schema_version": "1.0", "captured_at": datetime.now(timezone.utc).isoformat(),
                  "sample_artifact": args.sample, "sample_sha256": digest(sample),
                  "dependencies": current_dependencies(args.project_dir)}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"path": str(args.out), "sha256": digest(args.out), "approval_changed": False}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
