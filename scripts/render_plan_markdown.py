#!/usr/bin/env python3
"""Render the eight-column visual plan and per-shot production routes from JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TABLE_HEADER = "| 镜头 | 时间 | 配音文案 | A-roll / B-roll | 画面类型 | 画面设计 | 动态变化 | 画面衔接 |"
TABLE_SEPARATOR = "|---|---|---|---|---|---|---|---|"
ROUTE_HEADER = "| 镜头 | A/B | 动效方式 | 主制作工具 | 决策依据与辅助链路 |"
ROUTE_SEPARATOR = "|---|---|---|---|---|"
DISPLAY_TYPES = {"人物画面", "场景画面", "真实素材", "信息图形", "文字动效"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def md_cell(value: object) -> str:
    """Keep table cells single-line without changing the spoken words."""
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = "<br>".join(part.strip() for part in text.split("\n"))
    return text.replace("|", "\\|").strip()


def fmt_ms(value: object) -> str:
    return f"{int(value)}ms"


def display_type(shot: dict) -> str:
    explicit = str(shot.get("display_type") or "").strip()
    if explicit in DISPLAY_TYPES:
        return explicit

    role = shot.get("screen_role")
    if role == "A":
        presentation = str(shot.get("presentation_type") or "").lower()
        subtype = str(shot.get("screen_subtype") or "").lower()
        if presentation in {"scene", "environment", "full-scene"} or "scene" in subtype:
            return "场景画面"
        return "人物画面"

    presentation = str(shot.get("presentation_type") or "").lower()
    material_type = str(shot.get("material_type") or "").lower()
    if presentation == "verified-media" or material_type == "verified-media":
        return "真实素材"
    if presentation == "text-motion" or material_type == "text-only":
        return "文字动效"
    if presentation == "scene":
        return "场景画面"
    return "信息图形"


def design_text(shot: dict) -> str:
    design = shot.get("visual_design") or {}
    parts: list[str] = []
    for label, key in (("功能", "function"), ("关系", "relation"), ("载体", "carrier"), ("角色职责", "character_role")):
        if design.get(key):
            parts.append(f"{label}：{design[key]}")
    if design.get("interaction"):
        parts.append("互动：" + json.dumps(design["interaction"], ensure_ascii=False))
    if shot.get("screen_role") == "B" and shot.get("visual_structure"):
        parts.append(f"结构：{shot['visual_structure']}")
    for label, key in (("主体", "subject"), ("构图", "composition"), ("景别", "shot_scale")):
        if design.get(key):
            parts.append(f"{label}：{design[key]}")
    elements = design.get("elements") or []
    if elements:
        parts.append("关键元素：" + "、".join(str(item) for item in elements))
    if design.get("final_state"):
        parts.append("终态：" + str(design["final_state"]))
    if design.get("motion_mode"):
        parts.append("运动方式：" + str(design["motion_mode"]))
    check = design.get("motion_check") or {}
    if check:
        parts.append("验收动作：" + str(check.get("action", "")))
        parts.append("可见结果：" + str(check.get("visible_result", "")))
        parts.append("必要状态：" + " → ".join(str(s.get("description", "")) for s in check.get("required_states", [])))
    if shot.get("static_reason"):
        parts.append("保持理由：" + str(shot["static_reason"]))
    return "；".join(parts) or "待补充"


def changes_text(shot: dict) -> str:
    changes = shot.get("changes") or []
    values: list[str] = []
    for index, change in enumerate(changes, start=1):
        event = change.get("event") or change.get("description") or ""
        at_ms = change.get("at_ms")
        prefix = f"{index}. "
        if isinstance(at_ms, int):
            prefix += f"{fmt_ms(at_ms)} "
        values.append(prefix + str(event))
    return "<br>".join(values) or "无有效变化（需说明静止理由）"


def transition_text(shot: dict) -> str:
    transition = shot.get("transition") or {}
    from_previous = transition.get("from_previous") or ""
    to_next = transition.get("to_next") or ""
    text = (f"前接：{from_previous}<br>后接：{to_next}" if from_previous and to_next
            else from_previous or to_next or "待补充")
    if "visual_cut" in transition:
        from visual_timing import cut_ms
        cut = transition["visual_cut"]
        at = cut_ms(shot)
        text += (f"<br>视觉切入：{at}ms（相对语义起点 {cut['offset_ms']:+d}ms）"
                 f"；理由：{cut.get('reason', '')}；交接画面：{cut.get('bridge', '')}")
    return text


def motion_intent_text(shot: dict) -> str:
    design = shot.get("visual_design") or {}
    intent = design.get("motion_intent")
    if isinstance(intent, (dict, list)):
        return json.dumps(intent, ensure_ascii=False)
    if intent:
        return str(intent)
    if shot.get("static_reason"):
        return "有理由静止：" + str(shot["static_reason"])
    return "按动态变化与旁白节拍实现（需明确方式）"


def production_route_text(shot: dict) -> str:
    production = shot.get("production") or {}
    decision = production.get("runtime_decision") or {}
    generation = production.get("video_generation") or {}
    parts: list[str] = []
    if decision.get("mode"):
        parts.append(f"决策：{decision['mode']}")
    if decision.get("reason"):
        parts.append(f"原因：{decision['reason']}")
    if generation.get("workflow"):
        parts.append(f"workflow：{generation['workflow']}")
    fallbacks = production.get("fallback_tools") or []
    if fallbacks:
        parts.append("回退：" + " → ".join(str(item) for item in fallbacks))
    return "；".join(parts) or "按逐镜计划制作"


def materials_gaps(plan: dict) -> list[str]:
    gaps: list[str] = []
    for shot in plan.get("shots") or []:
        production = shot.get("production") or {}
        asset_gap = str(production.get("asset_gap") or "").strip()
        material_text = "；".join(str(item) for item in shot.get("materials") or [])
        if asset_gap or "needs-supplied-material" in material_text or production.get("asset_status") == "gap":
            detail = asset_gap or material_text or "需要确认镜头素材"
            gaps.append(f"{shot.get('id')}：{detail}")
    return gaps


def direction_items(plan: dict) -> list[str]:
    direction = plan.get("recommended_direction") or {}
    items: list[str] = []
    if direction.get("a_scene_mode"):
        items.append(f"主画面模式：{direction['a_scene_mode']}")
    if direction.get("status") and direction.get("status") not in {"approved", "locked"}:
        items.append(f"方向状态：{direction['status']}")
    for key in ("style", "palette", "notes"):
        if direction.get(key):
            items.append(f"{key}：{direction[key]}")
    return items


def hard_shots(plan: dict) -> list[str]:
    values: list[str] = []
    for shot in plan.get("shots") or []:
        production = shot.get("production") or {}
        risks = [str(item) for item in shot.get("risk") or [] if str(item).strip()]
        if risks or production.get("asset_status") in {"to-generate", "in-progress", "failed", "gap"}:
            detail = "；".join(risks) or f"素材状态：{production.get('asset_status')}"
            values.append(f"{shot.get('id')}：{detail}")
    return values


def render(plan: dict) -> str:
    shots = plan.get("shots") or []
    a_count = sum(1 for shot in shots if shot.get("screen_role") == "A")
    b_count = sum(1 for shot in shots if shot.get("screen_role") == "B")
    gaps = materials_gaps(plan)
    directions = direction_items(plan)
    difficult = hard_shots(plan)

    lines = [
        "# 视觉编排表",
        "",
        f"- 项目：`{plan.get('project_id', '')}`",
        "- 时间真源：SRT/配音对齐轴；时间列保留语义边界，视觉切点另见画面衔接；单位为毫秒",
        f"- 镜头数：{len(shots)}（A-roll {a_count} / B-roll {b_count}）",
        "- 机器真源：`planning/visual-plan.json`",
        "",
        TABLE_HEADER,
        TABLE_SEPARATOR,
    ]
    for shot in shots:
        time = f"{fmt_ms(shot['start_ms'])}-{fmt_ms(shot['end_ms'])}"
        cells = [
            shot.get("id", ""),
            time,
            shot.get("verbatim_text", ""),
            {"A": "A-roll", "B": "B-roll"}.get(shot.get("screen_role"), "待确认"),
            display_type(shot),
            design_text(shot),
            changes_text(shot),
            transition_text(shot),
        ]
        lines.append("| " + " | ".join(md_cell(cell) for cell in cells) + " |")

    lines.extend(["", "## 逐镜制作路由", "", ROUTE_HEADER, ROUTE_SEPARATOR])
    for shot in shots:
        production = shot.get("production") or {}
        cells = [
            shot.get("id", ""),
            shot.get("screen_role", ""),
            motion_intent_text(shot),
            production.get("primary_tool", "待选择"),
            production_route_text(shot),
        ]
        lines.append("| " + " | ".join(md_cell(cell) for cell in cells) + " |")

    def section(title: str, values: list[str], empty: str = "无") -> None:
        lines.extend(["", f"## {title}", ""])
        lines.extend(f"- {value}" for value in (values or [empty]))

    lines.extend(
        [
            "",
            "## 全片检查",
            "",
            "- 语义覆盖、S001 连续编号、原文一致性和时间边界：由 `validate_plan.py` 校验。",
            "- A/B 职责、长镜头有效变化、连续同类镜头和素材真实性：见机器真源与 QA 报告。",
            "- 表格不是制作许可；视觉基线和审核状态通过后才进入资产与 ChatCut 组装。",
        ]
    )
    section("需要补充的素材", gaps)
    section("需要确认的视觉方向", directions)
    section("制作难度较高的镜头", difficult)
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
