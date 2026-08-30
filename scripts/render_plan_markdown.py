#!/usr/bin/env python3
"""Render the human-readable visual-plan Markdown from its JSON source of truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def fmt_ms(value: int) -> str:
    minutes, remainder = divmod(value, 60000)
    seconds = remainder / 1000
    return f"{minutes:02d}:{seconds:06.3f}"


def render(plan: dict) -> str:
    lines = [
        "# 视觉分镜",
        "",
        f"- 项目：`{plan.get('project_id', '')}`",
        f"- 主画面模式：`{(plan.get('recommended_direction') or {}).get('a_scene_mode', '')}`",
        f"- 方向状态：`{(plan.get('recommended_direction') or {}).get('status', '')}`",
        "- 真源：`planning/visual-plan.json`",
        "",
    ]
    exceptions = plan.get("roll_run_exceptions") or []
    if exceptions:
        lines.extend(["## 连续同类画面说明", ""])
        lines.extend(
            f"- `{item.get('start_shot_id')}–{item.get('end_shot_id')}` · {item.get('screen_role')}-roll：{item.get('reason', '')}"
            for item in exceptions
        )
        lines.append("")
    for shot in plan.get("shots") or []:
        role = shot.get("screen_role")
        lines.extend(
            [
                f"## {shot.get('id')} · {role}-roll · {fmt_ms(shot['start_ms'])}–{fmt_ms(shot['end_ms'])}",
                "",
                f"- 原文：{shot.get('verbatim_text', '').replace(chr(10), ' / ')}",
                f"- 观众理解：{shot.get('viewer_takeaway', '')}",
                f"- 类型：`{shot.get('screen_subtype', '')}`",
            ]
        )
        if role == "A":
            lines.append(f"- A 视角：`{shot.get('a_view', '')}`")
        else:
            lines.extend(
                [
                    f"- 素材类型：`{shot.get('material_type', '')}`",
                    f"- 表现形式：`{shot.get('presentation_type', '')}`",
                    f"- 语义结构：`{shot.get('semantic_structure', '')}`",
                    f"- 具体模式：`{shot.get('semantic_pattern', '')}`",
                    f"- 信息项：{shot.get('item_count', '')}",
                    f"- 模板：`{shot.get('template_id') or 'none'}`",
                ]
            )
        design = shot.get("visual_design") or {}
        lines.extend(
            [
                f"- 画面：{design.get('subject', '')}",
                f"- 构图：{design.get('composition', '')}",
                f"- 终态：{design.get('final_state', '')}",
                "",
                "有效变化：",
                "",
            ]
        )
        lines.extend(
            f"- `{fmt_ms(change['at_ms'])}` {change.get('event', '')}"
            for change in shot.get("changes") or []
        )
        lines.extend(["", f"风险：{'；'.join(shot.get('risk') or []) or '无'}", ""])
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    data = json.loads(args.plan.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(data), encoding="utf-8")
    print(json.dumps({"status": "written", "out": str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
