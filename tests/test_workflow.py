"""Exercise resumed production decisions using isolated file-bound projects.

These tests validate routing and evidence checks, not film quality or whether
an independent agent will follow prose instructions.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_workflow import check, check_plan
from media_evidence import digest
from project_fixtures import bind_preflight
from render_plan_markdown import render


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.shot = {
            "id": "S001", "screen_role": "A", "a_view": "protagonist",
            "start_ms": 0, "end_ms": 1000, "cue_ids": [1], "verbatim_text": "观察陶猫",
            "viewer_takeaway": "观察陶猫的神态", "static_reason": "停留观察",
            "visual_design": {"motion_mode": "single-state", "motion_intent": "停留观察",
                              "final_state": "保持陶猫正面"},
            "changes": [{"at_ms": 0, "event": "展示陶猫"}],
            "narration_beats": [{"at_ms": 0, "cue_ids": [1], "trigger_text": "观察陶猫",
                                 "information_change": "展示主体", "state_after": "保持正面"}],
            "materials": ["测试已有照片"],
            "production": {"primary_tool": "existing-media", "assembly_tool": "chatcut",
                           "fallback_tools": [], "asset_status": "available"},
        }
        self.plan = {"shots": [self.shot]}
        self.project = {
            "project_id": "isolated-workflow-test", "primary_timeline": "chatcut",
            "review_mode": "manual", "a_scene_mode": "full-ai-scene",
            "chatcut": {"project_id": "fixture-project", "timeline_id": "fixture-timeline"},
            "status": {"plan": "approved", "visual_baseline": "pending", "sample": "pending", "final": "pending"},
            "approvals": {}, "sample": {"start_ms": 0, "end_ms": 1000},
            "timeline_policy": {"initial_gap": "show-first-shot", "inter_shot_gap": "hold-previous-shot", "tail_gap": "hold-last-shot"},
        }
        preflight = {"srt": {"cues": [{"id": 1, "start_ms": 0, "end_ms": 1000, "text": "观察陶猫"}]},
                     "audio": {"duration_ms": 1000}}
        bind_preflight(self.root, self.project, preflight)
        self.write("planning/preflight-report.json", preflight)
        self.write("planning/content-analysis.json", {"semantic_segments": [copy.deepcopy(self.shot)]})
        self.save_plan()
        self.write("planning/visual-plan-prompt.json", self.record("visual-plan", ["visual-plan-v1"]))
        record = self.record("S001", ["a-roll-image-v1", "a-roll-action-sequence-v1"])
        record["action_sequence"] = {"mode": "single-state", "static_reason": "停留观察", "beats": [
            {"at_ms": 0, "trigger_text": "观察陶猫", "visual_state": "保持正面", "implementation": "existing-media"}]}
        self.write("prompts/a-scenes/S001.json", record)
        self.approve_plan()

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def save_plan(self):
        self.write("planning/visual-plan.json", self.plan)
        (self.root / "planning/visual-plan.md").write_text(render(self.plan), encoding="utf-8")

    def approve_plan(self):
        self.project["approvals"]["plan"] = {"sha256": digest(self.root / "planning/visual-plan.json"), "review_source": "user"}
        self.write("config/project.json", self.project)

    def approve_legacy_baseline(self):
        # Existing legacy projects retain the documented compatibility path.
        self.write("preview/review.json", {"fixture": "legacy-baseline"})
        self.write("config/visual-style.json", {"candidate_review": {"path": "preview/review.json"}})
        self.project["status"]["visual_baseline"] = "approved"
        self.project["approvals"]["visual_baseline"] = {
            "sha256": digest(self.root / "preview/review.json"), "review_source": "user"}
        self.write("config/project.json", self.project)

    def record(self, subject, ids):
        return {"subject_id": subject, "prompt_ids": ids, "prompt_source": "references/production-prompts.md",
                "prompt_source_sha256": digest(ROOT / "references/production-prompts.md"),
                "inputs": {"fixture": True}, "resolved_prompt": "isolated test prompt", "status": "prepared"}

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_baseline_can_be_checked_before_baseline_approval(self):
        before = self.snapshot()
        result = check(self.root, "baseline")
        self.assertEqual("pass", result["status"], result)
        self.assertEqual(before, self.snapshot())

    def test_resume_does_not_promote_an_existing_mp4_or_static_confirmation(self):
        (self.root / "preview").mkdir()
        (self.root / "preview/old.mp4").write_bytes(b"old file is not approval")
        before = self.snapshot()
        result = check(self.root)
        self.assertEqual("pass", result["status"], result)
        self.assertEqual("pending", result["current"]["declared_status"]["visual_baseline"])
        self.assertIn("视觉基线", result["next_step"])
        blocked = check(self.root, "expand", "chatcut")
        self.assertEqual("fail", blocked["status"])
        self.assertEqual(before, self.snapshot())

    def test_changed_plan_invalidates_old_approval_on_resume(self):
        self.shot["viewer_takeaway"] = "改成观察底座"
        self.save_plan()
        result = check(self.root)
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("SHA-256" in e for e in result["errors"]), result)

    def test_continuous_source_cannot_be_used_in_manual_mode(self):
        self.project["approvals"]["plan"]["review_source"] = "agent-qa-under-user-authorization"
        self.write("config/project.json", self.project)
        self.assertEqual("fail", check(self.root, "baseline")["status"])
        self.project["review_mode"] = "continuous"
        self.write("config/project.json", self.project)
        self.assertEqual("pass", check(self.root, "baseline")["status"])

    def test_changed_audio_blocks_production_even_with_approved_plan(self):
        (self.root / self.project["inputs"]["audio"]).write_bytes(b"changed audio")
        result = check(self.root, "baseline")
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("SHA-256" in e for e in result["errors"]), result)

    def test_stale_markdown_blocks_production(self):
        (self.root / "planning/visual-plan.md").write_text("old page", encoding="utf-8")
        self.assertEqual("fail", check(self.root, "baseline")["status"])

    def test_missing_prompt_instance_blocks_production(self):
        (self.root / "planning/visual-plan-prompt.json").unlink()
        self.assertEqual("fail", check(self.root, "baseline")["status"])

    def test_asset_tool_must_match_the_actual_shot(self):
        self.approve_legacy_baseline()
        self.assertEqual("pass", check(self.root, "assets", "existing-media", "S001")["status"])
        self.assertEqual("fail", check(self.root, "assets", "hyperframes", "S001")["status"])
        self.assertEqual("fail", check(self.root, "assets", "existing-media", "S999")["status"])

    def test_candidate_and_sample_cannot_switch_the_primary_timeline(self):
        self.approve_legacy_baseline()
        for action in ("assemble", "candidate", "expand"):
            with self.subTest(action=action):
                result = check(self.root, action, "hyperframes")
                self.assertEqual("fail", result["status"])
                self.assertTrue(any("整片动作必须使用 chatcut" in e for e in result["errors"]), result)

    def test_single_shot_argument_cannot_disguise_a_full_candidate(self):
        self.approve_legacy_baseline()
        self.assertEqual("fail", check(self.root, "candidate", "chatcut", "S001")["status"])

    def test_assembly_needs_actual_project_identity(self):
        self.approve_legacy_baseline()
        self.assertEqual("pass", check(self.root, "assemble", "chatcut")["status"])
        self.project["chatcut"]["timeline_id"] = None
        self.write("config/project.json", self.project)
        self.assertEqual("fail", check(self.root, "assemble", "chatcut")["status"])

    def test_modern_candidate_needs_continuous_sample_even_if_user_requested_full_length(self):
        self.approve_legacy_baseline()
        self.project["sequence_review_policy"] = "sequence-quality-v1"
        self.plan["sequence_direction"] = {"visual_thread": "观察主体", "continuity": "保持对象",
            "layout_rules": "标签跟随", "motion_language": "必要阅读停留"}
        self.save_plan()
        self.approve_plan()
        result = check(self.root, "candidate", "chatcut")
        self.assertEqual("fail", result["status"])
        self.assertTrue(any("连续样片与参考" in e for e in result["errors"]), result)
        self.assertEqual("pending", self.project["status"]["sample"])

    def test_legacy_candidate_is_explicitly_unverified_and_never_approves_sample(self):
        self.approve_legacy_baseline()
        before = self.snapshot()
        result = check(self.root, "candidate", "chatcut")
        self.assertEqual("pass", result["status"], result)
        self.assertTrue(any("旧任务未接入" in w for w in result["warnings"]), result)
        self.assertEqual(before, self.snapshot())
        self.assertEqual("fail", check(self.root, "expand", "chatcut")["status"])

    def test_missing_real_delivery_cannot_pass_review_or_final(self):
        self.approve_legacy_baseline()
        for action in ("delivery-review", "delivery-final"):
            self.assertEqual("fail", check(self.root, action)["status"])

    def test_bad_json_and_missing_project_fail_without_crashing(self):
        self.assertEqual("fail", check(self.root / "missing")["status"])
        (self.root / "config/project.json").write_text("{", encoding="utf-8")
        self.assertEqual("fail", check(self.root)["status"])

    def test_plan_subprocess_error_is_not_pass(self):
        (self.root / "planning/preflight-report.json").unlink()
        self.assertEqual("fail", check_plan(self.root)["status"])

    def test_cli_report_and_exit_status_do_not_mutate_truth(self):
        before = self.snapshot()
        report_path = self.root / "workflow-check-test.json"
        command = [sys.executable, "-B", "-X", "utf8", str(ROOT / "scripts/check_workflow.py"),
                   "--project-dir", str(self.root), "--action", "candidate", "--tool", "hyperframes",
                   "--out", str(report_path)]
        result = subprocess.run(command, capture_output=True, timeout=30)
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual("fail", json.loads(report_path.read_text(encoding="utf-8"))["status"])
        after = self.snapshot()
        after.pop(report_path.name)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
