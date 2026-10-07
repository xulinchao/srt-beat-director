#!/usr/bin/env python3
"""Validate the visual-plan table and its derived per-shot production routes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from render_plan_markdown import (
    changes_text, design_text, display_type, md_cell, motion_intent_text,
    production_route_text, transition_text,
)


TABLE_HEADER = "| 镜头 | 时间 | 配音文案 | 画面类型 | 画面设计 | 动态变化 | 画面衔接 |"
TABLE_SEPARATOR = "|---|---|---|---|---|---|---|"
ROUTE_HEADER = "| 镜头 | A/B | 动效方式 | 主制作工具 | 决策依据与辅助链路 |"
ROUTE_SEPARATOR = "|---|---|---|---|---|"
TIME_RE = re.compile(r"^(\d+)ms-(\d+)ms$")
REQUIRED_SECTIONS = ("需要补充的素材", "需要确认的视觉方向", "制作难度较高的镜头")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--markdown", required=True, type=Path)
    parser.add_argument("--out-dir", type=Path)
    return parser.parse_args()


def split_row(line: str) -> list[str]:
    """Split a Markdown row while respecting escaped pipes inside a cell."""
    values: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if char == "|" and not escaped:
            values.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        escaped = char == "\\" and not escaped
        if char != "\\":
            escaped = False
    values.append("".join(current).strip())
    return values


def validate(plan: dict, markdown: str) -> dict:
    errors: list[str] = []
    lines = markdown.splitlines()
    try:
        header_index = lines.index(TABLE_HEADER)
    except ValueError:
        errors.append("缺少严格七列表头：" + TABLE_HEADER)
        header_index = -1

    rows: list[str] = []
    if header_index >= 0:
        if header_index + 1 >= len(lines) or lines[header_index + 1] != TABLE_SEPARATOR:
            errors.append("七列表头下一行必须是标准 Markdown 分隔线")
        for line in lines[header_index + 2 :]:
            if not line.startswith("|"):
                break
            rows.append(line)

    expected_shots = plan.get("shots") or []
    if len(rows) != len(expected_shots):
        errors.append(f"表格镜头行数为 {len(rows)}，但 JSON 镜头数为 {len(expected_shots)}")

    for index, (line, shot) in enumerate(zip(rows, expected_shots), start=1):
        cells = split_row(line)
        if len(cells) != 9 or cells[0] != "" or cells[-1] != "":
            errors.append(f"第 {index} 个镜头行不是七列：{line}")
            continue
        values = cells[1:-1]
        expected_id = f"S{index:03d}"
        if values[0] != expected_id or values[0] != shot.get("id"):
            errors.append(f"第 {index} 个镜头编号应为 {expected_id}，实际为 {values[0]}")
        match = TIME_RE.match(values[1])
        if not match:
            errors.append(f"{expected_id} 时间不是毫秒范围：{values[1]}")
        else:
            start_ms, end_ms = map(int, match.groups())
            if end_ms <= start_ms:
                errors.append(f"{expected_id} 结束时间不晚于开始时间")
            if start_ms != shot.get("start_ms") or end_ms != shot.get("end_ms"):
                errors.append(f"{expected_id} 表格时间与 JSON 不一致")
        if values[2] != md_cell(shot.get("verbatim_text") or ""):
            errors.append(f"{expected_id} 配音文案与 JSON 的 verbatim_text 不一致")
        for column, label, render_cell in (
            (3, "画面类型", display_type),
            (4, "画面设计", design_text),
            (5, "动态变化", changes_text),
            (6, "画面衔接", transition_text),
        ):
            if values[column] != md_cell(render_cell(shot)):
                errors.append(f"{expected_id} {label}与 JSON 不一致，请重新生成可读视图")

    try:
        route_section_index = lines.index("## 逐镜制作路由")
    except ValueError:
        errors.append("缺少表格后的逐镜制作路由")
        route_section_index = -1
    route_rows: list[str] = []
    if route_section_index >= 0:
        try:
            route_header_index = lines.index(ROUTE_HEADER, route_section_index + 1)
        except ValueError:
            errors.append("逐镜制作路由缺少标准表头")
            route_header_index = -1
        if route_header_index >= 0:
            if route_header_index + 1 >= len(lines) or lines[route_header_index + 1] != ROUTE_SEPARATOR:
                errors.append("逐镜制作路由表头下一行必须是标准 Markdown 分隔线")
            for line in lines[route_header_index + 2 :]:
                if not line.startswith("|"):
                    break
                route_rows.append(line)
    if len(route_rows) != len(expected_shots):
        errors.append(f"制作路由镜头行数为 {len(route_rows)}，但 JSON 镜头数为 {len(expected_shots)}")
    for index, (line, shot) in enumerate(zip(route_rows, expected_shots), start=1):
        cells = split_row(line)
        if len(cells) != 7 or cells[0] != "" or cells[-1] != "":
            errors.append(f"第 {index} 个制作路由行不是五列：{line}")
            continue
        values = cells[1:-1]
        expected_id = f"S{index:03d}"
        if values[0] != expected_id or values[0] != shot.get("id"):
            errors.append(f"第 {index} 个制作路由镜头编号应为 {expected_id}，实际为 {values[0]}")
        if values[1] != str(shot.get("screen_role") or ""):
            errors.append(f"{expected_id} 制作路由 A/B 职责与 JSON 不一致")
        if values[2] != md_cell(motion_intent_text(shot)):
            errors.append(f"{expected_id} 制作路由动效方式与 JSON 不一致")
        if not (shot.get("visual_design") or {}).get("motion_intent") and not shot.get("static_reason"):
            errors.append(f"{expected_id} JSON 缺少明确动效方式或静止理由")
        primary_tool = str((shot.get("production") or {}).get("primary_tool") or "")
        if not primary_tool.strip():
            errors.append(f"{expected_id} JSON 缺少主制作工具")
        if values[3] != md_cell(primary_tool):
            errors.append(f"{expected_id} 制作路由工具与 production.primary_tool 不一致")
        if values[4] != md_cell(production_route_text(shot)):
            errors.append(f"{expected_id} 制作路由决策依据与 JSON 不一致")
        if not values[2]:
            errors.append(f"{expected_id} 制作路由缺少动效方式")

    for section in REQUIRED_SECTIONS:
        if f"## {section}" not in markdown:
            errors.append(f"缺少表格后的检查部分：{section}")

    return {
        "schema_version": "0.1",
        "status": "pass" if not errors else "fail",
        "plan_shot_count": len(expected_shots),
        "markdown_row_count": len(rows),
        "errors": errors,
    }


def main() -> int:
    args = parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        markdown = args.markdown.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    report = validate(plan, markdown)
    out_dir = args.out_dir or args.markdown.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "plan-markdown-validation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    errors = "\n".join(f"- {item}" for item in report["errors"]) or "- 无"
    (out_dir / "plan-markdown-validation-report.md").write_text(
        f"# 视觉编排表格式校验\n\n- 状态：`{report['status']}`\n\n## 问题\n\n{errors}\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "out_dir": str(out_dir)}, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
