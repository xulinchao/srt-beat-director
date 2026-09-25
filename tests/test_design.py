from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_design import validate, digest
from render_plan_markdown import design_text


class DesignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = {"design_contract_version": "1.0", "review_mode": "manual", "video": {"width": 1920, "height": 1080, "fps": 30, "aspect_ratio": "16:9"}, "subtitle_safe_area": {"bottom_fraction": 0.22}}
        self.write("config/project.json", self.project)
        for path in ("config/font.ttf", "config/sample.png", "review.md"):
            p = self.root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"fixture")
        self.rules = {"video": self.project["video"], "fonts": [{"family": "Test", "path": "font.ttf"}], "font_sizes": {"body": 48}, "max_chars_per_line": 16, "max_lines": 4, "margin_fraction": 0.08, "subtitle_bottom_fraction": 0.22, "colors": {"text": "#111111"}, "graphic_language": "thin arrows", "character_direction": "identity reference", "scene_density": "minimal", "motion": "hold after contact"}
        self.film = {"schema_version": "1.0", "scope": "film", "version": "v1", "account": None, "rules": self.rules, "samples": [{"path": "sample.png", "sha256": digest(self.root / "config/sample.png")}]}
        self.save_spec()
        self.visual = {"design_ref": self.ref, "resolved_design": self.rules, "design_review": {"status": "approved", "sha256": self.ref["sha256"], "review_source": "user", "evidence": "review.md"}}
        self.plan = {"design_ref": self.ref, "shots": [{"id": "S001", "screen_role": "B", "end_ms": 2000, "narration_beats": [{"at_ms": 0}, {"at_ms": 1000}], "visual_design": {"function": "解释", "relation": "对象归属", "carrier": "独立图解", "character_role": "托举"}}]}
        self.write("config/visual-style.json", self.visual)
        self.write("planning/visual-plan.json", self.plan)
        for path in ("planning/visual-plan-prompt.json", "prompts/b-scenes/S001.json", "planning/template-selection/S001.json"):
            self.write(path, {"design_ref": self.ref})

    def write(self, path, data):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def save_spec(self):
        p = self.root / "config/DESIGN.md"
        p.write_text("```design-spec\n" + json.dumps(self.film) + "\n```\n", encoding="utf-8")
        self.ref = {"path": "config/DESIGN.md", "version": "v1", "sha256": digest(p)}

    def test_valid_all_stages(self):
        for stage in ("planning", "prepared", "produced"):
            self.assertEqual(validate(self.root, stage)["errors"], [])

    def test_design_edit_invalidates_reference(self):
        with (self.root / "config/DESIGN.md").open("a") as f:
            f.write("changed")
        self.assertTrue(any("哈希过期" in e for e in validate(self.root)["errors"]))

    def test_missing_font(self):
        (self.root / "config/font.ttf").unlink()
        self.assertTrue(any("字体" in e for e in validate(self.root, "prepared")["errors"]))

    def test_manual_cannot_self_approve(self):
        self.visual["design_review"]["review_source"] = "agent-qa-under-user-authorization"
        self.write("config/visual-style.json", self.visual)
        self.assertTrue(any("manual" in e for e in validate(self.root, "prepared")["errors"]))

    def test_selection_must_bind_design(self):
        self.write("planning/template-selection/S001.json", {})
        self.assertTrue(any("选型" in e for e in validate(self.root, "prepared")["errors"]))

    def test_interaction_boundary_and_asset(self):
        interaction = {"participants": ["c", "o"], "layout": "left", "occlusion": "front", "fallback": "point", "events": [{"beat_index": 0, "offset_ms": 500, "duration_ms": 600, "actor": "o", "target": "c", "action": "land", "contact": "palm", "reaction": "hold"}], "assets": [{"id": "c", "path": "missing.png"}]}
        self.plan["shots"][0]["visual_design"]["interaction"] = interaction
        self.write("planning/visual-plan.json", self.plan)
        errors = validate(self.root, "produced")["errors"]
        self.assertTrue(any("节拍边界" in e for e in errors))
        self.assertTrue(any("资产文件" in e for e in errors))
        interaction["events"][0]["duration_ms"] = 500
        interaction["assets"][0]["path"] = "config/sample.png"
        self.write("planning/visual-plan.json", self.plan)
        self.assertEqual(validate(self.root, "produced")["errors"], [])
        self.assertIn("托举", design_text(self.plan["shots"][0]))

    def test_legacy_warns(self):
        self.write("config/project.json", {})
        self.write("config/visual-style.json", {})
        self.write("planning/visual-plan.json", {})
        report = validate(self.root)
        self.assertFalse(report["errors"])
        self.assertTrue(report["warnings"])

    def test_account_hash_is_checked(self):
        account = dict(self.film, scope="account", account=None)
        p = self.root / "config/account.md"
        p.write_text("```design-spec\n" + json.dumps(account) + "\n```\n", encoding="utf-8")
        self.film["account"] = {"path": "account.md", "version": "v1", "sha256": "bad"}
        self.save_spec()
        self.visual["design_ref"] = self.ref
        self.write("config/visual-style.json", self.visual)
        self.assertTrue(any("账号 DESIGN" in e for e in validate(self.root)["errors"]))

    def test_account_inheritance_and_film_override(self):
        account = dict(self.film, scope="account", account=None)
        account["rules"] = dict(self.rules, colors={"text": "#222222"})
        p = self.root / "config/account.md"
        p.write_text("```design-spec\n" + json.dumps(account) + "\n```\n", encoding="utf-8")
        self.film["account"] = {"path": "account.md", "version": "v1", "sha256": digest(p)}
        self.film["rules"] = {"colors": self.rules["colors"]}
        self.save_spec()
        self.visual["design_ref"] = self.ref
        self.visual["design_review"]["sha256"] = self.ref["sha256"]
        self.plan["design_ref"] = self.ref
        self.write("config/visual-style.json", self.visual)
        self.write("planning/visual-plan.json", self.plan)
        for path in ("planning/visual-plan-prompt.json", "prompts/b-scenes/S001.json", "planning/template-selection/S001.json"):
            self.write(path, {"design_ref": self.ref})
        self.assertEqual(validate(self.root, "prepared")["errors"], [])

    def test_parameter_drift_and_malformed_design(self):
        self.visual["resolved_design"] = dict(self.rules, max_lines=8)
        self.write("config/visual-style.json", self.visual)
        self.assertTrue(any("resolved_design" in e for e in validate(self.root)["errors"]))
        (self.root / "config/DESIGN.md").write_text("```design-spec\n[]\n```", encoding="utf-8")
        self.assertEqual(validate(self.root)["status"], "fail")


if __name__ == "__main__":
    unittest.main()
