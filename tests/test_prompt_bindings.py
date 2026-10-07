from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from media_evidence import digest
from prompt_bindings import capture, section_hashes, validate_binding
from validate_prompt_usage import validate_record, validate

SOURCE = """# Shared policy
Common rules.
## 1. A
`prompt_id: a-v1`
```Markdown
## Nested heading
Do A.
```
## 2. B
`prompt_id: b-v1`
Note B.
```Markdown
Do B.
```
## Usage
Shared usage rules.
"""


class PromptBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "current.md"
        self.source.write_text(SOURCE, encoding="utf-8")
        self.record = capture(self.root, self.source, ["a-v1"], "prompts/sources/source.md", "prompts/sources/binding.json")

    def test_current_sections_match(self):
        self.assertEqual(validate_binding(self.root, self.record, self.source), [])

    def test_unused_section_changes_allowed(self):
        self.source.write_text(SOURCE.replace("Do B.", "Changed B."), encoding="utf-8")
        self.assertEqual(validate_binding(self.root, self.record, self.source), [])

    def test_used_section_changes_fail(self):
        self.source.write_text(SOURCE.replace("Do A.", "Changed A."), encoding="utf-8")
        self.assertTrue(validate_binding(self.root, self.record, self.source))

    def test_shared_rule_changes_fail(self):
        for old in ("Common rules.", "Shared usage rules."):
            self.source.write_text(SOURCE.replace(old, "Changed rules."), encoding="utf-8")
            self.assertTrue(validate_binding(self.root, self.record, self.source))

    def test_archive_tampering_fail(self):
        (self.root / "prompts/sources/source.md").write_text("tampered", encoding="utf-8")
        self.assertTrue(validate_binding(self.root, self.record, self.source))

    def test_prompt_ids_and_binding_must_match(self):
        self.record["prompt_ids"] = ["a-v1", "b-v1"]
        self.assertTrue(validate_binding(self.root, self.record, self.source))

    def test_duplicate_and_unknown_ids_fail(self):
        for ids in (["a-v1", "a-v1"], ["unknown-v1"]):
            with self.assertRaises(ValueError):
                capture(self.root, self.source, ids, "new.md", "new.json")
        self.assertFalse((self.root / "new.md").exists())

    def test_duplicate_chapters_and_unclosed_fences_fail(self):
        for text in (SOURCE + "## Duplicate\n`prompt_id: a-v1`\n", SOURCE + "```Markdown\n"):
            self.source.write_text(text)
            with self.assertRaises(ValueError):
                section_hashes(self.source)

    def test_crlf_hashes_and_nested_prompt_marker(self):
        before = section_hashes(self.source)
        self.source.write_bytes(SOURCE.replace("\n", "\r\n").encode())
        self.assertEqual(section_hashes(self.source), before)
        self.source.write_text(SOURCE.replace("Do A.", "`prompt_id: fake-v1`"))
        self.assertEqual(set(section_hashes(self.source)["prompts"]), {"a-v1", "b-v1"})

    def test_archive_outside_project_fails(self):
        self.record["prompt_binding"]["source_snapshot"]["path"] = "../outside.md"
        self.assertTrue(validate_binding(self.root, self.record, self.source))

    def test_no_overwrite(self):
        with self.assertRaises(ValueError):
            capture(self.root, self.source, ["a-v1"], "prompts/sources/source.md", "new.json")
        self.assertFalse((self.root / "new.json").exists())

    def test_repository_prompt_ids(self):
        self.assertEqual(len(section_hashes(ROOT / "references/production-prompts.md")["prompts"]), 6)

    def test_validate_record_legacy_and_scoped(self):
        record_path = self.root / "record.json"
        self.record.update(subject_id="shot", inputs={"shot": "shot"}, resolved_prompt="actual", status="prepared")
        self.source.write_text(SOURCE.replace("Do B.", "Changed B."))
        def check():
            errors = []
            record_path.write_text(json.dumps(self.record))
            validate_record(record_path=record_path, project_dir=self.root, expected_subject="shot",
                            required_prompt_ids={"a-v1"}, prompt_hash=digest(self.source),
                            prompts_path=self.source, stage="prepared", errors=errors, checked=[])
            return errors
        self.assertEqual(check(), [])
        del self.record["prompt_binding"]
        self.assertTrue(any("过期" in error for error in check()))

    def test_cli_capture(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/prompt_bindings.py"),
                                 "--project-dir", str(self.root), "--source", str(self.source),
                                 "--prompt-id", "b-v1", "--archive", "cli.md", "--out", "cli.json"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads((self.root / "cli.json").read_text())
        self.assertEqual(validate_binding(self.root, record, self.source), [])

    def test_planning_validator_uses_scoped_protocol(self):
        self.source.write_bytes((ROOT / "references/production-prompts.md").read_bytes())
        record = capture(self.root, self.source, ["visual-plan-v1"], "planning-source.md", "planning-binding.json")
        record.update(subject_id="visual-plan", inputs={"srt": "source"}, resolved_prompt="actual planning", status="prepared")
        (self.root / "config").mkdir()
        (self.root / "planning").mkdir()
        (self.root / "config/project.json").write_text(json.dumps({"a_scene_mode": "fixed-character-micro-scene"}))
        (self.root / "planning/visual-plan.json").write_text(json.dumps({"shots": []}))
        (self.root / "planning/visual-plan-prompt.json").write_text(json.dumps(record))
        source = self.source.read_text(encoding="utf-8")
        self.source.write_text(source.replace("## 3. A-roll 画面", "## 3. Updated A-roll section"), encoding="utf-8")
        report = validate(self.root, self.source, "planning")
        self.assertEqual(report["status"], "pass", report["errors"])
        self.source.write_text(self.source.read_text(encoding="utf-8").replace("## 使用规则", "## Changed shared rules"), encoding="utf-8")
        report = validate(self.root, self.source, "planning")
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("共用规则" in message for message in report["errors"]))


if __name__ == "__main__":
    unittest.main()
