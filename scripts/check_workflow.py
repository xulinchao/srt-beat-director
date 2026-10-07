#!/usr/bin/env python3
"""Inspect existing truth and run the checks required BEFORE a production action.

Read-only except an optional derived report. Never renders, connects to an app,
changes approvals, or executes a caller-supplied command.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from validate_state import validate as validate_state
from validate_prompt_usage import validate as validate_prompts
from validate_plan_markdown import validate as validate_markdown
from validate_delivery import validate as validate_delivery
from sequence_quality import validate as validate_sequence

ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ("status", "baseline", "assets", "assemble", "expand", "candidate",
           "delivery-review", "delivery-final")


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 必须为对象：{path}")
    return value


def check_plan(root: Path) -> dict:
    # Reuse the existing CLI unchanged; its generated reports stay outside the
    # user's project, so a status/check operation never rewrites project truth.
    with tempfile.TemporaryDirectory(prefix="knowledge-plan-check-") as output:
        command = [sys.executable, "-B", "-X", "utf8", str(ROOT / "scripts/validate_plan.py"),
                   "--project", str(root / "config/project.json"),
                   "--preflight", str(root / "planning/preflight-report.json"),
                   "--content-analysis", str(root / "planning/content-analysis.json"),
                   "--visual-plan", str(root / "planning/visual-plan.json"),
                   "--out-dir", output]
        index = root / "templates/template-index.json"
        if index.is_file():
            command += ["--template-index", str(index)]
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=60)
        path = Path(output) / "plan-validation-report.json"
        if path.is_file():
            report = load(path)
            if result.returncode and not report.get("errors"):
                report.setdefault("errors", []).append("计划检查退出异常")
                report["status"] = "fail"
            return report
        return {"status": "fail", "errors": ["计划检查未产出报告：" +
                (result.stderr or result.stdout).strip()], "warnings": []}


def check(root: Path, action: str = "status", tool: str | None = None,
          shot_id: str | None = None) -> dict:
    root = root.resolve()
    report = {"status": "fail", "action": action, "project_dir": str(root),
              "checks": [], "errors": [], "warnings": [],
              "next_step": "核对本次用户范围与项目真源"}
    errors, warnings = report["errors"], report["warnings"]

    def run(name, operation):
        try:
            result = operation()
            failures = result.get("errors", [])
            if result.get("status") != "pass" and not failures:
                failures = ["未通过，缺少详细原因"]
            errors.extend(f"{name}：{message}" for message in failures)
            warnings.extend(f"{name}：{message}" for message in result.get("warnings", []))
            report["checks"].append({"name": name, "status": "fail" if failures else "pass"})
        except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{name} 无法完成：{exc}")
            report["checks"].append({"name": name, "status": "fail"})

    try:
        if action not in ACTIONS:
            raise ValueError(f"未知动作：{action}")
        project = load(root / "config/project.json")
        plan_path = root / "planning/visual-plan.json"
        plan = load(plan_path) if plan_path.is_file() else {}
        statuses = project.get("status") or {}
        primary = project.get("primary_timeline", "chatcut")
        report["current"] = {
            "project_id": project.get("project_id"), "primary_timeline": primary,
            "review_mode": project.get("review_mode", "manual"),
            "declared_status": statuses, "planning_scope": project.get("planning_scope"),
            "chatcut": project.get("chatcut"),
            "shot_routes": [{"shot_id": shot.get("id"),
                             "primary_tool": (shot.get("production") or {}).get("primary_tool"),
                             "asset_status": (shot.get("production") or {}).get("asset_status")}
                            for shot in plan.get("shots", [])],
        }
        if primary not in {"chatcut", "hyperframes"}:
            errors.append(f"未知主工程：{primary}")
        if primary == "hyperframes":
            warnings.append("独立 HyperFrames 主工程须有既有用户授权；配置值本身不证明授权")
        # Route checks happen before expensive evidence/media checks.
        if action == "assets":
            shot = next((s for s in plan.get("shots", []) if s.get("id") == shot_id), None)
            if shot is None:
                errors.append("assets 必须指定计划中真实存在的 --shot")
            elif not tool or tool != (shot.get("production") or {}).get("primary_tool"):
                errors.append(f"{shot_id} 实际制作工具与计划不一致；先回写计划并复核受影响批准")
        elif shot_id:
            errors.append("--shot 仅用于 assets；整片动作不能伪装为单镜制作")
        if action in {"assemble", "expand", "candidate"}:
            if tool != primary:
                errors.append(f"本次整片动作必须使用 {primary}；候选/预览沿用相同主工程")
        if action == "assemble" and primary == "chatcut":
            identity = project.get("chatcut") or {}
            if not identity.get("project_id") or not identity.get("timeline_id"):
                errors.append("先按已通过的计划/基线创建或盘点 ChatCut 工程并保存真实 ID")
        if action not in {"status", "delivery-review", "delivery-final"}:
            required = ["plan"] if action == "baseline" else ["plan", "visual_baseline"]
            if action == "expand":
                required.append("sample")
            for stage in required:
                if statuses.get(stage) != "approved":
                    errors.append(f"{stage} 尚未有效批准；沿用已有授权补齐真实审核，不能把自检记成用户确认")
        if errors:
            report["next_step"] = "先修复范围、路由或审核状态；本次动作不能开始"
            return report

        run("状态与审批绑定", lambda: validate_state(root))
        if action == "status":
            if errors:
                report["next_step"] = "先处理状态冲突；读取对应阶段说明，不启动生产"
            elif statuses.get("final") == "approved":
                report["next_step"] = "已有最终批准；核对本次是否为局部修复，不自动重启全片生产"
            elif not plan:
                report["next_step"] = "读取 workflow-planning.md，完成预检与内容编排"
            elif statuses.get("plan") != "approved":
                report["next_step"] = "核对计划与已有用户意见；完成当前版本分镜审阅"
            elif statuses.get("visual_baseline") != "approved":
                report["next_step"] = "读取 workflow-production.md，准备视觉基线候选"
            elif statuses.get("sample") != "approved":
                report["next_step"] = "核对资产与主工程，制作/审阅连续样片；显式完整候选请求见 candidate"
            else:
                report["next_step"] = "读取 workflow-delivery.md，按本次范围选择扩大制作或交付检查"
            warnings.append("status 只核对已声明状态，不授权生产；planning_scope 与聊天中的暂停/范围须人工核对")
        elif not errors:
            if action.startswith("delivery-"):
                run("交付", lambda: validate_delivery(root, ROOT / "references/production-prompts.md",
                    "final" if action == "delivery-final" else "review"))
            else:
                run("当前计划与输入", lambda: check_plan(root))
                run("计划可读视图", lambda: validate_markdown(plan,
                    (root / "planning/visual-plan.md").read_text(encoding="utf-8")))
                stage = "planning" if action == "baseline" else "prepared"
                run("提示词与制作依据", lambda: validate_prompts(root, ROOT / "references/production-prompts.md", stage))
                if action in {"expand", "candidate"}:
                    run("连续样片与参考", lambda: validate_sequence(root, "expand"))
                    if project.get("sequence_review_policy") != "sequence-quality-v1":
                        warnings.append("旧任务未接入连续镜头门；须按 sequence-quality.md 人工复核真实样片，不能宣称本门已验证")
            report["next_step"] = "修复所列失败项后重查" if errors else "完成阶段说明中的实际画面/工具核对后，执行本次已授权动作"
        if action == "candidate":
            warnings.append("candidate 仅适用于用户明确要求完整候选；不会写入或替代样片批准")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        errors.append(f"真源不可检查：{exc}")
    report["status"] = "fail" if errors else "pass"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--action", choices=ACTIONS, default="status")
    parser.add_argument("--tool", help="本次实际调用的制作/组装工具，不是期望工具")
    parser.add_argument("--shot", help="assets 的单镜 ID；批量制作按各镜实际工具分别检查")
    parser.add_argument("--out", type=Path, help="可选派生报告路径，不能覆盖项目真源")
    args = parser.parse_args()
    report = check(args.project_dir, args.action, args.tool, args.shot)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        # Only dedicated derived-report filenames are accepted, even outside root.
        if not args.out.name.startswith("workflow-check-") or args.out.suffix != ".json":
            parser.error("--out 文件名须为 workflow-check-<label>.json，避免覆盖真源")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload)
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
