from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_prompt_usage  # noqa: E402


class PromptUsageActionSequenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.temp_dir.name)
        (self.project_dir / "config").mkdir()
        (self.project_dir / "planning").mkdir()
        (self.project_dir / "prompts" / "a-scenes").mkdir(parents=True)
        (self.project_dir / "assets" / "a-scenes").mkdir(parents=True)
        self.prompts_path = self.project_dir / "production-prompts.md"
        self.prompts_path.write_text("prompt source\n", encoding="utf-8")
        self.prompt_hash = hashlib.sha256(self.prompts_path.read_bytes()).hexdigest()
        self.shot = {
            "id": "S001",
            "start_ms": 0,
            "end_ms": 6500,
            "screen_role": "A",
            "narration_beats": [
                {"at_ms": 0, "trigger_text": "短语 1"},
                {"at_ms": 2000, "trigger_text": "短语 2"},
                {"at_ms": 4000, "trigger_text": "短语 3"},
            ],
        }
        self.write_json(
            "config/project.json",
            {"a_scene_mode": "fixed-character-micro-scene"},
        )
        self.write_json("planning/visual-plan.json", {"shots": [self.shot]})

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_json(self, relative_path: str, value: dict) -> None:
        path = self.project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def create_artifact(self, name: str) -> str:
        relative_path = f"assets/a-scenes/{name}"
        (self.project_dir / relative_path).write_bytes(b"asset")
        return relative_path

    def base_record(self, subject_id: str, prompt_ids: list[str], status: str) -> dict:
        return {
            "schema_version": "0.1",
            "subject_id": subject_id,
            "prompt_ids": prompt_ids,
            "prompt_source": "references/production-prompts.md",
            "prompt_source_sha256": self.prompt_hash,
            "inputs": {"shot_id": subject_id},
            "resolved_prompt": "resolved",
            "artifacts": [],
            "status": status,
        }

    def write_plan_prompt(self, status: str) -> None:
        record = self.base_record("visual-plan", ["visual-plan-v1"], status)
        if status == "completed":
            record["artifacts"] = [self.create_artifact("visual-plan.txt")]
        self.write_json("planning/visual-plan-prompt.json", record)

    def action_beat(self, index: int, artifact: str | None = None) -> dict:
        beat = {
            "beat_id": f"A{index:02d}",
            "at_ms": (index - 1) * 2000,
            "trigger_text": f"短语 {index}",
            "visual_state": f"状态 {index}",
            "implementation": "generated-state-frame",
        }
        if artifact is not None:
            beat["evidence"] = {"artifact": artifact, "artifact_time_ms": None}
        return beat

    def write_a_record(self, beats: list[dict], status: str) -> None:
        record = self.base_record(
            "S001",
            ["a-roll-image-v1", "a-roll-view-v1", "a-roll-action-sequence-v1"],
            status,
        )
        record["action_sequence"] = {
            "mode": "state-sequence",
            "static_reason": None,
            "beats": beats,
        }
        if status == "completed":
            record["artifacts"] = [beat["evidence"]["artifact"] for beat in beats]
        self.write_json("prompts/a-scenes/S001.json", record)

    def test_prepared_a_roll_requires_all_planned_beats(self) -> None:
        self.write_plan_prompt("prepared")
        self.write_a_record([self.action_beat(1), self.action_beat(2)], "prepared")

        report = validate_prompt_usage.validate(self.project_dir, self.prompts_path, "prepared")

        self.assertEqual("fail", report["status"])
        self.assertTrue(any("必须落实全部计划节拍" in value for value in report["errors"]))

    def test_long_single_state_passes_with_inherited_reason(self) -> None:
        self.shot["narration_beats"] = self.shot["narration_beats"][:1]
        self.shot["static_reason"] = "保持犹豫姿态，让观众听完同一处境的描述"
        self.write_json("planning/visual-plan.json", {"shots": [self.shot]})
        self.write_plan_prompt("prepared")
        self.write_a_record([self.action_beat(1)], "prepared")
        path = self.project_dir / "prompts/a-scenes/S001.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["action_sequence"].update(mode="single-state", static_reason=self.shot["static_reason"])
        self.write_json("prompts/a-scenes/S001.json", record)
        report = validate_prompt_usage.validate(self.project_dir, self.prompts_path, "prepared")
        self.assertEqual("pass", report["status"], report["errors"])

    def test_single_state_without_plan_reason_fails(self) -> None:
        self.shot["narration_beats"] = self.shot["narration_beats"][:1]
        self.write_json("planning/visual-plan.json", {"shots": [self.shot]})
        self.write_plan_prompt("prepared")
        self.write_a_record([self.action_beat(1)], "prepared")
        report = validate_prompt_usage.validate(self.project_dir, self.prompts_path, "prepared")
        self.assertEqual("fail", report["status"])
        self.assertTrue(any("static_reason" in value for value in report["errors"]))

    def test_produced_state_sequence_requires_distinct_evidence_assets(self) -> None:
        self.write_plan_prompt("completed")
        shared = self.create_artifact("shared.png")
        self.write_a_record(
            [self.action_beat(1, shared), self.action_beat(2, shared), self.action_beat(3, shared)],
            "completed",
        )

        report = validate_prompt_usage.validate(self.project_dir, self.prompts_path, "produced")

        self.assertEqual("fail", report["status"])
        self.assertTrue(any("不同的证据资产" in value for value in report["errors"]))

    def test_produced_state_sequence_passes_with_three_assets(self) -> None:
        self.write_plan_prompt("completed")
        artifacts = [self.create_artifact(f"state-{index}.png") for index in range(1, 4)]
        self.write_a_record(
            [self.action_beat(index, artifact) for index, artifact in enumerate(artifacts, start=1)],
            "completed",
        )

        report = validate_prompt_usage.validate(self.project_dir, self.prompts_path, "produced")

        self.assertEqual("pass", report["status"], report["errors"])

    def test_produced_sequence_must_match_planned_phrase_and_time(self) -> None:
        self.write_plan_prompt("completed")
        artifacts = [self.create_artifact(f"state-{index}.png") for index in range(1, 4)]
        beats = [self.action_beat(index, artifact) for index, artifact in enumerate(artifacts, start=1)]
        beats[1]["trigger_text"] = "另一句话"
        self.write_a_record(beats, "completed")

        report = validate_prompt_usage.validate(self.project_dir, self.prompts_path, "produced")

        self.assertEqual("fail", report["status"])
        self.assertTrue(any("与视觉计划旁白短语不一致" in value for value in report["errors"]))


class PromptUsageBrollMotionSequenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.temp_dir.name)
        for relative in (
            "config",
            "planning/template-selection",
            "prompts/b-scenes",
            "assets/b-scenes",
        ):
            (self.project_dir / relative).mkdir(parents=True, exist_ok=True)
        self.prompts_path = self.project_dir / "production-prompts.md"
        self.prompts_path.write_text("prompt source\n", encoding="utf-8")
        self.prompt_hash = hashlib.sha256(self.prompts_path.read_bytes()).hexdigest()
        self.shot = {
            "id": "S001",
            "start_ms": 1000,
            "end_ms": 7000,
            "screen_role": "B",
            "narration_beats": [
                {"at_ms": 1000, "trigger_text": "建立主体"},
                {"at_ms": 3000, "trigger_text": "关系改变"},
                {"at_ms": 5000, "trigger_text": "结论落定"},
            ],
        }
        self.write_json("config/project.json", {"a_scene_mode": "full-ai-scene"})
        self.write_json("planning/visual-plan.json", {"shots": [self.shot]})
        self.write_json("planning/template-selection/S001.json", {"status": "selected"})

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_json(self, relative_path: str, value: dict) -> None:
        path = self.project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def create_artifact(self, name: str) -> str:
        relative_path = f"assets/b-scenes/{name}"
        (self.project_dir / relative_path).write_bytes(b"asset")
        return relative_path

    def base_record(self, subject_id: str, prompt_ids: list[str], status: str) -> dict:
        return {
            "schema_version": "0.2",
            "subject_id": subject_id,
            "prompt_ids": prompt_ids,
            "prompt_source": "references/production-prompts.md",
            "prompt_source_sha256": self.prompt_hash,
            "inputs": {"shot_id": subject_id},
            "resolved_prompt": "resolved",
            "artifacts": [],
            "status": status,
        }

    def write_plan_prompt(self) -> None:
        record = self.base_record("visual-plan", ["visual-plan-v1"], "completed")
        artifact = self.create_artifact("visual-plan.txt")
        record["artifacts"] = [artifact]
        self.write_json("planning/visual-plan-prompt.json", record)

    def write_b_record(self, include_motion: bool = True) -> None:
        record = self.base_record("S001", ["b-roll-motion-selection-v1"], "completed")
        artifact = self.create_artifact("motion.mp4")
        record["artifacts"] = [artifact]
        record["selection_report"] = "planning/template-selection/S001.json"
        if include_motion:
            record["motion_sequence"] = {
                "mode": "continuous-motion",
                "static_reason": None,
                "beats": [
                    {
                        "beat_id": f"B{index:02d}",
                        "at_ms": planned["at_ms"],
                        "trigger_text": planned["trigger_text"],
                        "visual_state": f"状态 {index}",
                        "implementation": "rendered-motion",
                        "evidence": {"artifact": artifact, "artifact_time_ms": (index - 1) * 2000},
                    }
                    for index, planned in enumerate(self.shot["narration_beats"], start=1)
                ],
            }
        self.write_json("prompts/b-scenes/S001.json", record)

    def test_produced_broll_requires_motion_sequence(self) -> None:
        self.write_plan_prompt()
        self.write_b_record(include_motion=False)

        report = validate_prompt_usage.validate(self.project_dir, self.prompts_path, "produced")

        self.assertEqual("fail", report["status"])
        self.assertTrue(any("缺少 motion_sequence" in value for value in report["errors"]))

    def test_produced_broll_passes_with_timed_motion_evidence(self) -> None:
        self.write_plan_prompt()
        self.write_b_record(include_motion=True)

        report = validate_prompt_usage.validate(self.project_dir, self.prompts_path, "produced")

        self.assertEqual("pass", report["status"], report["errors"])


if __name__ == "__main__":
    unittest.main()
