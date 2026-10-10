from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from media_evidence import digest
from sample_dependencies import current_dependencies, validate_snapshot


class ScopedSampleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = {"inputs": {"srt": "input/source.srt", "audio": "input/audio.mp3"},
                        "sample": {"start_ms": 0, "end_ms": 2000}, "video": {"fps": 30}}
        self.plan = {"schema_version": "0.3", "shots": [
            {"id": "S001", "start_ms": 100, "end_ms": 1500, "screen_role": "A"},
            {"id": "S002", "start_ms": 3000, "end_ms": 4000, "screen_role": "B"}]}
        self.write("config/project.json", self.project)
        self.write("planning/visual-plan.json", self.plan)
        self.write("config/visual-style.json", {"candidate_review": {"path": "preview/baseline.json"}})
        self.write("preview/baseline.json", {})
        for value in ("input/source.srt", "input/audio.mp3", "assets/state.png", "preview/sample.mp4", "source/index.html"):
            path = self.root / value
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"unit fixture, not production media")
        self.record = {"artifacts": ["assets/state.png"], "action_sequence": {"beats": []}}
        self.write("prompts/a-scenes/S001.json", self.record)

    def write(self, value, data):
        path = self.root / value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_later_shot_edit_does_not_invalidate_v2(self):
        before = current_dependencies(self.root, "2.0")
        self.plan["shots"][1]["visual_design"] = {"subject": "changed later"}
        self.write("planning/visual-plan.json", self.plan)
        self.assertEqual(before, current_dependencies(self.root, "2.0"))

    def test_legacy_still_binds_complete_plan(self):
        before = current_dependencies(self.root)
        self.plan["shots"][1]["visual_design"] = {"subject": "changed later"}
        self.write("planning/visual-plan.json", self.plan)
        self.assertNotEqual(before, current_dependencies(self.root))

    def test_common_policy_and_selected_shot_invalidate(self):
        before = current_dependencies(self.root, "2.0")
        for edit in (lambda: self.plan.update(broll_layout_policy="motion-first-v1"),
                     lambda: self.plan["shots"][0].update(transition={"to_next": "fade"})):
            edit()
            self.write("planning/visual-plan.json", self.plan)
            self.assertNotEqual(before, current_dependencies(self.root, "2.0"))

    def test_gap_hold_boundary_enters_sample(self):
        before = current_dependencies(self.root, "2.0")
        self.plan["shots"][1]["start_ms"] = 1900
        self.write("planning/visual-plan.json", self.plan)
        self.write("prompts/b-scenes/S002.json", {"artifacts": ["assets/state.png"]})
        after = current_dependencies(self.root, "2.0")
        self.assertEqual(after["shot_ids"], ["S001", "S002"])
        self.assertNotEqual(before, after)

    def test_visual_lead_enters_sample_without_changing_semantic_start(self):
        self.plan["shots"][1]["start_ms"] = 2200
        self.write("planning/visual-plan.json", self.plan)
        before = current_dependencies(self.root, "2.0")
        self.plan["shots"][1]["transition"] = {"visual_cut": {
            "offset_ms": -400, "reason": "预备观察", "bridge": "先见对象"}}
        self.write("planning/visual-plan.json", self.plan)
        self.write("prompts/b-scenes/S002.json", {"artifacts": ["assets/state.png"]})
        after = current_dependencies(self.root, "2.0")
        self.assertEqual(["S001", "S002"], after["shot_ids"])
        self.assertEqual([1800, 2000], after["plan_scope"]["shots"][1]["display_range_ms"])
        self.assertNotEqual(before, after)

    def test_visual_tail_keeps_previous_shot_inside_sample(self):
        self.project["sample"] = {"start_ms": 3100, "end_ms": 4000}
        self.plan["shots"][1]["transition"] = {"visual_cut": {
            "offset_ms": 250, "reason": "读完结果", "bridge": "引导语期间保持结果"}}
        self.write("config/project.json", self.project)
        self.write("planning/visual-plan.json", self.plan)
        self.write("prompts/b-scenes/S002.json", {"artifacts": ["assets/state.png"]})
        after = current_dependencies(self.root, "2.0")
        self.assertEqual(["S001", "S002"], after["shot_ids"])
        self.assertEqual([3100, 3250], after["plan_scope"]["shots"][0]["display_range_ms"])

    def test_dict_artifact_and_source_are_bound(self):
        self.record["artifacts"] = [{"path": "assets/state.png"}]
        self.plan["shots"][0]["production"] = {"source_files": ["source/index.html"]}
        self.write("planning/visual-plan.json", self.plan)
        self.write("prompts/a-scenes/S001.json", self.record)
        before = current_dependencies(self.root, "2.0")
        (self.root / "source/index.html").write_text("updated")
        self.assertNotEqual(before, current_dependencies(self.root, "2.0"))

    def test_changed_shared_audio_invalidates(self):
        before = current_dependencies(self.root, "2.0")
        (self.root / "input/audio.mp3").write_bytes(b"changed")
        self.assertNotEqual(before, current_dependencies(self.root, "2.0"))

    def test_semantic_json_format_does_not_invalidate(self):
        before = current_dependencies(self.root, "2.0")
        (self.root / "planning/visual-plan.json").write_text(json.dumps(self.plan, indent=4))
        self.assertEqual(before, current_dependencies(self.root, "2.0"))

    def test_cli_creates_v2_and_never_overwrites(self):
        command = [sys.executable, "-B", str(ROOT / "scripts/sample_dependencies.py"),
                   "--project-dir", str(self.root), "--sample", "preview/sample.mp4",
                   "--out", str(self.root / "preview/dependencies.json")]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.root / "preview/dependencies.json"
        snapshot = json.loads(path.read_text())
        self.assertEqual(snapshot["schema_version"], "2.0")
        approval = {"artifact": "preview/sample.mp4", "sha256": digest(self.root / "preview/sample.mp4"),
                    "dependencies": {"path": "preview/dependencies.json", "sha256": digest(path)}}
        self.assertEqual(validate_snapshot(self.root, approval), [])
        original = path.read_bytes()
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
