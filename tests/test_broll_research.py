from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import select_broll_template  # noqa: E402
import validate_broll_research  # noqa: E402
import validate_template_index  # noqa: E402


def mapping() -> dict:
    return {
        "structures": [
            {
                "id": "comparison",
                "aliases": [],
                "local_template_ids": [],
                "external_candidates": [
                    {
                        "id": "candidate-a",
                        "repository": "demo-repo",
                        "path": "references/a.md",
                        "license": "Apache-2.0",
                        "status": "port-required",
                        "material_types": ["no-material"],
                        "presentation_types": ["infographic"],
                        "skeleton": {
                            "element_relation": "A 与 B 并列",
                            "main_motion": "先建立再高亮",
                            "phase_order": ["建立", "比较", "结论"],
                        },
                    },
                    {
                        "id": "candidate-b",
                        "repository": "demo-repo",
                        "path": "references/b.md",
                        "license": "Apache-2.0",
                        "status": "port-required",
                        "material_types": ["no-material"],
                        "presentation_types": ["infographic"],
                        "skeleton": {
                            "element_relation": "双路径",
                            "main_motion": "分路后汇总",
                            "phase_order": ["起点", "分路", "落点"],
                        },
                    },
                ],
            }
        ]
    }


def plan(template_id: str, record: str | None = None) -> dict:
    return {
        "shots": [
            {
                "id": "S001",
                "screen_role": "B",
                "material_type": "no-material",
                "presentation_type": "infographic",
                "semantic_structure": "comparison",
                "template_id": template_id,
                "broll_research_record": record,
            }
        ]
    }


class SelectorGateTests(unittest.TestCase):
    def test_external_candidates_block_direct_custom_build(self) -> None:
        report = select_broll_template.select(
            {"templates": []},
            "comparison",
            2,
            6000,
            "16:9",
            semantic_mapping=mapping(),
            material_type="no-material",
            presentation_type="infographic",
        )
        self.assertEqual(report["status"], "external-research-required")
        self.assertEqual(report["required_external_candidate_reviews"], 2)
        self.assertTrue(report["research_record_required_before_implementation"])
        self.assertFalse(report["custom_build_allowed"])

    def test_unfinished_local_svg_does_not_block_external_research(self) -> None:
        index = {
            "templates": [
                {
                    "id": "scratch-svg",
                    "semantic_structure": "comparison",
                    "item_range": [2, 2],
                    "duration_ms": [3000, 8000],
                    "aspect_ratios": ["16:9"],
                    "hyperframes_status": "implementation-required",
                    "source_file": "scratch.svg",
                }
            ]
        }
        report = select_broll_template.select(
            index,
            "comparison",
            2,
            6000,
            "16:9",
            semantic_mapping=mapping(),
            material_type="no-material",
            presentation_type="infographic",
        )
        self.assertEqual(report["status"], "external-research-required")
        self.assertIsNone(report["selected"])
        self.assertEqual(report["local_candidates"][0]["template_id"], "scratch-svg")
        self.assertFalse(report["local_candidates"][0]["qualified_for_reuse"])


class ResearchValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.research_dir = self.root / "planning" / "broll-research"
        self.selection_dir = self.root / "planning" / "template-selection"
        self.repo = self.root / "repositories" / "demo-repo"
        self.research_dir.mkdir(parents=True)
        self.selection_dir.mkdir(parents=True)
        (self.repo / "references").mkdir(parents=True)
        (self.repo / "demos").mkdir(parents=True)
        for name in ("a.md", "b.md"):
            (self.repo / "references" / name).write_text("shot card", encoding="utf-8")
        for name in ("a.tsx", "b.tsx"):
            (self.repo / "demos" / name).write_text("export {};", encoding="utf-8")
        selector = {
            "status": "external-research-required",
            "selection_policy": "single-source-per-shot",
            "query": {"semantic_structure": "comparison"},
            "external_candidates": [{"id": "candidate-a"}, {"id": "candidate-b"}],
            "research_record_required_before_implementation": True,
        }
        (self.selection_dir / "S001.json").write_text(
            json.dumps(selector), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_missing_research_record_blocks_custom_build(self) -> None:
        report = validate_broll_research.validate(
            plan("new:comparison"),
            {"templates": []},
            mapping(),
            self.research_dir,
            self.root / "repositories",
        )
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any("缺少外部骨架研究记录" in value for value in report["errors"]))

    def test_concrete_external_review_allows_port(self) -> None:
        record = {
            "schema_version": "0.1",
            "shot_id": "S001",
            "selector_report": "planning/template-selection/S001.json",
            "source_policy": "single-source",
            "inspected_candidates": [
                {
                    "id": "candidate-a",
                    "repository": "demo-repo",
                    "shot_card": "references/a.md",
                    "implementation_files": ["demos/a.tsx"],
                    "license": "Apache-2.0",
                    "fit": "selected",
                    "assessment": "两项并列结构适配。",
                    "rejection_reason": None,
                },
                {
                    "id": "candidate-b",
                    "repository": "demo-repo",
                    "shot_card": "references/b.md",
                    "implementation_files": ["demos/b.tsx"],
                    "license": "Apache-2.0",
                    "fit": "rejected",
                    "assessment": "分支关系过强。",
                    "rejection_reason": "当前镜头不需要汇聚。",
                },
            ],
            "decision": "port-external-skeleton",
            "selected_candidate": "candidate-a",
            "implementation_source": {"candidate_id": "candidate-a"},
            "extracted_skeleton": {
                "element_relation": "A 与 B 并列",
                "main_motion": "先建立再高亮",
                "phase_order": ["建立", "比较", "结论"],
            },
            "custom_reason": None,
            "borrowed_motion_principles": [],
        }
        (self.research_dir / "S001.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
        report = validate_broll_research.validate(
            plan("external:candidate-a", "planning/broll-research/S001.json"),
            {"templates": []},
            mapping(),
            self.research_dir,
            self.root / "repositories",
        )
        self.assertEqual(report["status"], "pass", report["errors"])

    def test_native_reuse_requires_matching_runtime(self) -> None:
        inspected = []
        for candidate in mapping()["structures"][0]["external_candidates"]:
            inspected.append({
                "id": candidate["id"], "repository": candidate["repository"],
                "shot_card": candidate["path"],
                "implementation_files": [f"demos/{Path(candidate['path']).stem}.tsx"],
                "license": candidate["license"],
                "fit": "selected" if candidate["id"] == "candidate-a" else "rejected",
                "assessment": "已核对双栏预览与源码。", "rejection_reason": "另一效果改造量较大。",
            })
        record = {
            "shot_id": "S001", "selector_report": "planning/template-selection/S001.json",
            "source_policy": "single-source", "decision": "reuse-native-source",
            "selected_candidate": "candidate-a", "inspected_candidates": inspected,
            "implementation_source": {"candidate_id": "candidate-a", "runtime": "remotion"},
            "extracted_skeleton": {"element_relation": "两项并列", "main_motion": "依次出现", "phase_order": ["建立", "比较", "落定"]},
        }
        (self.research_dir / "S001.json").write_text(json.dumps(record), encoding="utf-8")
        native_plan = plan("external:candidate-a", "planning/broll-research/S001.json")
        native_plan["shots"][0]["production"] = {"primary_tool": "remotion", "runtime_decision": {"mode": "native-reuse", "source_runtime": "remotion"}}
        report = validate_broll_research.validate(native_plan, {"templates": []}, mapping(), self.research_dir, self.root / "repositories")
        self.assertEqual(report["status"], "pass", report["errors"])
        native_plan["shots"][0]["production"]["primary_tool"] = "hyperframes"
        report = validate_broll_research.validate(native_plan, {"templates": []}, mapping(), self.research_dir, self.root / "repositories")
        self.assertEqual(report["status"], "fail")

    def test_custom_build_requires_rejections_and_borrowed_principles(self) -> None:
        record = {
            "schema_version": "0.1",
            "shot_id": "S001",
            "selector_report": "planning/template-selection/S001.json",
            "source_policy": "single-source",
            "inspected_candidates": [
                {
                    "id": candidate_id,
                    "repository": "demo-repo",
                    "shot_card": f"references/{suffix}.md",
                    "implementation_files": [f"demos/{suffix}.tsx"],
                    "license": "Apache-2.0",
                    "fit": "rejected",
                    "assessment": "已检查结构。",
                    "rejection_reason": "当前语义关系不匹配。",
                }
                for candidate_id, suffix in (("candidate-a", "a"), ("candidate-b", "b"))
            ],
            "decision": "custom-after-external-review",
            "selected_candidate": None,
            "extracted_skeleton": {
                "element_relation": "两条路径共享起点",
                "main_motion": "先分路再分别落定",
                "phase_order": ["建立起点", "分出路径", "落定差异"],
            },
            "custom_reason": "目录候选都依赖同位或等权比较，无法表达共享起点。",
            "borrowed_motion_principles": ["先快速建立差异，再保留阅读期"],
        }
        (self.research_dir / "S001.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
        report = validate_broll_research.validate(
            plan("new:shared-origin", "planning/broll-research/S001.json"),
            {"templates": []},
            mapping(),
            self.research_dir,
            self.root / "repositories",
        )
        self.assertEqual(report["status"], "pass", report["errors"])


class TemplateReadinessTests(unittest.TestCase):
    def test_static_svg_cannot_be_animation_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "templates").mkdir()
            svg = root / "graphic.svg"
            svg.write_text("<svg/>", encoding="utf-8")
            index = {
                "templates": [
                    {
                        "id": "static-svg",
                        "semantic_structure": "comparison",
                        "item_range": [2, 2],
                        "duration_ms": [3000, 8000],
                        "aspect_ratios": ["16:9"],
                        "source_file": "graphic.svg",
                        "source": {"license": "user-authored"},
                        "hyperframes_status": "animation-verified",
                    }
                ]
            }
            index_path = root / "templates" / "template-index.json"
            index_path.write_text(json.dumps(index), encoding="utf-8")
            report = validate_template_index.validate(index_path)
            self.assertEqual(report["status"], "fail")
            self.assertTrue(any("静态 SVG" in value for value in report["errors"]))


if __name__ == "__main__":
    unittest.main()
