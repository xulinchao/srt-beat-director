"""Regression checks for the shared MiniMax H3 first/last-frame workflow."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_comfyui_workflow import configure_workflow  # noqa: E402


class MiniMaxH3WorkflowTests(unittest.TestCase):
    def test_t8_reference_motion_preserves_audio(self):
        workflow = json.loads((ROOT / "workflows/minimax_h3_motion_ref_audio_api.json").read_text(encoding="utf-8"))
        configure_workflow(workflow, None, None, ["design.png"], "motion and sound", 124, 1344, 768, 42, "test/motion")
        self.assertEqual(workflow["310"]["inputs"]["prompt"], "motion and sound")
        self.assertEqual(workflow["310"]["inputs"]["length"], 124)
        self.assertEqual(workflow["282"]["inputs"]["image"], "design.png")
        self.assertEqual(workflow["306"]["inputs"]["audio"], ["280", 1])
        self.assertEqual(workflow["310"]["inputs"]["audio_mode"], "native")
        with self.assertRaisesRegex(ValueError, "不是精确首尾帧"):
            configure_workflow(workflow, "first.png", None, [], "motion", None, None, None, None, "test")
        with self.assertRaisesRegex(ValueError, "需要 1 张"):
            configure_workflow(workflow, None, None, ["one.png", "two.png"], "motion", None, None, None, None, "test")

    def test_native_output_has_one_sampler_and_no_resize(self):
        workflow = json.loads((ROOT / "workflows/minimax_h3_fl2v_turbo_native_api.json").read_text(encoding="utf-8"))
        configure_workflow(workflow, "first.png", "last.png", [], "motion", 124, 1344, 768, 42, "test/native")
        self.assertEqual(workflow["105:104"]["inputs"]["width"], 1344)
        self.assertEqual(workflow["105:104"]["inputs"]["height"], 768)
        classes = [node["class_type"] for node in workflow.values()]
        self.assertEqual(classes.count("SamplerCustomAdvanced"), 1)
        self.assertFalse(any("upscal" in name.lower() or name == "ImageScale" for name in classes))
        self.assertEqual(workflow["105:91"]["inputs"]["images"], ["105:10", 0])
        self.assertEqual(workflow["92"]["inputs"]["video"], ["105:91", 0])

    def test_upscale_workflow_is_rejected(self):
        workflow = self.load_workflow()
        workflow["disabled"] = {"class_type": "MiniMaxH3LatentUpscaleCombined", "inputs": {}}
        with self.assertRaisesRegex(ValueError, "停用"):
            configure_workflow(workflow, "first.png", "last.png", [], "motion", None, None, None, None, "test")

    def test_partial_dimensions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "同时"):
            configure_workflow(self.load_workflow(), "first.png", "last.png", [], "motion", None, 1344, None, None, "test")

    def test_dry_run_works_without_server(self):
        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory) / "frame.png"
            frame.write_bytes(b"dry-run-placeholder")
            result = subprocess.run([
                sys.executable, "-B", str(ROOT / "scripts/run_comfyui_workflow.py"),
                "--url", "http://127.0.0.1:1", "--workflow",
                str(ROOT / "workflows/minimax_h3_fl2v_turbo_native_api.json"),
                "--first-frame", str(frame), "--last-frame", str(frame),
                "--prompt", "motion", "--width", "1344", "--height", "768",
                "--out-dir", directory, "--dry-run",
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["environment_checked"])
            self.assertTrue(Path(report["request"]).is_file())

    def load_workflow(self):
        path = ROOT / "workflows" / "minimax_h3_fl2v_turbo_api.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_two_frames_and_turbo_reach_the_sampler(self):
        workflow = self.load_workflow()
        configure_workflow(
            workflow, "first.png", "last.png", [], "subject moves naturally",
            124, None, None, 42, "test/fl2v",
        )
        video = workflow["105:104"]["inputs"]
        self.assertEqual(workflow[video["first_frame"][0]]["inputs"]["image"], "first.png")
        self.assertEqual(workflow[video["last_frame"][0]]["inputs"]["image"], "last.png")
        self.assertEqual(video["prompt"], "subject moves naturally")
        self.assertTrue(workflow["105:126"]["inputs"]["value"])
        self.assertEqual(workflow["105:125"]["inputs"]["value"], 8)
        self.assertEqual(workflow["105:16"]["inputs"]["model"], ["900", 0])
        self.assertEqual(workflow["900"]["inputs"]["model"], ["105:122", 0])
        self.assertEqual(workflow["105:123"]["inputs"]["on_true"], ["105:125", 0])
        self.assertEqual(workflow["105:122"]["inputs"]["on_true"], ["105:121", 0])
        self.assertNotIn("audio", workflow["105:91"]["inputs"])

    def test_last_frame_is_required(self):
        with self.assertRaisesRegex(ValueError, "last-frame"):
            configure_workflow(
                self.load_workflow(), "first.png", None, [], "movement",
                None, None, None, None, "test/fl2v",
            )

    def test_other_shared_modes_keep_their_turbo_paths(self):
        for filename, switch, steps, references in (
            ("minimax_h3_i2v_turbo_api.json", "105:126", "105:125", []),
            ("minimax_h3_r2v_turbo_api.json", "146", "144", ["ref1.png", "ref2.png"]),
        ):
            with self.subTest(filename=filename):
                workflow = json.loads((ROOT / "workflows" / filename).read_text(encoding="utf-8"))
                configure_workflow(
                    workflow, "first.png", None, references, "gentle motion",
                    124, None, None, 42, "test/video",
                )
                self.assertTrue(workflow[switch]["inputs"]["value"])
                self.assertEqual(workflow[steps]["inputs"]["value"], 4 if references else 8)
                self.assertTrue(any(n["class_type"] == "SaveVideo" for n in workflow.values()))

    def test_three_reference_workflow_uses_local_turbo_model(self):
        path = ROOT / "workflows" / "minimax_h3_r2v_3ref_optimized_api.json"
        workflow = json.loads(path.read_text(encoding="utf-8"))
        configure_workflow(
            workflow, None, None, ["one.png", "two.png", "three.png"],
            "natural interaction", 124, None, None, 42, "test/three-ref",
        )
        inputs = workflow["245"]["inputs"]
        for index, filename in enumerate(("one.png", "two.png", "three.png")):
            load_id = inputs[f"ref_images.ref_image_{index}"][0]
            self.assertEqual(workflow[load_id]["inputs"]["image"], filename)
        self.assertTrue(workflow["247"]["inputs"]["value"])
        self.assertEqual(workflow["251"]["inputs"]["on_true"], ["250", 0])
        self.assertEqual(workflow["250"]["inputs"]["value"], 4)
        self.assertEqual(workflow["248"]["inputs"]["on_true"], ["246", 0])
        self.assertEqual(workflow["219"]["inputs"]["model"], ["900", 0])
        self.assertEqual(workflow["900"]["inputs"]["model"], ["248", 0])
        self.assertEqual(workflow["232"]["inputs"]["model"], ["248", 0])
        self.assertEqual(workflow["238"]["inputs"]["unet_name"], "minimax_h3_ref2va_pruned_int8_convrot.safetensors")
        self.assertFalse(any(node["class_type"] in {"EasyCache", "VHS_VideoCombine"} for node in workflow.values()))
        self.assertNotIn("audio", workflow["220"]["inputs"])

    def test_three_reference_count_is_exact(self):
        path = ROOT / "workflows" / "minimax_h3_r2v_3ref_optimized_api.json"
        workflow = json.loads(path.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "需要 3 张参考图"):
            configure_workflow(
                workflow, None, None, ["one.png", "two.png"],
                "movement", None, None, None, None, "test/three-ref",
            )


if __name__ == "__main__":
    unittest.main()
