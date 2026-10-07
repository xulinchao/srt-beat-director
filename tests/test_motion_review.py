"""Regression cases for single-cue action, incomplete stills and false motion approval."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from media_evidence import digest
from motion_review import POLICY, validate_motion_plan, validate_visual_review
import validate_state
import validate_prompt_usage
from project_fixtures import bind_preflight


def moving_shot():
    return {"id": "S001", "narration_beats": [{"at_ms": 0, "trigger_text": "头和身子是两个陶罐拼成的"}],
            "visual_design": {"motion_mode": "continuous-motion", "motion_check": {
                "action": "头罐上移，身罐留在原处", "visible_result": "相对罐口与间距清楚",
                "required_states": [{"id": "whole", "beat_index": 0, "description": "完整头身"},
                                    {"id": "split", "beat_index": 0, "description": "两罐口显露"}]}}}


class MotionPlanTests(unittest.TestCase):
    def setUp(self):
        self.project = {"motion_review_policy": POLICY}
        self.plan = {"motion_review_policy": POLICY, "baseline_shot_ids": ["S001"], "shots": [moving_shot()]}

    def test_one_cue_can_contain_multiple_action_states(self):
        self.assertEqual([], validate_motion_plan(self.plan, self.project)["errors"])
        self.assertNotIn("static_reason", self.plan["shots"][0])

    def test_plan_cli_does_not_require_static_reason_for_one_cue_motion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "planning").mkdir()
            shot = self.plan["shots"][0]
            text = shot["narration_beats"][0]["trigger_text"]
            cue = {"id": 1, "start_ms": 0, "end_ms": 2000, "text": text}
            preflight = {"srt": {"cues": [cue]}, "audio": {"duration_ms": 2000}}
            bind_preflight(root, self.project, preflight)
            self.project["timeline_policy"] = {"initial_gap": "show-first-shot", "inter_shot_gap": "hold-previous-shot", "tail_gap": "hold-last-shot"}
            shot.update(screen_role="A", a_view="first-person", start_ms=0, end_ms=2000, cue_ids=[1], verbatim_text=text,
                        viewer_takeaway="识别两个陶罐的连接", changes=[{"at_ms": 0, "event": "拆开头身"}],
                        materials=[{"path": "input/reference.png"}],
                        production={"primary_tool": "existing-media", "fallback_tools": [], "asset_status": "to-generate"})
            shot["visual_design"]["final_state"] = "两罐口可辨"
            shot["narration_beats"][0].update(cue_ids=[1], information_change="拆开头身", state_after="两罐口可辨")
            documents = {"config/project.json": self.project, "planning/preflight.json": preflight,
                         "planning/content.json": {"semantic_segments": [{"id": "C001", "cue_ids": [1], "start_ms": 0, "end_ms": 2000, "verbatim_text": text}]},
                         "planning/visual-plan.json": self.plan}
            for name, value in documents.items():
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/validate_plan.py"),
                                     "--project", str(root / "config/project.json"), "--preflight", str(root / "planning/preflight.json"),
                                     "--content-analysis", str(root / "planning/content.json"), "--visual-plan", str(root / "planning/visual-plan.json"),
                                     "--out-dir", str(root / "out")], capture_output=True, timeout=20)
            report = json.loads((root / "out/plan-validation-report.json").read_text(encoding="utf-8"))
            self.assertEqual(0, result.returncode, report["errors"])
            self.assertNotIn("static_reason", shot)

    def test_new_task_cannot_omit_policy(self):
        del self.plan["motion_review_policy"]
        self.assertTrue(validate_motion_plan(self.plan, self.project)["errors"])

    def test_legacy_plan_is_not_migrated_or_claimed_verified(self):
        before = copy.deepcopy(self.plan)
        del self.plan["motion_review_policy"]
        report = validate_motion_plan(self.plan, {})
        self.assertFalse(report["errors"])
        self.assertTrue(report["warnings"])
        self.assertEqual(before["shots"], self.plan["shots"])

    def test_missing_visible_action_and_result_is_rejected(self):
        self.plan["shots"][0]["visual_design"]["motion_check"].update(action="", visible_result="")
        errors = validate_motion_plan(self.plan, self.project)["errors"]
        self.assertTrue(any("action" in e for e in errors))
        self.assertTrue(any("visible_result" in e for e in errors))

    def test_single_state_reading_is_valid_without_forcing_animation(self):
        self.plan["shots"][0] = {"id": "S001", "narration_beats": [{"at_ms": 0}],
                                "static_reason": "保留原件让观众读完引文", "visual_design": {"motion_mode": "single-state"}}
        self.assertEqual([], validate_motion_plan(self.plan, self.project)["errors"])
        del self.plan["shots"][0]["static_reason"]
        self.assertTrue(any("static_reason" in e for e in validate_motion_plan(self.plan, self.project)["errors"]))

    def test_unknown_beat_and_repeated_state_are_rejected(self):
        states = self.plan["shots"][0]["visual_design"]["motion_check"]["required_states"]
        states[1].update(id="whole", beat_index=1)
        self.assertTrue(any("重复" in e for e in validate_motion_plan(self.plan, self.project)["errors"]))
        self.assertTrue(any("beat_index" in e for e in validate_motion_plan(self.plan, self.project)["errors"]))


@unittest.skipUnless(shutil.which("ffprobe"), "需要ffprobe核验实际媒体")
class MotionReviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in ("planning", "config", "preview", "input"):
            (self.root / name).mkdir()
        self.project = {"motion_review_policy": POLICY, "review_mode": "manual", "inputs": {"audio": "input/narration.mp3"}}
        (self.root / "input/narration.mp3").write_bytes(b"original input hash fixture, not an audio decoding test")
        self.plan = {"motion_review_policy": POLICY, "baseline_shot_ids": ["S001"], "shots": [moving_shot()],
                     "design_ref": {"path": "config/DESIGN.md", "version": "test", "sha256": "design"}}
        self.write("planning/visual-plan.json", self.plan)
        self.png("preview/before.png", 30)
        self.png("preview/after.png", 200)
        self.entry = {"shot_id": "S001", "state_evidence": [self.state("whole", "preview/before.png"),
                                                              self.state("split", "preview/after.png")],
                      "technical_review": {"status": "pass", "notes": "Actual image/video decoding and hashes tested"},
                      "expression_review": {"status": "pass", "review_source": "user", "observed_action": "头罐上移",
                                            "observed_result": "两罐口可辨", "action_matches": True,
                                            "result_matches": True, "narration_matches": True},
                      "narration_sha256": digest(self.root / "input/narration.mp3")}
        self.review = {"policy": POLICY, "scope": "state-preview", "plan_sha256": digest(self.root / "planning/visual-plan.json"),
                       "design_ref": self.plan["design_ref"], "shots": [self.entry]}

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def png(self, name, gray):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        pixels = b"".join(b"\0" + bytes([gray, gray, gray]) * 32 for _ in range(24))
        data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 24, 8, 2, 0, 0, 0))
        (self.root / name).write_bytes(data + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))

    def state(self, sid, path, at=None):
        return {"state_id": sid, "artifact": path, "sha256": digest(self.root / path), "artifact_time_ms": at}

    def check(self, approve=False):
        return validate_visual_review(self.root, self.plan, self.project, self.review, approve=approve)

    def make_video(self, audio=True):
        if not shutil.which("ffmpeg"):
            self.skipTest("需要ffmpeg生成可探测视频")
        args = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=32x24:r=10:d=2"]
        if audio:
            args += ["-f", "lavfi", "-i", "sine=frequency=220:duration=2"]
        args += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if audio:
            args += ["-c:a", "aac", "-shortest"]
        subprocess.run(args + [str(self.root / "preview/clip.mp4")], check=True, capture_output=True, timeout=20)
        self.entry["dynamic_preview"] = {"artifact": "preview/clip.mp4", "sha256": digest(self.root / "preview/clip.mp4")}

    def test_partial_style_preview_is_allowed_but_cannot_be_approved(self):
        self.review["scope"] = "style-preview"
        self.entry["state_evidence"] = self.entry["state_evidence"][:1]
        self.assertEqual("pass", self.check()["status"])
        self.assertTrue(any("不能批准" in e for e in self.check(approve=True)["errors"]))

    def test_one_still_cannot_verify_two_required_states(self):
        self.entry["state_evidence"] = self.entry["state_evidence"][:1]
        self.assertTrue(any("必要状态未覆盖" in e for e in self.check()["errors"]))

    def test_same_image_under_different_names_is_not_two_states(self):
        shutil.copy2(self.root / "preview/before.png", self.root / "preview/after.png")
        self.entry["state_evidence"][1] = self.state("split", "preview/after.png")
        self.assertTrue(any("冒充不同状态" in e for e in self.check()["errors"]))

    def test_invalid_image_is_rejected_even_with_matching_hash(self):
        (self.root / "preview/after.png").write_bytes(b"not an image")
        self.entry["state_evidence"][1] = self.state("split", "preview/after.png")
        self.assertTrue(any("解码" in e for e in self.check()["errors"]))

    def test_image_cannot_be_video_time_evidence(self):
        self.entry["state_evidence"][1]["artifact_time_ms"] = 1000
        self.assertTrue(any("无法验证" in e for e in self.check()["errors"]))

    def test_plan_hash_and_artifact_hash_must_match(self):
        self.review["plan_sha256"] = "stale"
        self.entry["state_evidence"][0]["sha256"] = "wrong"
        errors = self.check()["errors"]
        self.assertTrue(any("计划哈希过期" in e for e in errors))
        self.assertTrue(any("证据哈希不一致" in e for e in errors))

    def test_path_escape_is_rejected(self):
        self.entry["state_evidence"][0]["artifact"] = "../outside.png"
        self.assertTrue(any("越界" in e for e in self.check()["errors"]))

    def test_stills_cannot_replace_motion_baseline(self):
        self.review["scope"] = "motion-baseline"
        self.assertTrue(any("dynamic_preview" in e for e in self.check()["errors"]))

    def test_static_source_reading_needs_no_video(self):
        self.plan["shots"][0] = {"id": "S001", "narration_beats": [{"at_ms": 0}],
                                "static_reason": "静止阅读原件", "visual_design": {"motion_mode": "single-state"}}
        self.write("planning/visual-plan.json", self.plan)
        self.review.update(scope="motion-baseline", plan_sha256=digest(self.root / "planning/visual-plan.json"))
        self.entry["state_evidence"] = [self.state("hold", "preview/before.png")]
        self.assertEqual("pass", self.check(approve=True)["status"])

    def test_decodable_motion_can_show_multiple_states_inside_one_cue(self):
        self.make_video()
        self.entry["state_evidence"] = [self.state("whole", "preview/clip.mp4", 0), self.state("split", "preview/clip.mp4", 1000)]
        self.review["scope"] = "motion-baseline"
        self.assertEqual("pass", self.check()["status"], self.check()["errors"])
        self.entry["state_evidence"][1]["artifact_time_ms"] = 0
        self.assertTrue(any("冒充不同状态" in e for e in self.check()["errors"]))
        self.entry["state_evidence"][1]["artifact_time_ms"] = 2000
        self.assertTrue(any("超出素材时长" in e for e in self.check()["errors"]))

    def test_technical_pass_cannot_cover_push_only_or_missing_action(self):
        self.make_video()
        self.review["scope"] = "motion-baseline"
        self.entry["expression_review"].update(status="fail", observed_action="只有整图推镜，没有头罐拆分", action_matches=False)
        errors = self.check()["errors"]
        self.assertTrue(any("表达检查未通过" in e for e in errors))
        self.assertTrue(any("action_matches 未通过" in e for e in errors))

    def test_motion_review_requires_narration_audio_and_current_input_binding(self):
        self.make_video(audio=False)
        self.review["scope"] = "motion-baseline"
        self.entry["narration_sha256"] = "old"
        errors = self.check()["errors"]
        self.assertTrue(any("缺少音轨" in e for e in errors))
        self.assertTrue(any("未绑定当前原旁白" in e for e in errors))

    def test_state_approval_rechecks_scope_instead_of_only_hash(self):
        self.review["scope"] = "style-preview"
        self.write("preview/review.json", self.review)
        self.project.update(status={"visual_baseline": "approved"}, approvals={"visual_baseline": {
            "sha256": digest(self.root / "preview/review.json"), "review_source": "user"}})
        self.write("config/project.json", self.project)
        self.write("config/visual-style.json", {"candidate_review": {"path": "preview/review.json"}})
        with patch.object(validate_state, "validate_design", return_value={"errors": [], "warnings": []}):
            errors = validate_state.validate(self.root)["errors"]
        self.assertTrue(any("不能批准" in e for e in errors))

    def test_baseline_cannot_omit_selected_representative(self):
        self.plan["shots"].append({**moving_shot(), "id": "S002"})
        self.plan["baseline_shot_ids"].append("S002")
        self.write("planning/visual-plan.json", self.plan)
        self.review.update(scope="motion-baseline", plan_sha256=digest(self.root / "planning/visual-plan.json"))
        self.assertTrue(any("缺少代表镜头" in e for e in self.check()["errors"]))

    def test_produced_prompt_checks_internal_states_not_just_one_cue_anchor(self):
        self.make_video()
        shot = self.plan["shots"][0]
        shot.update(screen_role="A", start_ms=0, end_ms=2000)
        shot["visual_design"].update(function="解释", relation="头身组成", carrier="陶罐拆分", character_role="展示")
        self.project.update(design_contract_version="1.0", video={"width": 32, "height": 24, "fps": 10, "aspect_ratio": "4:3"},
                            subtitle_safe_area={"bottom_fraction": 0.22})
        (self.root / "config/font.ttf").write_bytes(b"font path fixture")
        (self.root / "review.md").write_text("offline design approval fixture", encoding="utf-8")
        rules = {"video": self.project["video"], "fonts": [{"family": "Test", "path": "font.ttf"}], "font_sizes": {"body": 12},
                 "max_chars_per_line": 16, "max_lines": 4, "margin_fraction": 0.08, "subtitle_bottom_fraction": 0.22,
                 "colors": {"text": "#111111"}, "graphic_language": "thin arrows", "character_direction": "reference",
                 "scene_density": "minimal", "motion": "split head and body"}
        spec = {"schema_version": "1.0", "scope": "film", "version": "test", "account": None, "rules": rules,
                "samples": [{"path": "../preview/before.png", "sha256": digest(self.root / "preview/before.png")}]}
        design = self.root / "config/DESIGN.md"
        design.write_text("```design-spec\n" + json.dumps(spec) + "\n```\n", encoding="utf-8")
        self.plan["design_ref"] = {"path": "config/DESIGN.md", "version": "test", "sha256": digest(design)}
        self.write("config/visual-style.json", {"design_ref": self.plan["design_ref"], "resolved_design": rules,
                   "design_review": {"status": "approved", "sha256": digest(design), "review_source": "user", "evidence": "review.md"}})
        self.write("planning/visual-plan.json", self.plan)
        self.write("config/project.json", self.project)
        source = self.root / "source.md"
        source.write_text("offline test prompt", encoding="utf-8")
        def record(sid, ids):
            return {"subject_id": sid, "prompt_ids": ids, "prompt_source": "references/production-prompts.md",
                    "prompt_source_sha256": digest(source), "inputs": {"fixture": "one-cue-motion"},
                    "resolved_prompt": "offline regression record", "status": "completed",
                    "artifacts": ["preview/clip.mp4"], "design_ref": self.plan["design_ref"]}
        self.write("planning/visual-plan-prompt.json", record("visual-plan", ["visual-plan-v1"]))
        action = record("S001", ["a-roll-image-v1", "a-roll-action-sequence-v1"])
        action["action_sequence"] = {"mode": "continuous-motion", "beats": [{
            "at_ms": 0, "trigger_text": shot["narration_beats"][0]["trigger_text"],
            "visual_state": "头罐拆分", "implementation": "rendered-motion",
            "evidence": {"artifact": "preview/clip.mp4", "artifact_time_ms": 0}}]}
        self.entry["plan_sha256"] = digest(self.root / "planning/visual-plan.json")
        self.entry["state_evidence"] = [self.state("whole", "preview/clip.mp4", 0), self.state("split", "preview/clip.mp4", 1000)]
        action["motion_review"] = copy.deepcopy(self.entry)
        (self.root / "prompts/a-scenes").mkdir(parents=True)
        self.write("prompts/a-scenes/S001.json", action)
        report = validate_prompt_usage.validate(self.root, source, "produced")
        self.assertEqual("pass", report["status"], report["errors"])
        action["motion_review"]["state_evidence"] = action["motion_review"]["state_evidence"][:1]
        self.write("prompts/a-scenes/S001.json", action)
        errors = validate_prompt_usage.validate(self.root, source, "produced")["errors"]
        self.assertTrue(any("必要状态未覆盖" in e for e in errors))

    def test_candidate_cli_never_writes_approval(self):
        self.review["scope"] = "style-preview"
        self.write("config/project.json", self.project)
        self.write("preview/review.json", self.review)
        before = digest(self.root / "config/project.json")
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/validate_visual_review.py"),
                                 "--project-dir", str(self.root), "--review", str(self.root / "preview/review.json"),
                                 "--approve-baseline", "--out", str(self.root / "planning/check.json")],
                                capture_output=True, timeout=20)
        self.assertEqual(2, result.returncode)
        self.assertEqual(before, digest(self.root / "config/project.json"))
        self.assertTrue(any("不能批准" in e for e in json.loads((self.root / "planning/check.json").read_text(encoding="utf-8"))["errors"]))


if __name__ == "__main__":
    unittest.main()
