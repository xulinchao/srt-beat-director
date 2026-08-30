#!/usr/bin/env python3
"""Create a non-destructive Knowledge A/B-roll Video project from SRT and audio."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("--srt", required=True, type=Path)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--aspect-ratio", required=True, choices=["9:16", "16:9", "1:1", "4:5"])
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument("--height", required=True, type=int)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--a-scene-mode",
        choices=["fixed-character-micro-scene", "full-ai-scene"],
        required=True,
    )
    parser.add_argument("--sample-end-ms", type=int, default=45000)
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

    input_dir = args.project_dir / "input"
    config_dir = args.project_dir / "config"
    planning_dir = args.project_dir / "planning"
    templates_dir = args.project_dir / "templates"
    for directory in (input_dir, config_dir, planning_dir, templates_dir):
        directory.mkdir(parents=True, exist_ok=True)

    shutil.copy2(args.srt, input_dir / "source.srt")
    audio_suffix = args.audio.suffix.lower() or ".mp3"
    audio_name = f"narration{audio_suffix}"
    shutil.copy2(args.audio, input_dir / audio_name)

    project = {
        "schema_version": "0.2",
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
        "a_scene_mode": args.a_scene_mode,
        "a_scene_mode_status": "user-specified",
        "subtitle_safe_area": {"bottom_fraction": 0.22},
        "timeline_policy": {
            "initial_gap": "show-first-shot",
            "inter_shot_gap": "hold-previous-shot",
            "tail_gap": "hold-last-shot",
        },
        "sample": {"start_ms": 0, "end_ms": args.sample_end_ms},
        "status": {
            "character_identity": "pending" if args.a_scene_mode == "fixed-character-micro-scene" else "not-required",
            "plan": "draft",
            "visual_baseline": "pending",
            "sample": "pending",
            "final": "pending",
        },
        "approvals": {
            "plan": {"sha256": None, "approved_at": None},
            "visual_baseline": {"sha256": None, "approved_at": None},
            "sample": {"sha256": None, "approved_at": None},
        },
    }
    (config_dir / "project.json").write_text(
        json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    skill_templates = Path(__file__).resolve().parents[1] / "templates"
    shutil.copy2(skill_templates / "template-index.json", templates_dir / "template-index.json")
    shutil.copytree(
        skill_templates / "hyperframes-dark-broll",
        templates_dir / "hyperframes-dark-broll",
        dirs_exist_ok=False,
    )
    print(json.dumps({"status": "created", "project_dir": str(args.project_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
