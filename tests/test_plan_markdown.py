"""Production routes must survive rendering and remain faithful to the plan."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from render_plan_markdown import display_type, render
from validate_plan_markdown import validate


class ProductionRouteMarkdownTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"shots": [{
            "id": "S001", "start_ms": 0, "end_ms": 2000, "screen_role": "B",
            "material_type": "no-material", "presentation_type": "scene",
            "verbatim_text": "保留 A|B\n保持原文",
            "visual_design": {"motion_intent": "先保持 A|B\r\n再完成动作", "final_state": "动作完成"},
            "changes": [{"at_ms": 0, "event": "建立状态"}],
            "production": {"primary_tool": "comfyui-minimax-h3-fl2v", "fallback_tools": []},
        }]}

    def test_scene_display_and_escaped_text_roundtrip(self):
        self.assertEqual(display_type(self.plan["shots"][0]), "场景画面")
        report = validate(self.plan, render(self.plan))
        self.assertEqual(report["status"], "pass", report["errors"])

    def test_route_tool_and_role_cannot_drift_from_json(self):
        for old, new in (("comfyui-minimax-h3-fl2v", "remotion"), ("| S001 | B |", "| S001 | A |")):
            with self.subTest(replacement=new):
                report = validate(self.plan, render(self.plan).replace(old, new))
                self.assertEqual(report["status"], "fail")

    def test_renderer_placeholders_do_not_approve_missing_decisions(self):
        for path in ("motion_intent", "primary_tool"):
            plan = copy.deepcopy(self.plan)
            container = "visual_design" if path == "motion_intent" else "production"
            del plan["shots"][0][container][path]
            with self.subTest(field=path):
                self.assertEqual(validate(plan, render(plan))["status"], "fail")

    def test_removing_route_section_is_rejected(self):
        markdown = render(self.plan)
        start, end = markdown.index("## 逐镜制作路由"), markdown.index("## 全片检查")
        self.assertEqual(validate(self.plan, markdown[:start] + markdown[end:])["status"], "fail")


if __name__ == "__main__":
    unittest.main()
