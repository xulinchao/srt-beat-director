from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from media_evidence import digest
from promote_template import promote
from validate_template_index import template_digest, validate


class TemplatePromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.target = self.root / "target"
        self.prefix = "templates/library/example"
        package = self.source / self.prefix
        package.mkdir(parents=True)
        for name in ("index.html", "preview.mp4", "font.woff2", "review.md", "LICENSE", "package.json"):
            (package / name).write_text("structural unit fixture only: " + name)
        self.template = {
            "id": "example", "metadata_version": "1.0", "semantic_structure": "comparison",
            "item_range": [2, 2], "duration_ms": [1500, 2500], "aspect_ratios": ["16:9"],
            "source_file": f"{self.prefix}/index.html", "preview": f"{self.prefix}/preview.mp4",
            "runtime": "hyperframes", "animation_status": "animation-verified",
            "animation_phases": ["start", "change", "result"], "element_relation": "two equal dimensions",
            "text_capacity": {"font_path": f"{self.prefix}/font.woff2"}, "replaceable_fields": ["labels"],
            "validation_evidence": f"{self.prefix}/evidence.json",
            "source": {"license": "unit-test-license", "license_evidence": f"{self.prefix}/LICENSE"}}
        self.evidence = {
            "schema_version": "1.0", "template_id": "example", "status": "pass",
            "video": {"width": 320, "height": 180, "fps": 30}, "seek_times_ms": [0, 500, 1500],
            "checks": {key: "pass" for key in ("render", "seek_safe", "chinese_capacity", "visual", "portable")},
            "review": {"source": "user", "evidence": f"{self.prefix}/review.md"}}
        self.save()
        (self.target / "templates").mkdir(parents=True)
        self.target_index = self.target / "templates/template-index.json"
        self.target_index.write_text(json.dumps({"schema_version": "0.1", "templates": []}))
        self.probe = patch("promote_template.probe_video", return_value={
            "width": 320, "height": 180, "fps": 30, "duration_ms": 2000, "decoded_frames": 60})
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def save(self):
        self.evidence["template_sha256"] = template_digest(self.template)
        self.evidence["files"] = [
            {"path": path.relative_to(self.source).as_posix(), "sha256": digest(path)}
            for path in (self.source / self.prefix).rglob("*") if path.is_file() and path.name != "evidence.json"]
        (self.source / self.template["validation_evidence"]).write_text(json.dumps(self.evidence))
        (self.source / "templates/template-index.json").write_text(json.dumps({"templates": [self.template]}))

    def test_dry_run_does_not_change_target(self):
        original = self.target_index.read_bytes()
        report = promote(self.source, self.target, "example")
        self.assertFalse(report["applied"])
        self.assertEqual(self.target_index.read_bytes(), original)
        self.assertFalse((self.target / self.prefix).exists())

    def test_copy_exact_bytes_and_reject_overwrite(self):
        self.assertTrue(promote(self.source, self.target, "example", apply=True)["applied"])
        self.assertEqual(validate(self.target_index)["errors"], [])
        for path in (self.source / self.prefix).rglob("*"):
            if path.is_file():
                self.assertEqual(path.read_bytes(), (self.target / path.relative_to(self.source)).read_bytes())
        with self.assertRaisesRegex(ValueError, "不能覆盖"):
            promote(self.source, self.target, "example", apply=True)

    def test_unbound_resource_rejected(self):
        (self.source / self.prefix / "extra.js").write_text("unbound")
        with self.assertRaisesRegex(ValueError, "全部文件"):
            promote(self.source, self.target, "example")

    def test_cache_rejected(self):
        (self.source / self.prefix / "node_modules").mkdir()
        with self.assertRaisesRegex(ValueError, "缓存"):
            promote(self.source, self.target, "example")

    def test_changed_source_rejected(self):
        (self.source / self.template["source_file"]).write_text("changed")
        with self.assertRaisesRegex(ValueError, "过期"):
            promote(self.source, self.target, "example")

    def test_metadata_change_rejected(self):
        self.template["item_range"] = [2, 999]
        (self.source / "templates/template-index.json").write_text(json.dumps({"templates": [self.template]}))
        with self.assertRaisesRegex(ValueError, "元数据"):
            promote(self.source, self.target, "example")

    def test_missing_license_basis_rejected(self):
        del self.template["source"]["license_evidence"]
        self.save()
        with self.assertRaisesRegex(ValueError, "分发依据"):
            promote(self.source, self.target, "example")

    def test_missing_portable_check_rejected(self):
        del self.evidence["checks"]["portable"]
        self.save()
        with self.assertRaisesRegex(ValueError, "复现检查"):
            promote(self.source, self.target, "example")

    def test_old_certificate_not_automatically_promoted(self):
        del self.evidence["template_sha256"]
        (self.source / self.template["validation_evidence"]).write_text(json.dumps(self.evidence))
        with self.assertRaisesRegex(ValueError, "不补写"):
            promote(self.source, self.target, "example")

    def test_preview_metadata_and_out_of_bounds_seek_rejected(self):
        self.evidence["video"]["width"] = 1920
        self.save()
        with self.assertRaisesRegex(ValueError, "实际预览"):
            promote(self.source, self.target, "example")
        self.evidence["video"]["width"] = 320
        self.evidence["seek_times_ms"] = [0, 500, 2000]
        self.save()
        with self.assertRaisesRegex(ValueError, "时长"):
            promote(self.source, self.target, "example")

    def test_invalid_seek_and_nonfinite_video_rejected(self):
        for field, value in (("seek_times_ms", [0, -1, 500]), ("seek_times_ms", [0, True, 500]),
                             ("video", {"width": 320, "height": 180, "fps": float("inf")})):
            previous = copy.deepcopy(self.evidence)
            self.evidence[field] = value
            self.save()
            with self.assertRaises(ValueError):
                promote(self.source, self.target, "example")
            self.evidence = previous

    def test_preview_decodes_real_video(self):
        self.probe.stop()
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("实际预览回归需要 ffmpeg/ffprobe")
        preview = self.source / self.template["preview"]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=s=320x180:r=30:d=2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(preview)], check=True, capture_output=True)
        self.save()
        report = promote(self.source, self.target, "example")
        self.assertEqual(report["media"]["decoded_frames"], 60)

    def test_failed_copy_preserves_index(self):
        original = self.target_index.read_bytes()
        with patch("promote_template.shutil.copytree", side_effect=OSError("fixture copy failure")):
            with self.assertRaises(OSError):
                promote(self.source, self.target, "example", apply=True)
        self.assertEqual(original, self.target_index.read_bytes())


if __name__ == "__main__":
    unittest.main()
