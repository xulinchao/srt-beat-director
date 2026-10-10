"""Cut timing changes display coverage, never the original narration clock."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from visual_timing import display_ranges, validate_visual_cuts
from sequence_quality import scope_hash, validate_plan
from render_plan_markdown import render
from validate_plan_markdown import validate as validate_markdown


class VisualTimingTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"shots": [
            {"id": "S001", "start_ms": 100, "end_ms": 900,
             "narration_beats": [{"at_ms": 100}, {"at_ms": 600}]},
            {"id": "S002", "start_ms": 1000, "end_ms": 1900,
             "narration_beats": [{"at_ms": 1300}]}]}

    def cut(self, offset):
        self.plan["shots"][1]["transition"] = {"visual_cut": {
            "offset_ms": offset, "reason": "先认出对象再解释", "bridge": "只有桥体，结构标记随原旁白出现"}}

    def test_legacy_gap_and_tail_holds_are_unchanged(self):
        self.assertEqual([[0, 1000], [1000, 2100]], display_ranges(self.plan["shots"], 2100))
        self.assertEqual([], validate_visual_cuts(self.plan, 30, 2100))

    def test_early_late_and_explicit_sync_keep_semantics_and_beats(self):
        for offset in (-250, 250, 0):
            with self.subTest(offset=offset):
                self.cut(offset)
                before = copy.deepcopy(self.plan)
                self.assertEqual([], validate_visual_cuts(self.plan, 30, 2100))
                self.assertEqual([[0, 1000+offset], [1000+offset, 2100]], display_ranges(self.plan["shots"], 2100))
                self.assertEqual(before, self.plan)

    def test_late_cut_cannot_hide_opening_beat(self):
        self.cut(250)
        self.plan["shots"][1]["narration_beats"][0]["at_ms"] = 1000
        self.assertTrue(any("遮掉旁白节拍" in e for e in validate_visual_cuts(self.plan, 30, 2100)))

    def test_early_cut_cannot_remove_previous_beat_even_on_rounded_frame(self):
        for beat in (800, 759):
            self.cut(-240)
            self.plan["shots"][0]["narration_beats"][-1]["at_ms"] = beat
            self.assertTrue(any("遮掉旁白节拍" in e for e in validate_visual_cuts(self.plan, 30, 2100)))

    def test_invalid_type_first_shot_missing_reason_and_zero_frame_fail(self):
        for offset in (True, 0.5, "-250", -1000, -999, 1100):
            self.cut(offset)
            self.assertTrue(validate_visual_cuts(self.plan, 30, 2100), offset)
        for cut in (None, {}, {"offset_ms": 0}, {"offset_ms": -250, "reason": "", "bridge": "ready"}):
            self.plan["shots"][1]["transition"] = {"visual_cut": cut}
            self.assertTrue(validate_visual_cuts(self.plan, 30, 2100), cut)
        self.cut(-250)
        self.plan["shots"][0]["transition"] = copy.deepcopy(self.plan["shots"][1]["transition"])
        self.assertTrue(any("首镜" in e for e in validate_visual_cuts(self.plan, 30, 2100)))

    def test_cut_is_checked_without_sequence_policy(self):
        self.cut(400)
        self.assertTrue(validate_plan(self.plan, {"video": {"fps": 30}})["errors"])

    def test_outgoing_boundary_outside_selection_invalidates_review_hash(self):
        self.cut(250)
        before = scope_hash(self.plan, ["S001"])
        self.cut(200)
        self.assertNotEqual(before, scope_hash(self.plan, ["S001"]))
        self.plan["shots"][1]["transition"].pop("visual_cut")
        self.assertNotEqual(before, scope_hash(self.plan, ["S001"]))

    def test_markdown_exposes_cut_but_keeps_semantic_time(self):
        self.cut(-250)
        for shot in self.plan["shots"]:
            shot.update(screen_role="A", production={"primary_tool": "existing-media"},
                        visual_design={"motion_intent": "按旁白展示结构"})
        markdown = render(self.plan)
        self.assertIn("1000ms-1900ms", markdown)
        self.assertIn("视觉切入：750ms", markdown)
        self.assertEqual("pass", validate_markdown(self.plan, markdown)["status"])
        self.assertEqual("fail", validate_markdown(self.plan, markdown.replace("750ms", "1000ms"))["status"])


if __name__ == "__main__":
    unittest.main()
