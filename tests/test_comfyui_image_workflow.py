"""Check shared Qwen image workflows and exact-size override behavior."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_comfyui_image_workflow import configure_workflow  # noqa: E402


class QwenImageWorkflowTests(unittest.TestCase):
    def load(self, name: str):
        return json.loads((ROOT / "workflows" / name).read_text(encoding="utf-8"))

    def test_t2i_uses_exact_requested_dimensions(self):
        workflow = self.load("qwen_image_2_1_t2i_api.json")
        configure_workflow(workflow, [], None, "scene prompt", None, 1280, 736, 42, "test/t2i")
        latent = workflow["459:456"]["inputs"]
        self.assertEqual((latent["width"], latent["height"]), (1280, 736))
        self.assertEqual(workflow["459:452"]["inputs"]["prompt"], "scene prompt")

    def test_edit_defaults_to_reference_latent_and_accepts_one_image(self):
        workflow = self.load("qwen_image_2_1_edit_keyframe_api.json")
        configure_workflow(workflow, ["first.png"], None, "change hand pose", None, None, None, 42, "test/edit")
        self.assertEqual(workflow["470"]["inputs"]["image"], "first.png")
        self.assertFalse(workflow["459:468"]["inputs"]["switch"])
        self.assertEqual(workflow["459:474"]["inputs"]["prompt"], "change hand pose")
        self.assertNotIn("images.image_2", workflow["459:474"]["inputs"])

    def test_edit_can_override_output_size(self):
        workflow = self.load("qwen_image_2_1_edit_keyframe_api.json")
        configure_workflow(workflow, ["first.png"], None, "change hand pose", None, 1280, 736, 42, "test/edit")
        self.assertTrue(workflow["459:468"]["inputs"]["switch"])
        self.assertEqual(workflow["459:456"]["inputs"]["width"], 1280)
        self.assertEqual(workflow["459:456"]["inputs"]["height"], 736)

    def test_dimensions_must_be_complete(self):
        with self.assertRaisesRegex(ValueError, "同时提供"):
            configure_workflow(self.load("qwen_image_2_1_t2i_api.json"), [], None, "scene", None, 1280, None, None, "test/t2i")


if __name__ == "__main__":
    unittest.main()
