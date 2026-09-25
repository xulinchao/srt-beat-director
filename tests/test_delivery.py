from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import subprocess
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_delivery  # noqa: E402
from media_evidence import digest
from scan_video import scan
from sample_dependencies import current_dependencies


class DeliveryClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise unittest.SkipTest("真实媒体回归测试需要 ffmpeg/ffprobe")
        cls.media_temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.media_temp.cleanup)
        cls.media_path = Path(cls.media_temp.name) / "source.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=30:d=2",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(cls.media_path)], check=True, capture_output=True)
        cls.scan_report = scan(cls.media_path)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.temp.name)
        for relative in ("config", "planning", "prompts/a-scenes", "assets/a-scenes", "render", "reports"):
            (self.project_dir / relative).mkdir(parents=True, exist_ok=True)
        self.prompts_path = self.project_dir / "production-prompts.md"
        self.prompts_path.write_text("prompt source\n", encoding="utf-8")
        self.prompt_hash = hashlib.sha256(self.prompts_path.read_bytes()).hexdigest()

        self.final_path = self.project_dir / "render" / "final.mp4"
        shutil.copy2(self.media_path, self.final_path)
        self.final_hash = hashlib.sha256(self.final_path.read_bytes()).hexdigest()
        self.final_artifact = {
            "path": "render/final.mp4",
            "sha256": self.final_hash,
            "bytes": self.final_path.stat().st_size,
            "duration_ms": 2000,
            "timeline_id": "timeline-1",
            "exported_at": "2026-01-01T00:00:00Z",
            "exporter": "chatcut-local-export",
        }
        self.beat = {
            "cue_ids": [1],
            "at_ms": 0,
            "trigger_text": "一句话",
            "information_change": "人物抬头",
            "state_after": "人物已抬头",
        }
        self.shot = {
            "id": "S001",
            "start_ms": 0,
            "end_ms": 2000,
            "screen_role": "A",
            "static_reason": "短镜头只有一个原子动作",
            "narration_beats": [self.beat],
        }
        self.artifact_path = "assets/a-scenes/state.png"
        (self.project_dir / self.artifact_path).write_bytes(b"state")

        project = {
            "schema_version": "0.3",
            "project_id": "fixture",
            "primary_timeline": "chatcut",
            "review_mode": "manual",
            "video": {"fps": 30, "width": 320, "height": 180},
            "inputs": {"srt": "input/source.srt", "audio": "input/narration.mp3"},
            "sample": {"start_ms": 0, "end_ms": 2000},
            "a_scene_mode": "fixed-character-micro-scene",
            "chatcut": {"timeline_id": "timeline-1"},
            "status": {"plan": "approved", "visual_baseline": "approved", "sample": "approved", "final": "rendered-pending-user-review"},
            "approvals": {"final": {"sha256": None, "review_source": None}},
            "final_artifact": self.final_artifact,
        }
        self.write("config/project.json", project)
        self.write("planning/visual-plan.json", {"shots": [self.shot]})
        self.write("planning/preflight-report.json", {"audio": {"duration_ms": 2000}})

        plan_record = self.record("visual-plan", ["visual-plan-v1"], "completed")
        plan_record["artifacts"] = [self.artifact_path]
        self.write("planning/visual-plan-prompt.json", plan_record)
        a_record = self.record(
            "S001",
            ["a-roll-image-v1", "a-roll-view-v1", "a-roll-action-sequence-v1"],
            "completed",
        )
        a_record["artifacts"] = [self.artifact_path]
        a_record["action_sequence"] = {
            "mode": "single-state",
            "static_reason": "短镜头只有一个原子动作",
            "beats": [
                {
                    "beat_id": "A01",
                    "at_ms": 0,
                    "trigger_text": "一句话",
                    "visual_state": "人物抬头",
                    "implementation": "generated-state-frame",
                    "evidence": {"artifact": self.artifact_path, "artifact_time_ms": None},
                }
            ],
        }
        self.write("prompts/a-scenes/S001.json", a_record)

        audit = {
            "schema_version": "0.3",
            "status": "pass",
            "timeline": {"id": "timeline-1", "fps": 30},
            "shots": [
                {
                    "id": "S001",
                    "screen_role": "A",
                    "plan_range_ms": [0, 2000],
                    "timeline_range_frames": [0, 60],
                    "status": "pass",
                    "beats": [
                        {
                            "at_ms": 0,
                            "trigger_text": "一句话",
                            "timeline_at_ms": 0,
                            "status": "covered",
                            "evidence": {
                                "artifact": self.artifact_path,
                                "artifact_time_ms": None,
                                "timeline_items": [{"item_id": "item-1", "asset_id": "asset-1", "range_frames": [0, 60]}],
                            },
                        }
                    ],
                }
            ],
        }
        self.write("reports/timeline-audit.json", audit)
        self.write("reports/qa-report.json", {"status": "pass", "final_artifact": self.final_artifact})
        self.write(
            "reports/manifest.json",
            {
                "status": "rendered-pending-user-review",
                "chatcut": {"timeline_id": "timeline-1"},
                "final_artifact": self.final_artifact,
            },
        )
        self.write("config/visual-style.json", {"candidate_review": {"path": "preview/baseline.json"}})
        self.write("preview/baseline.json", {"status": "pass"})
        (self.project_dir / "input").mkdir()
        (self.project_dir / "input/source.srt").write_text("source", encoding="utf-8")
        (self.project_dir / "input/narration.mp3").write_bytes(b"dependency fixture")
        shutil.copy2(self.final_path, self.project_dir / "preview/sample.mp4")
        self.write("reports/frame-scan.json", self.scan_report)
        self.write("reports/qa-report.json", {"status": "pass", "final_artifact": self.final_artifact,
                   "frame_scan": {"path": "reports/frame-scan.json", "sha256": digest(self.project_dir / "reports/frame-scan.json")}})
        project["approvals"].update({
            "plan": {"sha256": digest(self.project_dir / "planning/visual-plan.json"), "review_source": "user"},
            "visual_baseline": {"sha256": digest(self.project_dir / "preview/baseline.json"), "review_source": "user"},
            "sample": {"artifact": "preview/sample.mp4", "sha256": digest(self.project_dir / "preview/sample.mp4"), "review_source": "user"},
        })
        self.write("config/project.json", project)
        self.write("preview/sample-dependencies.json", {"schema_version": "1.0", "sample_artifact": "preview/sample.mp4",
                   "sample_sha256": project["approvals"]["sample"]["sha256"], "dependencies": current_dependencies(self.project_dir)})
        project["approvals"]["sample"]["dependencies"] = {"path": "preview/sample-dependencies.json", "sha256": digest(self.project_dir / "preview/sample-dependencies.json")}
        self.write("config/project.json", project)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, relative: str, value: dict) -> None:
        path = self.project_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def record(self, subject: str, prompt_ids: list[str], status: str) -> dict:
        return {
            "subject_id": subject,
            "prompt_ids": prompt_ids,
            "prompt_source": "references/production-prompts.md",
            "prompt_source_sha256": self.prompt_hash,
            "inputs": {"subject": subject},
            "resolved_prompt": "resolved",
            "status": status,
            "artifacts": [],
        }

    def test_review_delivery_passes_when_all_truths_match(self) -> None:
        report = validate_delivery.validate(self.project_dir, self.prompts_path, "review")
        self.assertEqual("pass", report["status"], report["errors"])

    def test_missing_chatcut_asset_id_breaks_closure(self) -> None:
        audit_path = self.project_dir / "reports" / "timeline-audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        del audit["shots"][0]["beats"][0]["evidence"]["timeline_items"][0]["asset_id"]
        self.write("reports/timeline-audit.json", audit)

        report = validate_delivery.validate(self.project_dir, self.prompts_path, "review")

        self.assertEqual("fail", report["status"])
        self.assertTrue(any("缺少 asset_id" in value for value in report["errors"]))

    def test_final_mode_requires_matching_approval_hash(self) -> None:
        report = validate_delivery.validate(self.project_dir, self.prompts_path, "final")
        self.assertEqual("fail", report["status"])
        self.assertTrue(any("status.final=approved" in value for value in report["errors"]))

    def mutate(self, relative, change):
        value = json.loads((self.project_dir / relative).read_text(encoding="utf-8"))
        change(value)
        self.write(relative, value)

    def assert_rejected(self, message):
        report = validate_delivery.validate(self.project_dir, self.prompts_path, "review")
        self.assertEqual("fail", report["status"], report)
        self.assertTrue(any(message in e for e in report["errors"]), report["errors"])

    def test_40ms_is_more_than_one_frame_at_30fps(self):
        self.mutate("reports/timeline-audit.json", lambda d: d["shots"][0]["beats"][0].update(timeline_at_ms=40))
        self.assert_rejected("一个时间线帧")

    def test_invalid_shot_frame_range(self):
        self.mutate("reports/timeline-audit.json", lambda d: d["shots"][0].update(timeline_range_frames=[9000, 9001]))
        self.assert_rejected("timeline_range_frames")

    def test_item_must_cover_beat(self):
        self.mutate("reports/timeline-audit.json", lambda d: d["shots"][0]["beats"][0]["evidence"]["timeline_items"][0].update(range_frames=[20, 60]))
        self.assert_rejected("未覆盖实际节拍")

    def test_non_video_with_consistent_metadata_rejected(self):
        self.final_path.write_bytes(b"this is not an mp4")
        for relative in ("config/project.json", "reports/manifest.json", "reports/qa-report.json"):
            self.mutate(relative, lambda d: d["final_artifact"].update(sha256=digest(self.final_path), bytes=self.final_path.stat().st_size))
        self.assert_rejected("实际媒体验证失败")

    def test_scan_must_match_current_file(self):
        self.mutate("reports/frame-scan.json", lambda d: d.update(artifact_sha256="0" * 64))
        self.mutate("reports/qa-report.json", lambda d: d["frame_scan"].update(sha256=digest(self.project_dir / "reports/frame-scan.json")))
        self.assert_rejected("不是当前成片")

    def test_unreviewed_candidate_rejected(self):
        self.mutate("reports/frame-scan.json", lambda d: d.update(candidates=[{"frame": 3, "review": None}]))
        self.mutate("reports/qa-report.json", lambda d: d["frame_scan"].update(sha256=digest(self.project_dir / "reports/frame-scan.json")))
        self.assert_rejected("尚未解释")

    def test_reapproved_plan_does_not_reapprove_old_sample(self):
        self.mutate("planning/visual-plan.json", lambda d: d.update(note="new plan"))
        self.mutate("config/project.json", lambda d: d["approvals"]["plan"].update(sha256=digest(self.project_dir / "planning/visual-plan.json")))
        self.assert_rejected("样片上游")

    def test_input_change_invalidates_sample(self):
        (self.project_dir / "input/narration.mp3").write_bytes(b"changed")
        self.assert_rejected("样片上游")

    def test_asset_change_invalidates_sample(self):
        (self.project_dir / self.artifact_path).write_bytes(b"changed")
        self.assert_rejected("样片上游")

    def test_missing_snapshot_cannot_claim_approved(self):
        self.mutate("config/project.json", lambda d: d["approvals"]["sample"].pop("dependencies"))
        self.assert_rejected("缺少 dependencies")


if __name__ == "__main__":
    unittest.main()
