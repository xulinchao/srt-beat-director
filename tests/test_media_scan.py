from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from scan_video import scan
from media_evidence import probe_video


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "需要 ffmpeg/ffprobe")
class MediaScanTests(unittest.TestCase):
    def test_single_black_frame_and_both_edges_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "flash.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=white:s=160x90:r=30:d=2",
                            "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='eq(n,30)'",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True, capture_output=True)
            report = scan(video)
            self.assertEqual(report["decoded_frames"], 60)
            candidates = {c["frame"]: c for c in report["candidates"]}
            self.assertIn("black", candidates[30]["reasons"])
            self.assertIn("adjacent-change", candidates[30]["reasons"])
            self.assertIn("adjacent-change", candidates[31]["reasons"])
            self.assertIsNone(candidates[30]["review"])

    def test_invalid_media_fails_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake.mp4"
            path.write_bytes(b"not video")
            with self.assertRaisesRegex(ValueError, "失败"):
                probe_video(path)

    def test_cli_does_not_overwrite_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text('{"historic": true}', encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/scan_video.py"),
                                     "--video", "missing.mp4", "--out", str(path)], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"historic": True})


if __name__ == "__main__":
    unittest.main()
