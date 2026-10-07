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
from prompt_bindings import capture


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
            "cue_ids": [1],
            "verbatim_text": "一句话",
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
            "chatcut": {"project_id": "chatcut-fixture", "timeline_id": "timeline-1"},
            "status": {"plan": "approved", "visual_baseline": "approved", "sample": "approved", "final": "rendered-pending-user-review"},
            "approvals": {"final": {"sha256": None, "review_source": None}},
            "final_artifact": self.final_artifact,
        }
        self.write("config/project.json", project)
        self.write("planning/visual-plan.json", {"shots": [self.shot]})
        self.write("planning/content-analysis.json", {"semantic_segments": [self.shot]})
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
        (self.project_dir / "input/source.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\n一句话\n", encoding="utf-8")
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
        self.write("planning/preflight-report.json", {
            "status": "pass", "errors": [],
            "inputs": {f"{key}_sha256": digest(self.project_dir / value) for key, value in project["inputs"].items()},
            "srt": {"cues": [{"id": 1, "start_ms": 0, "end_ms": 2000, "text": "一句话"}]},
            "audio": {"duration_ms": 2000},
        })
        self.write("reports/raw-timeline.json", {"fixture": "synthetic inspector result", "items": [
            {"id": "item-1", "asset": "asset-1", "artifact": self.artifact_path,
             "range_frames": [0, 60], "source_start_ms": 0, "playback_rate": 1}]})
        self.write("reports/timeline-source.json", {
            "schema_version": "1.0", "captured_at": "2026-01-01T00:00:00Z",
            "project_id": "chatcut-fixture", "timeline_id": "timeline-1", "fps": 30,
            "final_sha256": self.final_hash, "plan_sha256": digest(self.project_dir / "planning/visual-plan.json"),
            "sources": [{"path": "reports/raw-timeline.json", "sha256": digest(self.project_dir / "reports/raw-timeline.json")}],
            "items": [{"item_id": "item-1", "asset_id": "asset-1", "range_frames": [0, 60],
                       "artifact": self.artifact_path, "sha256": digest(self.project_dir / self.artifact_path),
                       "source_start_ms": 0, "playback_rate": 1,
                       "origin": {"path": "reports/raw-timeline.json", "fields": {
                           "item_id": "/items/0/id", "asset_id": "/items/0/asset",
                           "artifact": "/items/0/artifact",
                           "range_frames": "/items/0/range_frames", "source_start_ms": "/items/0/source_start_ms",
                           "playback_rate": "/items/0/playback_rate"}}}],
        })
        self.mutate("reports/timeline-audit.json", lambda d: d.update(source_snapshot={
            "path": "reports/timeline-source.json", "sha256": digest(self.project_dir / "reports/timeline-source.json")}))
        self.write("preview/sample-dependencies.json", {"schema_version": "1.0", "sample_artifact": "preview/sample.mp4",
                   "sample_sha256": project["approvals"]["sample"]["sha256"], "dependencies": current_dependencies(self.project_dir)})
        project["approvals"]["sample"]["dependencies"] = {"path": "preview/sample-dependencies.json", "sha256": digest(self.project_dir / "preview/sample-dependencies.json")}
        self.write("config/project.json", project)
        self.refresh_manifest()

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

    def refresh_manifest(self):
        entries = [{"path": path.relative_to(self.project_dir).as_posix(), "sha256": digest(path),
                    "source": "test fixture", "version": "1", "status": "current"}
                   for path in sorted(self.project_dir.rglob("*")) if path.is_file()
                   and path != self.project_dir / "reports/manifest.json"]
        self.mutate("reports/manifest.json", lambda d: d.update(files=entries))

    def refresh_timeline_reference(self):
        self.mutate("reports/timeline-audit.json", lambda d: d["source_snapshot"].update(
            sha256=digest(self.project_dir / "reports/timeline-source.json")))

    def test_review_delivery_passes_when_all_truths_match(self) -> None:
        report = validate_delivery.validate(self.project_dir, self.prompts_path, "review")
        self.assertEqual("pass", report["status"], report["errors"])

    def test_review_candidate_cannot_bypass_enabled_sequence_quality_gate(self) -> None:
        self.mutate("config/project.json", lambda d: d.update(
            sequence_review_policy="sequence-quality-v1", sequence_review={"sample": None, "full": None}))
        self.mutate("planning/visual-plan.json", lambda d: d.update(sequence_direction={
            "visual_thread": "观察对象变化", "continuity": "单镜过程", "layout_rules": "主体与字幕分区", "motion_language": "变化后停留"}))
        self.mutate("planning/visual-plan.json", lambda d: d["shots"][0].update(
            production={"primary_tool": "existing-media", "assembly_tool": "chatcut"}))
        self.refresh_manifest()
        report = validate_delivery.validate(self.project_dir, self.prompts_path, "review")
        self.assertEqual("fail", report["status"])
        self.assertTrue(any("连续镜头质量证据不可验证" in value for value in report["errors"]))

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

    def test_failed_preflight_blocks_delivery(self):
        self.mutate("planning/preflight-report.json", lambda d: d.update(status="fail", errors=["invalid input"]))
        self.assert_rejected("预检未通过")

    def test_stale_preflight_hash_blocks_delivery(self):
        self.mutate("planning/preflight-report.json", lambda d: d["inputs"].update(audio_sha256="0" * 64))
        self.assert_rejected("预检 audio")

    def test_missing_manifest_inventory_is_rejected(self):
        self.mutate("reports/manifest.json", lambda d: d.pop("files"))
        self.assert_rejected("files 交付清单")

    def test_manifest_missing_required_file_is_rejected(self):
        self.mutate("reports/manifest.json", lambda d: d.update(files=[v for v in d["files"] if v["path"] != "input/source.srt"]))
        self.assert_rejected("未登记必要文件：input/source.srt")

    def test_manifest_changed_file_hash_is_rejected(self):
        self.mutate("reports/manifest.json", lambda d: d["files"][0].update(sha256="0" * 64))
        self.assert_rejected("manifest 文件 SHA-256 不一致")

    def test_invented_item_id_is_rejected(self):
        self.mutate("reports/timeline-audit.json", lambda d: d["shots"][0]["beats"][0]["evidence"]["timeline_items"][0].update(item_id="invented"))
        self.assert_rejected("item_id 不在工程快照")

    def test_wrong_asset_id_is_rejected(self):
        self.mutate("reports/timeline-audit.json", lambda d: d["shots"][0]["beats"][0]["evidence"]["timeline_items"][0].update(asset_id="invented"))
        self.assert_rejected("asset_id 与工程快照不一致")

    def test_missing_timeline_snapshot_is_rejected(self):
        self.mutate("reports/timeline-audit.json", lambda d: d.pop("source_snapshot"))
        self.assert_rejected("缺少 source_snapshot")

    def test_stale_timeline_snapshot_is_rejected(self):
        self.mutate("reports/timeline-source.json", lambda d: d.update(final_sha256="0" * 64))
        self.refresh_timeline_reference()
        self.assert_rejected("时间线快照未绑定当前成片")

    def test_invented_id_in_both_audit_and_snapshot_is_rejected(self):
        self.mutate("reports/timeline-source.json", lambda d: d["items"][0].update(item_id="invented"))
        self.mutate("reports/timeline-audit.json", lambda d: d["shots"][0]["beats"][0]["evidence"]["timeline_items"][0].update(item_id="invented"))
        self.refresh_timeline_reference()
        self.assert_rejected("item_id 与原始工程读取结果不一致")

    def test_wrong_registered_file_is_rejected(self):
        self.mutate("reports/raw-timeline.json", lambda d: d["items"][0].update(artifact="wrong.png"))
        self.mutate("reports/timeline-source.json", lambda d: d["sources"][0].update(
            sha256=digest(self.project_dir / "reports/raw-timeline.json")))
        self.refresh_timeline_reference()
        self.assert_rejected("源文件路径与原始工程读取结果不一致")

    def test_registered_asset_path_can_come_from_separate_inspection(self):
        self.write("reports/raw-asset.json", {"localPath": str(self.project_dir / self.artifact_path)})
        self.mutate("reports/timeline-source.json", lambda d: d["sources"].append({
            "path": "reports/raw-asset.json", "sha256": digest(self.project_dir / "reports/raw-asset.json")}))
        self.mutate("reports/timeline-source.json", lambda d: d["items"][0]["origin"]["fields"].update(
            artifact={"path": "reports/raw-asset.json", "pointer": "/localPath"}))
        self.refresh_timeline_reference()
        self.refresh_manifest()
        report = validate_delivery.validate(self.project_dir, self.prompts_path, "review")
        self.assertEqual("pass", report["status"], report["errors"])

    def test_final_approval_with_current_inventory_passes(self):
        self.mutate("config/project.json", lambda d: d["status"].update(final="approved"))
        self.mutate("config/project.json", lambda d: d["approvals"]["final"].update(sha256=self.final_hash, review_source="user"))
        self.mutate("reports/manifest.json", lambda d: d.update(status="approved"))
        self.refresh_manifest()
        report = validate_delivery.validate(self.project_dir, self.prompts_path, "final")
        self.assertEqual("pass", report["status"], report["errors"])

    def test_review_cli_writes_passing_report(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/validate_delivery.py"),
                                 "--project-dir", str(self.project_dir), "--production-prompts", str(self.prompts_path),
                                 "--mode", "review", "--out-dir", str(self.project_dir / "reports")], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads((self.project_dir / "reports/delivery-validation-report.json").read_text(encoding="utf-8"))
        self.assertEqual("pass", report["status"])

    def scoped_fixture(self):
        self.prompts_path.write_bytes((ROOT / "references/production-prompts.md").read_bytes())
        for position, relative in enumerate(("planning/visual-plan-prompt.json", "prompts/a-scenes/S001.json")):
            record = json.loads((self.project_dir / relative).read_text(encoding="utf-8"))
            binding = capture(self.project_dir, self.prompts_path, record["prompt_ids"],
                              f"prompts/sources/source-{position}.md", f"prompts/sources/binding-{position}.json")
            self.mutate(relative, lambda d: d.update(binding))
        self.mutate("preview/sample-dependencies.json", lambda d: d.update(
            schema_version="2.0", dependencies=current_dependencies(self.project_dir, "2.0")))
        self.mutate("config/project.json", lambda d: d["approvals"]["sample"]["dependencies"].update(
            sha256=digest(self.project_dir / "preview/sample-dependencies.json")))
        self.refresh_manifest()

    def test_scoped_protocol_delivery_passes(self):
        self.scoped_fixture()
        report = validate_delivery.validate(self.project_dir, self.prompts_path, "review")
        self.assertEqual(report["status"], "pass", report["errors"])

    def test_prompt_source_archive_must_be_in_manifest(self):
        self.scoped_fixture()
        self.mutate("reports/manifest.json", lambda d: d.update(files=[
            entry for entry in d["files"] if entry["path"] != "prompts/sources/source-0.md"]))
        self.assert_rejected("prompts/sources/source-0.md")

    def test_v2_plan_format_change_preserves_sample_not_full_plan_hash(self):
        self.scoped_fixture()
        path = self.project_dir / "planning/visual-plan.json"
        path.write_text(json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=4), encoding="utf-8")
        self.assert_rejected("视觉计划批准 SHA-256")
        self.mutate("config/project.json", lambda d: d["approvals"]["plan"].update(sha256=digest(path)))
        self.mutate("reports/timeline-source.json", lambda d: d.update(plan_sha256=digest(path)))
        self.refresh_timeline_reference()
        self.refresh_manifest()
        report = validate_delivery.validate(self.project_dir, self.prompts_path, "review")
        self.assertEqual(report["status"], "pass", report["errors"])


if __name__ == "__main__":
    unittest.main()
