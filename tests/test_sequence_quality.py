"""Evidence and routing regressions; synthetic fixtures do not judge visual taste."""
from __future__ import annotations

import copy
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from media_evidence import digest
from sequence_quality import POLICY, scope_hash, validate, validate_plan
from sample_dependencies import current_dependencies


def direction():
    return {"visual_thread": "整件、结构、用途", "continuity": "前镜结果成为后镜观察依据",
            "layout_rules": "主体与标签分区，出处和字幕各有位置", "motion_language": "操作后停留可见结果"}


class SequencePlanTests(unittest.TestCase):
    def setUp(self):
        self.project = {"sequence_review_policy": POLICY, "primary_timeline": "chatcut"}
        self.shot = {"id": "S001", "material_type": "verified-media", "presentation_type": "verified-media",
                     "visual_design": {"motion_mode": "verified-media-sequence"},
                     "production": {"primary_tool": "hyperframes", "assembly_tool": "chatcut"}}
        self.plan = {"sequence_direction": direction(), "shots": [self.shot]}

    def test_existing_photo_does_not_exempt_custom_animation(self):
        self.assertTrue(any("motion_reference_review" in e for e in validate_plan(self.plan, self.project)["errors"]))

    def test_scene_and_a_roll_have_the_same_reference_requirement(self):
        self.shot.update(screen_role="A", presentation_type="scene", material_type="no-material")
        self.assertTrue(any("motion_reference_review" in e for e in validate_plan(self.plan, self.project)["errors"]))

    def test_existing_media_with_new_custom_motion_requires_reference(self):
        self.shot["production"].update(primary_tool="existing-media", custom_motion=True)
        self.assertTrue(any("motion_reference_review" in e for e in validate_plan(self.plan, self.project)["errors"]))

    def test_static_reading_and_unmodified_media_are_allowed(self):
        self.shot["visual_design"]["motion_mode"] = "single-state"
        self.assertFalse(validate_plan(self.plan, self.project)["errors"])
        self.shot["visual_design"]["motion_mode"] = "continuous-motion"
        self.shot["production"]["primary_tool"] = "existing-media"
        self.assertFalse(validate_plan(self.plan, self.project)["errors"])

    def test_direction_and_assembly_mismatch_are_rejected(self):
        self.plan["sequence_direction"]["continuity"] = ""
        self.shot["production"]["assembly_tool"] = "hyperframes"
        errors = validate_plan(self.plan, self.project)["errors"]
        self.assertTrue(any("continuity" in e for e in errors))
        self.assertTrue(any("assembly_tool" in e for e in errors))

    def test_legacy_is_unchanged_and_unknown_policy_is_rejected(self):
        before = copy.deepcopy(self.plan)
        report = validate_plan(self.plan, {})
        self.assertFalse(report["errors"])
        self.assertTrue(report["warnings"])
        self.assertEqual(before, self.plan)
        self.project["sequence_review_policy"] = "typo"
        self.assertTrue(validate_plan(self.plan, self.project)["errors"])


    def test_initializer_enables_gate_and_keeps_review_paths_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n例句\n", encoding="utf-8")
            (root / "source.mp3").write_bytes(b"input path fixture")
            command = [sys.executable, "-B", str(ROOT / "scripts/init_project.py"), "--project-dir", str(root / "task"),
                       "--srt", str(root / "source.srt"), "--audio", str(root / "source.mp3"), "--aspect-ratio", "16:9",
                       "--width", "1920", "--height", "1080", "--a-scene-mode", "full-ai-scene"]
            result = subprocess.run(command, capture_output=True, timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)
            project = json.loads((root / "task/config/project.json").read_text(encoding="utf-8"))
            self.assertEqual(POLICY, project["sequence_review_policy"])
            self.assertEqual({"sample": None, "full": None}, project["sequence_review"])
            self.assertEqual("chatcut", project["primary_timeline"])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "需要ffmpeg/ffprobe验证实际媒体")
class SequenceEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.media_temp.cleanup)
        cls.media = Path(cls.media_temp.name) / "fixture.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=30:d=2",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(cls.media)], check=True, capture_output=True)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in ("config", "planning", "preview", "input", "reports", "assets"):
            (self.root / name).mkdir()
        shutil.copy2(self.media, self.root / "preview/sample.mp4")
        (self.root / "input/narration.mp3").write_bytes(b"input identity fixture")
        (self.root / "input/source.srt").write_text("original subtitle identity fixture", encoding="utf-8")
        (self.root / "config/DESIGN.md").write_text("design identity fixture", encoding="utf-8")
        self.png("preview/state.png")
        self.project = {"sequence_review_policy": POLICY, "sequence_review": {"sample": "preview/sequence.json", "full": "preview/sequence-full.json"},
                        "primary_timeline": "chatcut", "chatcut": {"project_id": "project-1", "timeline_id": "timeline-1"},
                        "review_mode": "manual", "video": {"width": 320, "height": 180, "fps": 30},
                        "inputs": {"audio": "input/narration.mp3", "srt": "input/source.srt"},
                        "sample": {"start_ms": 0, "end_ms": 2000}, "status": {"sample": "pending"}}
        self.plan = {"sequence_direction": direction(), "design_ref": {"path": "config/DESIGN.md", "version": "fixture", "sha256": digest(self.root / "config/DESIGN.md")},
                     "shots": [{"id": f"S{i+1:03}", "start_ms": i*1000, "end_ms": (i+1)*1000,
                                "screen_role": "B", "visual_design": {"motion_mode": "continuous-motion" if i == 0 else "single-state"},
                                "production": {"primary_tool": "existing-media", "assembly_tool": "chatcut"}} for i in range(2)]}
        self.write("config/project.json", self.project)
        self.write("planning/visual-plan.json", self.plan)
        self.write("planning/captured-plan.json", self.plan)
        self.items = [{"item_id": f"item-{i+1}", "asset_id": f"asset-{i+1}", "artifact": "preview/sample.mp4",
                       "range_frames": [i*30, (i+1)*30], "source_start_ms": i*1000, "playback_rate": 1} for i in range(2)]
        self.snapshot = {"schema_version": "1.0", "captured_at": "2026-01-01T00:00:00Z", "project_id": "project-1",
                         "timeline_id": "timeline-1", "fps": 30, "final_sha256": digest(self.root / "preview/sample.mp4"),
                         "plan_sha256": digest(self.root / "planning/captured-plan.json")}
        self.refresh_snapshot()
        self.review = {"policy": POLICY, "scope": "sample", "range_ms": [0, 2000], "plan_snapshot": self.ref("planning/captured-plan.json"),
                       "plan_scope_sha256": scope_hash(self.plan, ["S001", "S002"]), "design_ref": self.plan["design_ref"],
                       "narration_sha256": digest(self.root / "input/narration.mp3"), "srt_sha256": digest(self.root / "input/source.srt"),
                       "artifact": self.ref("preview/sample.mp4"), "timeline": {"runtime": "chatcut", "project_id": "project-1", "timeline_id": "timeline-1",
                       "exporter": "chatcut-local-export", "source_snapshot": self.ref("reports/snapshot.json")},
                       "review_source": "agent-self-check", "normal_speed_viewed": True,
                       "sequence_checks": {k: self.passed() for k in ("visual_continuity", "ppt_feel", "reading_rhythm")},
                       "shots": [{"shot_id": "S001", "actual_tool": "existing-media", "item_ids": ["item-1"],
                                  "explanation_review": self.passed(), "layout_review": self.passed(),
                                  "state_evidence": [self.state(p, at) for p, at in (("start", 0), ("change", 400), ("result", 900))]},
                                 {"shot_id": "S002", "actual_tool": "existing-media", "item_ids": ["item-2"],
                                  "explanation_review": self.passed(), "layout_review": self.passed(), "state_evidence": [self.state("hold", 1000)]}],
                       "transitions": [{"from": "S001", "to": "S002", "artifact_time_ms": 1000, "evidence": self.ref("preview/state.png"), **self.passed()}]}
        self.save_review()

    def png(self, name):
        def chunk(kind, data):
            return struct.pack(">I", len(data))+kind+data+struct.pack(">I", zlib.crc32(kind+data))
        data = b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 24, 8, 2, 0, 0, 0))
        pixels = b"".join(b"\0" + bytes([70, 80, 90])*32 for _ in range(24))
        (self.root / name).write_bytes(data+chunk(b"IDAT", zlib.compress(pixels))+chunk(b"IEND", b""))

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def ref(self, name):
        return {"path": name, "sha256": digest(self.root / name)}

    def passed(self):
        return {"status": "pass", "notes": "synthetic evidence/routing fixture; no visual-quality claim"}

    def state(self, phase, at):
        return {"phase": phase, "artifact_time_ms": at, **self.ref("preview/state.png")}

    def refresh_snapshot(self):
        self.write("reports/raw.json", {"items": self.items})
        self.snapshot["sources"] = [self.ref("reports/raw.json")]
        self.snapshot["items"] = [{**item, "sha256": digest(self.root / item["artifact"]),
            "origin": {"path": "reports/raw.json", "fields": {key: f"/items/{i}/{key}" for key in
                       ("item_id", "asset_id", "artifact", "range_frames", "source_start_ms", "playback_rate")}}} for i, item in enumerate(self.items)]
        self.write("reports/snapshot.json", self.snapshot)

    def save_review(self):
        self.write("preview/sequence.json", self.review)

    def errors(self, stage="sample"):
        self.save_review()
        return validate(self.root, stage)["errors"]

    def test_real_media_and_independent_clip_evidence_pass_without_writing_approval(self):
        self.assertEqual([], self.errors())
        self.assertEqual("pending", json.loads((self.root / "config/project.json").read_text(encoding="utf-8"))["status"]["sample"])

    def test_ppt_failure_blocks_expansion_even_with_valid_media(self):
        self.review["sequence_checks"]["ppt_feel"] = {"status": "fail", "notes": "逐页换图，动作没有解释收益"}
        self.assertTrue(any("ppt_feel" in e for e in self.errors("expand")))

    def test_missing_motion_middle_and_unviewed_playback_are_rejected(self):
        self.review["shots"][0]["state_evidence"].pop(1)
        self.review["normal_speed_viewed"] = False
        errors = self.errors()
        self.assertTrue(any("中间变化" in e for e in errors))
        self.assertTrue(any("正常速度" in e for e in errors))

    def test_missing_adjacent_transition_is_rejected(self):
        self.review["transitions"] = []
        self.assertTrue(any("衔接审阅" in e for e in self.errors()))

    def test_undeclared_actual_tool_and_wrong_main_timeline_are_rejected(self):
        self.review["shots"][0]["actual_tool"] = "hyperframes"
        self.review["timeline"].update(runtime="hyperframes", exporter="hyperframes-render")
        errors = self.errors()
        self.assertTrue(any("实际制作工具" in e for e in errors))
        self.assertTrue(any("实际主时间线" in e for e in errors))
        self.assertTrue(any("由ChatCut导出" in e for e in errors))

    def test_one_merged_item_cannot_stand_in_for_all_shots(self):
        self.items = [dict(self.items[0], range_frames=[0, 60])]
        self.refresh_snapshot()
        self.review["timeline"]["source_snapshot"] = self.ref("reports/snapshot.json")
        self.review["shots"][1]["item_ids"] = ["item-1"]
        self.assertTrue(any("独立镜头实例" in e for e in self.errors()))

    def test_raw_engine_data_cannot_be_replaced_by_a_plan_copy(self):
        self.write("reports/raw.json", {"shots": self.plan["shots"]})
        self.snapshot["sources"] = [self.ref("reports/raw.json")]
        self.write("reports/snapshot.json", self.snapshot)
        self.review["timeline"]["source_snapshot"] = self.ref("reports/snapshot.json")
        self.assertTrue(any("时间线快照不可验证" in e for e in self.errors()))

    def test_changed_input_and_current_design_are_rejected(self):
        (self.root / "input/source.srt").write_text("changed", encoding="utf-8")
        (self.root / "config/DESIGN.md").write_text("changed", encoding="utf-8")
        errors = self.errors()
        self.assertTrue(any("当前 srt" in e for e in errors))
        self.assertTrue(any("当前DESIGN" in e for e in errors))

    def test_out_of_range_frame_and_renamed_text_image_are_rejected(self):
        self.review["shots"][0]["state_evidence"][1]["artifact_time_ms"] = 1500
        self.assertTrue(any("镜头范围" in e for e in self.errors()))
        (self.root / "preview/state.png").write_bytes(b"not an image")
        for row in self.review["shots"]:
            for state in row["state_evidence"]:
                state.update(self.ref("preview/state.png"))
        self.assertTrue(any("静帧证据" in e for e in self.errors()))

    def test_approved_sample_must_match_review_artifact(self):
        self.project.update(status={"sample": "approved"}, approvals={"sample": {"artifact": "preview/other.mp4", "sha256": "other"}})
        self.write("config/project.json", self.project)
        self.assertTrue(any("已批准的实际样片" in e for e in self.errors()))

    def test_future_shot_change_keeps_unaffected_sample_valid_but_shared_direction_does_not(self):
        self.plan["shots"].append({"id": "S003", "start_ms": 2000, "end_ms": 3000,
            "visual_design": {"motion_mode": "single-state"}, "production": {"primary_tool": "existing-media", "assembly_tool": "chatcut"}})
        self.write("planning/visual-plan.json", self.plan)
        self.write("planning/captured-plan.json", self.plan)
        self.snapshot["plan_sha256"] = digest(self.root / "planning/captured-plan.json")
        self.refresh_snapshot()
        self.review["plan_snapshot"] = self.ref("planning/captured-plan.json")
        self.review["timeline"]["source_snapshot"] = self.ref("reports/snapshot.json")
        self.plan["shots"][2]["visual_design"]["subject"] = "outside sample changed"
        self.write("planning/visual-plan.json", self.plan)
        self.assertEqual([], self.errors())
        self.plan["sequence_direction"]["continuity"] = "changed shared direction"
        self.write("planning/visual-plan.json", self.plan)
        self.assertTrue(any("过期" in e for e in self.errors()))

    def test_full_review_binds_actual_final_file_and_all_shots(self):
        self.review["scope"] = "full"
        self.project["final_artifact"] = self.ref("preview/sample.mp4")
        self.write("config/project.json", self.project)
        self.write("preview/sequence-full.json", self.review)
        self.assertFalse(validate(self.root, "delivery")["errors"])
        self.project["final_artifact"]["sha256"] = "changed final"
        self.write("config/project.json", self.project)
        self.assertTrue(any("final_artifact" in e for e in validate(self.root, "delivery")["errors"]))

    def test_motion_reference_requires_real_preview_and_real_native_source(self):
        self.plan["shots"][0]["production"].update(primary_tool="hyperframes", motion_reference_review="planning/reference.json")
        self.write("planning/visual-plan.json", self.plan)
        record = {"decision": "reuse-native-source", "selected_candidate": "ref-1", "inspected_candidates": [
            {"id": "ref-1", "source_locator": "specific-source.js", "assessment": "适配定位动作",
             "preview_evidence": {"status": "inspected", **self.ref("preview/state.png")},
             "license": "MIT", "license_evidence": self.ref("input/source.srt"), "implementation_files": ["missing-source.js"]}]}
        self.write("planning/reference.json", record)
        self.assertTrue(any("具体实现文件不可读取" in e for e in validate(self.root, "prepared")["errors"]))
        (self.root / "specific-source.js").write_text("// inspected source fixture", encoding="utf-8")
        record["inspected_candidates"][0]["implementation_files"] = ["specific-source.js"]
        self.write("planning/reference.json", record)
        self.assertFalse(validate(self.root, "prepared")["errors"])
        record["inspected_candidates"][0]["preview_evidence"]["sha256"] = "made-up"
        self.write("planning/reference.json", record)
        self.assertTrue(any("候选预览" in e for e in validate(self.root, "prepared")["errors"]))

    def test_quality_cli_reports_failure_without_media_production(self):
        self.review["sequence_checks"]["ppt_feel"]["status"] = "pending"
        self.save_review()
        command = [sys.executable, "-B", str(ROOT / "scripts/validate_sequence_quality.py"), "--project-dir", str(self.root),
                   "--stage", "expand", "--out", str(self.root / "reports/result.json")]
        result = subprocess.run(command, capture_output=True, timeout=30)
        self.assertEqual(2, result.returncode)
        self.assertEqual("fail", json.loads((self.root / "reports/result.json").read_text(encoding="utf-8"))["status"])

    def test_v2_dependency_snapshot_binds_sequence_review_evidence(self):
        self.write("config/visual-style.json", {"candidate_review": {"path": "preview/baseline.json"}})
        self.write("preview/baseline.json", {})
        (self.root / "prompts/b-scenes").mkdir(parents=True)
        for sid in ("S001", "S002"):
            self.write(f"prompts/b-scenes/{sid}.json", {"artifacts": ["preview/sample.mp4"]})
        before = current_dependencies(self.root, "2.0")
        paths = {entry["path"] for entry in before["files"]}
        self.assertIn("preview/sequence.json", paths)
        self.assertIn("reports/raw.json", paths)
        self.assertIn("planning/captured-plan.json", paths)
        self.review["sequence_checks"]["reading_rhythm"]["notes"] = "changed actual viewing observation"
        self.save_review()
        self.assertNotEqual(before, current_dependencies(self.root, "2.0"))

    def test_new_policy_cannot_downgrade_to_unbound_v1_snapshot(self):
        with self.assertRaisesRegex(ValueError, "2.0"):
            current_dependencies(self.root, "1.0")


if __name__ == "__main__":
    unittest.main()
