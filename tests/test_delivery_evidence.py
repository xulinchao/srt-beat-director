from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from delivery_evidence import original_value, validate_manifest, validate_timeline_item
from media_evidence import digest, probe_source_duration, validate_source_time


class TimelineMappingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("fixture").resolve()
        self.item = {"item_id": "item", "asset_id": "asset", "range_frames": [60, 120]}
        self.snapshot = {"item": dict(self.item, artifact="clip.mp4", source_start_ms=200, playback_rate=2)}
        self.evidence = {"artifact": "clip.mp4", "artifact_time_ms": 1200}

    def test_trim_and_speed_are_mapped(self):
        self.assertEqual([], validate_timeline_item(self.root, self.item, self.evidence, 2500, self.snapshot, 30))

    def test_incorrect_source_time_is_rejected(self):
        self.evidence["artifact_time_ms"] = 300
        errors = validate_timeline_item(self.root, self.item, self.evidence, 2500, self.snapshot, 30)
        self.assertTrue(any("裁切/速度映射" in e for e in errors))

    def test_wrong_source_asset_is_rejected(self):
        self.evidence["artifact"] = "another.mp4"
        self.assertTrue(any("实际资产" in e for e in validate_timeline_item(self.root, self.item, self.evidence, 2500, self.snapshot, 30)))

    def test_native_microseconds_can_be_normalized(self):
        raw = {"startUs": 2000000, "endUs": 4000000, "sourceUs": 200000, "a/b": {"~id": "item"}}
        references = [{"pointer": "/startUs", "scale": 30 / 1000000, "round_to_frame": True},
                      {"pointer": "/endUs", "scale": 30 / 1000000, "round_to_frame": True}]
        self.assertEqual([60, 120], original_value(raw, references))
        self.assertEqual(200, original_value(raw, {"pointer": "/sourceUs", "scale": 0.001}))
        self.assertEqual("item", original_value(raw, "/a~1b/~0id"))


class ManifestEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "input.txt").write_text("source", encoding="utf-8")
        self.entry = {"path": "input.txt", "sha256": digest(self.root / "input.txt"),
                      "source": "user", "version": "1", "status": "current"}

    def test_valid_inventory_passes(self):
        self.assertEqual([], validate_manifest(self.root, {"files": [self.entry]}, {"input.txt"}))

    def test_missing_source_metadata_is_rejected(self):
        del self.entry["source"]
        self.assertTrue(any("缺少 source" in e for e in validate_manifest(self.root, {"files": [self.entry]}, set())))

    def test_aliases_cannot_hide_duplicate_files(self):
        alias = dict(self.entry, path="./input.txt")
        self.assertTrue(any("文件重复" in e for e in validate_manifest(self.root, {"files": [self.entry, alias]}, set())))

    def test_outside_file_is_rejected(self):
        self.entry["path"] = "../outside.txt"
        self.assertTrue(any("越界" in e for e in validate_manifest(self.root, {"files": [self.entry]}, set())))

    def test_self_hash_is_rejected(self):
        (self.root / "reports").mkdir()
        path = self.root / "reports/manifest.json"
        path.write_text("{}", encoding="utf-8")
        self.entry.update(path="reports/manifest.json", sha256=digest(path))
        self.assertTrue(any("自身哈希" in e for e in validate_manifest(self.root, {"files": [self.entry]}, set())))


class SourceMediaTests(unittest.TestCase):
    def test_probe_is_cached_across_beats(self):
        cache = {}
        with patch("media_evidence.probe_source_duration", return_value=2000) as probe:
            self.assertEqual([], validate_source_time(Path("clip.mp4"), 0, cache))
            self.assertEqual([], validate_source_time(Path("clip.mp4"), 1999, cache))
            self.assertTrue(validate_source_time(Path("clip.mp4"), 2000, cache))
            probe.assert_called_once()

    def test_boolean_source_time_is_rejected(self):
        self.assertTrue(validate_source_time(Path("clip.mp4"), True, {}))

    def test_audio_cover_cannot_be_continuous_video(self):
        from types import SimpleNamespace
        response = SimpleNamespace(returncode=0, stderr="", stdout='{"streams":[{"codec_type":"video","duration":"2","disposition":{"attached_pic":1}}]}')
        with patch("media_evidence.shutil.which", return_value="ffprobe"), patch("media_evidence.subprocess.run", return_value=response):
            with self.assertRaisesRegex(ValueError, "单个视频流"):
                probe_source_duration(Path("cover.mp3"))
