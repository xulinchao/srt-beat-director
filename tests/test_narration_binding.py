from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_plan  # noqa: E402


class NarrationBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cues = {
            1: {"id": 1, "start_ms": 100, "end_ms": 1200, "text": "先建立主体"},
            2: {"id": 2, "start_ms": 1400, "end_ms": 2600, "text": "再形成关系"},
        }
        self.shot = {
            "id": "S001",
            "start_ms": 100,
            "end_ms": 2600,
            "cue_ids": [1, 2],
            "narration_beats": [
                {
                    "cue_ids": [1],
                    "at_ms": 100,
                    "trigger_text": "先建立主体",
                    "information_change": "主体出现",
                    "state_after": "主体已建立",
                },
                {
                    "cue_ids": [2],
                    "at_ms": 1400,
                    "trigger_text": "再形成关系",
                    "information_change": "连线出现",
                    "state_after": "关系已建立",
                },
            ],
        }
        self.changes = [
            {"at_ms": 100, "event": "主体出现"},
            {"at_ms": 1400, "event": "连线出现"},
        ]

    def validate(self) -> list[str]:
        errors: list[str] = []
        validate_plan.validate_narration_binding(
            shot=self.shot,
            changes=self.changes,
            cues_by_id=self.cues,
            errors=errors,
        )
        return errors

    def test_matching_changes_and_cues_pass(self) -> None:
        self.assertEqual([], self.validate())

    def test_change_time_must_match_narration_beat(self) -> None:
        self.changes[1]["at_ms"] = 1500
        errors = self.validate()
        self.assertTrue(any("时间不一致" in value for value in errors))

    def test_trigger_text_must_be_original_cue_text(self) -> None:
        self.shot["narration_beats"][1]["trigger_text"] = "自由改写"
        errors = self.validate()
        self.assertTrue(any("与绑定 cue 原文不一致" in value for value in errors))

    def test_trigger_text_accepts_full_cue_concatenation(self) -> None:
        self.shot["narration_beats"] = [
            {
                "cue_ids": [1, 2],
                "at_ms": 100,
                "trigger_text": "先建立主体\n再形成关系",
                "information_change": "主体与关系一次建立",
                "state_after": "关系已建立",
            }
        ]
        self.changes = [{"at_ms": 100, "event": "主体与关系一次建立"}]
        self.assertEqual([], self.validate())

    def test_trigger_text_accepts_single_cue_full_text(self) -> None:
        self.shot["narration_beats"][0]["trigger_text"] = "先建立主体"
        self.assertEqual([], self.validate())

    def test_trigger_text_accepts_contiguous_cue_fragment(self) -> None:
        self.shot["narration_beats"][0]["trigger_text"] = "建立主体"
        self.shot["narration_beats"][1]["trigger_text"] = "形成关系"
        self.assertEqual([], self.validate())

    def test_trigger_text_rejects_non_contiguous_splice(self) -> None:
        self.shot["narration_beats"][0]["trigger_text"] = "先主体"
        errors = self.validate()
        self.assertTrue(any("与绑定 cue 原文不一致" in value for value in errors))

    def test_trigger_text_rejects_unrelated_text(self) -> None:
        self.shot["narration_beats"][0]["trigger_text"] = "完全不同的旁白内容"
        errors = self.validate()
        self.assertTrue(any("与绑定 cue 原文不一致" in value for value in errors))

    def test_trigger_text_rejects_empty_value(self) -> None:
        self.shot["narration_beats"][0]["trigger_text"] = ""
        errors = self.validate()
        self.assertTrue(any("与绑定 cue 原文不一致" in value for value in errors))


if __name__ == "__main__":
    unittest.main()
