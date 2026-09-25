from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from media_evidence import digest
from validate_template_index import validate_evidence


class TemplateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Unit fixtures test evidence binding only; these are not certified production templates.
        for name in ("source.html", "preview.mp4", "font.woff2", "review.md"):
            (self.root / name).write_text(name, encoding="utf-8")
        self.template = {"id": "example", "source_file": "source.html", "preview": "preview.mp4",
                         "text_capacity": {"font_path": "font.woff2"}, "validation_evidence": "evidence.json"}
        self.evidence = {"schema_version": "1.0", "template_id": "example", "status": "pass",
                         "video": {"width": 1920, "height": 1080, "fps": 30}, "seek_times_ms": [0, 1500, 3000],
                         "checks": {key: "pass" for key in ("render", "seek_safe", "chinese_capacity", "visual")},
                         "files": [{"path": p.name, "sha256": digest(p)} for p in self.root.iterdir()],
                         "review": {"source": "user", "evidence": "review.md"}}
        self.save()

    def save(self):
        (self.root / "evidence.json").write_text(json.dumps(self.evidence), encoding="utf-8")

    def test_matching_evidence(self):
        self.assertEqual(validate_evidence(self.root, self.template), [])

    def test_changed_source_invalidates_certification(self):
        (self.root / "source.html").write_text("changed", encoding="utf-8")
        self.assertTrue(any("过期" in e for e in validate_evidence(self.root, self.template)))

    def test_missing_font_binding_rejected(self):
        self.evidence["files"] = [f for f in self.evidence["files"] if f["path"] != "font.woff2"]
        self.save()
        self.assertTrue(any("未绑定" in e for e in validate_evidence(self.root, self.template)))

    def test_unreviewed_template_rejected(self):
        self.evidence["review"] = {}
        self.save()
        self.assertTrue(any("审核来源" in e for e in validate_evidence(self.root, self.template)))


if __name__ == "__main__":
    unittest.main()
