from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from preflight import build_report, validate_preflight
from project_fixtures import bind_preflight
from validate_plan import validate_units


class PlanCoverageTests(unittest.TestCase):
    def setUp(self):
        self.cues = [{"id": value, "start_ms": index * 1100, "end_ms": index * 1100 + 1000,
                      "text": str(value)} for index, value in enumerate((10, 20, 30))]

    def errors(self, groups):
        by_id = {cue["id"]: cue for cue in self.cues}
        units = [{"id": f"S{i:03}", "cue_ids": ids,
                  "start_ms": by_id[ids[0]]["start_ms"], "end_ms": by_id[ids[-1]]["end_ms"],
                  "verbatim_text": "\n".join(by_id[v]["text"] for v in ids)} for i, ids in enumerate(groups, 1)]
        errors = []
        validate_units("visual-plan", units, by_id, [cue["id"] for cue in self.cues], errors)
        return errors

    def test_nonsequential_original_ids_and_real_gaps_are_allowed(self):
        self.assertEqual([], self.errors([[10, 20], [30]]))

    def test_interleaved_units_are_rejected(self):
        errors = self.errors([[10, 30], [20]])
        self.assertTrue(any("连续覆盖" in e for e in errors))
        self.assertTrue(any("重叠" in e for e in errors))

    def test_reversed_cues_are_rejected(self):
        self.assertTrue(any("连续覆盖" in e for e in self.errors([[20, 10], [30]])))


class PreflightBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = {}
        self.report = {"srt": {"cues": [{"id": 1, "start_ms": 0, "end_ms": 1000, "text": "one"}]},
                       "audio": {"duration_ms": 1000}}
        bind_preflight(self.root, self.project, self.report)

    def test_current_inputs_pass(self):
        self.assertEqual([], validate_preflight(self.report, self.project, self.root))

    def test_failed_report_is_rejected(self):
        self.report["status"] = "fail"
        self.assertTrue(any("预检未通过" in e for e in validate_preflight(self.report, self.project, self.root)))

    def test_changed_audio_is_rejected(self):
        (self.root / self.project["inputs"]["audio"]).write_bytes(b"changed")
        self.assertTrue(any("SHA-256 已过期" in e for e in validate_preflight(self.report, self.project, self.root)))

    def test_cue_changes_cannot_hide_behind_current_hash(self):
        self.report["srt"]["cues"][0]["text"] = "invented"
        self.assertTrue(any("与当前 SRT" in e for e in validate_preflight(self.report, self.project, self.root)))

    def test_duplicate_cue_ids_fail_real_preflight(self):
        source = self.root / self.project["inputs"]["srt"]
        source.write_text("1\n00:00:00,000 --> 00:00:01,000\none\n\n1\n00:00:01,000 --> 00:00:02,000\ntwo\n", encoding="utf-8")
        args = argparse.Namespace(srt=source, audio=self.root / self.project["inputs"]["audio"], duration_tolerance_ms=250)
        with patch("preflight.audio_duration_ms", return_value=2000):
            report = build_report(args)
        self.assertEqual("fail", report["status"])
        self.assertTrue(any("唯一正整数" in e for e in report["errors"]))

    def test_failed_preflight_is_rejected_by_plan_cli(self):
        (self.root / "config").mkdir()
        (self.root / "planning").mkdir()
        self.report["status"] = "fail"
        documents = {"config/project.json": self.project, "planning/preflight.json": self.report,
                     "planning/content.json": {"semantic_segments": []}, "planning/plan.json": {"shots": []}}
        for name, value in documents.items():
            (self.root / name).write_text(json.dumps(value), encoding="utf-8")
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/validate_plan.py"),
                                 "--project", str(self.root / "config/project.json"),
                                 "--preflight", str(self.root / "planning/preflight.json"),
                                 "--content-analysis", str(self.root / "planning/content.json"),
                                 "--visual-plan", str(self.root / "planning/plan.json"),
                                 "--out-dir", str(self.root / "out")], capture_output=True)
        self.assertEqual(2, result.returncode)
        report = json.loads((self.root / "out/plan-validation-report.json").read_text(encoding="utf-8"))
        self.assertTrue(any("预检未通过" in e for e in report["errors"]), report)
