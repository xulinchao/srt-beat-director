#!/usr/bin/env python3
"""Create a non-destructive Knowledge A/B-roll Video project from SRT and audio."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def probe_audio_duration_ms(path: Path) -> int | None:
    """读取音频时长。环境缺少 ffprobe 或读取失败时返回 None，不视为初始化失败。"""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        return None
    try:
        return round(float(json.loads(completed.stdout)["format"]["duration"]) * 1000)
    except (KeyError, TypeError, ValueError):
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("--srt", required=True, type=Path)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--aspect-ratio", required=True, choices=["9:16", "16:9", "1:1", "4:5"])
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument("--height", required=True, type=int)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--primary-timeline", choices=["chatcut", "hyperframes"], default="chatcut")
    parser.add_argument("--review-mode", choices=["manual", "continuous"], default="manual")
    parser.add_argument(
        "--a-scene-mode",
        choices=["fixed-character-micro-scene", "full-ai-scene"],
        required=True,
    )
    parser.add_argument(
        "--sample-end-ms",
        type=int,
        default=45000,
        help="样片结束毫秒；能读到音频时长且小于该值时，自动收敛到音频时长",
    )
    parser.add_argument(
        "--repositories-root",
        type=str,
        default=None,
        help="本地参考仓库根目录路径，写入 project.json 的 repositories_root 字段",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    if not args.srt.is_file():
        errors.append(f"SRT 不存在：{args.srt}")
    if not args.audio.is_file():
        errors.append(f"音频不存在：{args.audio}")
    if args.width <= 0 or args.height <= 0 or args.fps <= 0:
        errors.append("width、height 和 fps 必须为正整数")
    if args.sample_end_ms <= 0:
        errors.append("sample-end-ms 必须大于 0")
    if args.project_dir.exists() and any(args.project_dir.iterdir()):
        errors.append(f"目标目录不是空目录，拒绝覆盖：{args.project_dir}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2

    audio_duration_ms = probe_audio_duration_ms(args.audio)
    sample_end_ms = args.sample_end_ms
    warnings: list[str] = []
    if audio_duration_ms is not None:
        if sample_end_ms > audio_duration_ms:
            warnings.append(f"样片区间 {sample_end_ms}ms 超过音频时长，已收敛到 {audio_duration_ms}ms")
            sample_end_ms = audio_duration_ms
    else:
        warnings.append("未能读取音频时长（ffprobe 不可用或读取失败），样片区间未校验，需人工核对")

    input_dir = args.project_dir / "input"
    config_dir = args.project_dir / "config"
    planning_dir = args.project_dir / "planning"
    template_selection_dir = planning_dir / "template-selection"
    broll_research_dir = planning_dir / "broll-research"
    templates_dir = args.project_dir / "templates"
    for directory in (
        input_dir,
        config_dir,
        planning_dir,
        template_selection_dir,
        broll_research_dir,
        templates_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    shutil.copy2(args.srt, input_dir / "source.srt")
    audio_suffix = args.audio.suffix.lower() or ".mp3"
    audio_name = f"narration{audio_suffix}"
    shutil.copy2(args.audio, input_dir / audio_name)

    # --repositories-root: 用户显式提供则转绝对路径；否则推断 Skill 根目录下的 research/reference-repos
    if args.repositories_root:
        repositories_root = Path(args.repositories_root).resolve().as_posix()
    else:
        inferred = Path(__file__).resolve().parents[1] / "research" / "reference-repos"
        repositories_root = inferred.as_posix() if inferred.is_dir() else None

    project = {
        "schema_version": "0.3",
        "design_contract_version": "1.0",
        "motion_review_policy": "evidence-first-v1",
        "sequence_review_policy": "sequence-quality-v1",
        "sequence_review": {"sample": None, "full": None},
        "project_id": args.project_dir.name,
        "inputs": {"srt": "input/source.srt", "audio": f"input/{audio_name}"},
        "output": {"directory": "render", "filename": "final.mp4"},
        "video": {
            "aspect_ratio": args.aspect_ratio,
            "width": args.width,
            "height": args.height,
            "fps": args.fps,
            "status": "user-specified",
        },
        "primary_timeline": args.primary_timeline,
        "review_mode": args.review_mode,
        "chatcut": {
            "project_id": None,
            "project_name": None,
            "timeline_id": None,
            "timeline_name": None,
        },
        "a_scene_mode": args.a_scene_mode,
        "a_scene_mode_status": "user-specified",
        "subtitle_safe_area": {"bottom_fraction": 0.22},
        "timeline_policy": {
            "initial_gap": "show-first-shot",
            "inter_shot_gap": "hold-previous-shot",
            "tail_gap": "hold-last-shot",
        },
        "sample": {"start_ms": 0, "end_ms": sample_end_ms},
        "status": {
            "character_identity": "pending" if args.a_scene_mode == "fixed-character-micro-scene" else "not-required",
            "plan": "draft",
            "visual_baseline": "pending",
            "sample": "pending",
            "final": "pending",
        },
        "approvals": {
            "plan": {"sha256": None, "approved_at": None, "review_source": None},
            "visual_baseline": {"sha256": None, "approved_at": None, "review_source": None},
            "sample": {"sha256": None, "approved_at": None, "review_source": None, "artifact": None, "dependencies": None},
            "final": {"sha256": None, "approved_at": None, "review_source": None},
        },
        "final_artifact": None,
        "repositories_root": repositories_root,
    }
    (config_dir / "project.json").write_text(
        json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    skill_templates = Path(__file__).resolve().parents[1] / "templates"
    shutil.copy2(skill_templates / "template-index.json", templates_dir / "template-index.json")
    # Certified templates keep their complete, portable bundle under templates/library/.
    if (skill_templates / "library").is_dir():
        shutil.copytree(skill_templates / "library", templates_dir / "library")
    print(
        json.dumps(
            {
                "status": "created",
                "project_dir": str(args.project_dir),
                "sample_end_ms": sample_end_ms,
                "warnings": warnings,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
