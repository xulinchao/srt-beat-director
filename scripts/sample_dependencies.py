"""Capture sample inputs without changing approvals or historical evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from media_evidence import digest
from validate_design import spec
from sequence_quality import POLICY as SEQUENCE_POLICY, validate as validate_sequence_quality
from visual_timing import display_ranges


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def current_dependencies(root: Path, schema_version: str = "1.0") -> dict:
    if schema_version not in {"1.0", "2.0"}:
        raise ValueError("样片依赖快照版本无效")
    root = root.resolve()
    project = load(root / "config/project.json")
    if project.get("sequence_review_policy") == SEQUENCE_POLICY and schema_version != "2.0":
        raise ValueError("新连续镜头质量门必须使用2.0样片依赖快照，绑定实际质量证据")
    plan = load(root / "planning/visual-plan.json")
    visual = load(root / "config/visual-style.json")
    paths = set()

    def add(value: str | Path) -> Path:
        path = (root / value).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"样片依赖不在项目内或不存在：{value}")
        paths.add(path.relative_to(root).as_posix())
        return path

    for value in (("planning/visual-plan.json", "config/visual-style.json")
                  if schema_version == "1.0" else ("config/visual-style.json",)):
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
    scoped_shots = []
    shots = plan.get("shots") or []
    ranges = display_ranges(shots, end)
    for index, shot in enumerate(shots):
        display_start, display_end = ranges[index]
        if display_start >= end or display_end <= start:
            continue
        selected.append(shot["id"])
        scoped_shots.append({"shot": shot, "display_range_ms": [max(start, display_start), min(end, display_end)]})
        folder = "a-scenes" if shot["screen_role"] == "A" else "b-scenes"
        record_path = add(f"prompts/{folder}/{shot['id']}.json")
        record = load(record_path)
        assets = list(record.get("artifacts") or [])
        if schema_version == "2.0":
            assets = [v.get("path") if isinstance(v, dict) else v for v in assets]
        sequence = record.get("action_sequence" if shot["screen_role"] == "A" else "motion_sequence") or {}
        assets.extend((b.get("evidence") or {}).get("artifact") for b in sequence.get("beats", []))
        if not assets or any(not isinstance(v, str) or not v for v in assets):
            raise ValueError(f"{shot['id']} 样片资产证据不完整")
        for value in assets:
            add(value)
        if schema_version == "2.0":
            review = record.get("layout_review") or {}
            extra = list(review.get("artifacts") or [])
            extra.extend((shot.get("production") or {}).get("source_files") or [])
            for value in (record.get("selection_report"), shot.get("broll_research_record"),
                          review.get("dynamic_preview"),
                          ((record.get("prompt_binding") or {}).get("source_snapshot") or {}).get("path")):
                if value:
                    extra.append(value)
            for value in extra:
                add(value)
    if not selected:
        raise ValueError("样片区间未覆盖镜头")
    if schema_version == "2.0" and project.get("sequence_review_policy") == SEQUENCE_POLICY:
        quality = validate_sequence_quality(root, "sample", plan=plan, project=project)
        if quality["errors"]:
            raise ValueError("样片连续镜头质量证据未通过：" + "; ".join(quality["errors"]))
        for value in quality["files"]:
            add(value)
    dependencies = {
        "settings": {key: project.get(key) for key in ("inputs", "video", "sample", "timeline_policy", "subtitle_safe_area", "a_scene_mode", "primary_timeline")},
        "shot_ids": selected,
        "files": [{"path": value, "sha256": digest(root / value)} for value in sorted(paths)],
    }
    if schema_version == "2.0":
        if project.get("sequence_review_policy") == SEQUENCE_POLICY:
            dependencies["settings"]["sequence_review_policy"] = project["sequence_review_policy"]
            dependencies["settings"]["sequence_review_sample"] = (project.get("sequence_review") or {}).get("sample")
        # Unknown root fields remain shared dependencies; only shots are scoped.
        dependencies["plan_scope"] = {"shared": {k: v for k, v in plan.items() if k != "shots"},
                                      "shots": scoped_shots}
    return dependencies


def validate_snapshot(root: Path, approval: dict) -> list[str]:
    reference = approval.get("dependencies")
    if not isinstance(reference, dict) or not reference.get("path") or not reference.get("sha256"):
        return ["样片审批缺少 dependencies 快照；复核样片后创建快照，不得补写旧批准冒充复核"]
    try:
        root = root.resolve()
        path = (root / reference["path"]).resolve()
        if Path(reference["path"]).is_absolute() or not path.is_relative_to(root):
            return ["样片依赖快照必须位于项目内"]
        if digest(path) != reference["sha256"]:
            return ["样片依赖快照哈希不一致"]
        snapshot = load(path)
        version = snapshot.get("schema_version")
        if version not in {"1.0", "2.0"}:
            return ["样片依赖快照版本无效"]
        if load(root / "config/project.json").get("sequence_review_policy") == SEQUENCE_POLICY and version != "2.0":
            return ["新连续镜头质量门必须使用2.0样片依赖快照"]
        if snapshot.get("dependencies") != current_dependencies(root, version):
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
        if not args.out.resolve().is_relative_to(args.project_dir.resolve()):
            raise ValueError("快照必须保存于项目内")
        sample = (args.project_dir / args.sample).resolve()
        if Path(args.sample).is_absolute() or not sample.is_relative_to(args.project_dir.resolve()):
            raise ValueError("样片必须位于项目内")
        report = {"schema_version": "2.0", "captured_at": datetime.now(timezone.utc).isoformat(),
                  "sample_artifact": args.sample, "sample_sha256": digest(sample),
                  "dependencies": current_dependencies(args.project_dir, "2.0")}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"path": str(args.out), "sha256": digest(args.out), "approval_changed": False}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
