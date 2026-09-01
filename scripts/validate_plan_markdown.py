#!/usr/bin/env python3
"""Validate the user-facing seven-column visual-plan Markdown contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


TABLE_HEADER = "| 镜头 | 时间 | 配音文案 | 画面类型 | 画面设计 | 动态变化 | 画面衔接 |"
TABLE_SEPARATOR = "|---|---|---|---|---|---|---|"
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
        if values[2].replace("<br>", "\n") != str(shot.get("verbatim_text") or ""):
            errors.append(f"{expected_id} 配音文案与 JSON 的 verbatim_text 不一致")

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
