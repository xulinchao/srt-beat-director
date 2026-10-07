from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from broll_runtime import validate_runtime_decision
from select_broll_template import select
from validate_plan import validate_broll_structure_variety
from validate_template_index import validate as validate_templates
from project_fixtures import bind_preflight


class RuntimeDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "review.json").write_text("{}", encoding="utf-8")
        self.shot = {
            "id": "S001", "screen_role": "B", "template_id": "three-card",
            "production": {
                "primary_tool": "remotion",
                "runtime_decision": {
                    "mode": "native-reuse", "source_runtime": "remotion",
                    "source_ref": "three-card", "reason": "三卡顺序与旁白适配。",
                    "alternative_reason": "原生替换内容比重新实现改动少。",
                    "evidence": ["review.json"],
                },
            },
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_native_remotion_reuse_is_allowed(self):
        self.assertEqual(validate_runtime_decision(self.shot, self.root), [])

    def test_programmatic_a_roll_keeps_runtime_evidence_requirements(self):
        self.shot["screen_role"] = "A"
        self.assertEqual(validate_runtime_decision(self.shot, self.root), [])
        del self.shot["production"]["runtime_decision"]
        self.assertTrue(validate_runtime_decision(self.shot, self.root))

    def test_h3_supports_both_roles_without_loosening_keyframe_requirements(self):
        self.shot["production"] = {
            "primary_tool": "comfyui-minimax-h3-fl2v",
            "runtime_decision": {"mode": "capability-exception", "reason": "需要首尾状态间的动作"},
            "video_generation": {
                "workflow": "workflows/minimax_h3_fl2v_turbo_native_api.json",
                "motion_prompt": "保持机位，主体完成计划中的动作",
                "first_frame": "assets/start.png", "last_frame": "assets/end.png",
            },
        }
        for role in ("A", "B"):
            with self.subTest(role=role):
                self.shot["screen_role"] = role
                self.assertEqual(validate_runtime_decision(self.shot, self.root), [])
                last = self.shot["production"]["video_generation"].pop("last_frame")
                self.assertTrue(any("last_frame" in error for error in validate_runtime_decision(self.shot, self.root)))
                self.shot["production"]["video_generation"]["last_frame"] = last

    def test_h3_scene_plan_accepts_both_roles_and_rejects_false_verified_media(self):
        (self.root / "config").mkdir()
        (self.root / "planning").mkdir()
        cues, shots = [], []
        for index, role in enumerate(("A", "B")):
            start = index * 4000
            shot_cues = [
                {"id": index * 2 + beat + 1, "start_ms": start + beat * 2000,
                 "end_ms": start + (beat + 1) * 2000, "text": f"{role}状态{beat}"}
                for beat in range(2)
            ]
            cues.extend(shot_cues)
            shots.append({
                "id": f"S{index + 1:03}", "start_ms": start, "end_ms": start + 4000,
                "cue_ids": [cue["id"] for cue in shot_cues],
                "verbatim_text": "\n".join(cue["text"] for cue in shot_cues),
                "screen_role": role, "a_view": "protagonist", "screen_subtype": "scene",
                "material_type": "no-material", "presentation_type": "scene",
                "semantic_structure": "replacement", "semantic_pattern": "state-change",
                "item_count": 1, "visual_structure": "object-state-demonstration",
                "template_id": None, "viewer_takeaway": "理解主体状态的改变",
                "visual_design": {"final_state": "新状态成立", "motion_intent": "首尾帧间完成动作"},
                "changes": [{"at_ms": cue["start_ms"], "event": cue["text"]} for cue in shot_cues],
                "narration_beats": [{"at_ms": cue["start_ms"], "cue_ids": [cue["id"]],
                    "trigger_text": cue["text"], "information_change": cue["text"],
                    "state_after": cue["text"]} for cue in shot_cues],
                "materials": [{"type": "generated-scene"}],
                "production": {"primary_tool": "comfyui-minimax-h3-fl2v", "fallback_tools": [],
                    "asset_status": "to-generate",
                    "runtime_decision": {"mode": "capability-exception", "reason": "首尾状态约束"},
                    "video_generation": {"workflow": "workflows/minimax_h3_fl2v_turbo_native_api.json",
                        "motion_prompt": "按计划改变状态", "first_frame": "assets/start.png", "last_frame": "assets/end.png"}},
            })
        documents = {
            "config/project.json": {"primary_timeline": "chatcut", "video": {"fps": 30},
                "sample": {"start_ms": 0, "end_ms": 8000}, "timeline_policy": {
                    "initial_gap": "show-first-shot", "inter_shot_gap": "hold-previous-shot", "tail_gap": "hold-last-shot"}},
            "planning/preflight.json": {"srt": {"cues": cues}, "audio": {"duration_ms": 8000}},
            "planning/content.json": {"semantic_segments": shots},
            "planning/plan.json": {"shots": shots},
        }
        bind_preflight(self.root, documents["config/project.json"], documents["planning/preflight.json"])
        for relative, data in documents.items():
            (self.root / relative).write_text(json.dumps(data), encoding="utf-8")
        command = [sys.executable, "-B", str(ROOT / "scripts/validate_plan.py"),
            "--project", str(self.root / "config/project.json"), "--preflight", str(self.root / "planning/preflight.json"),
            "--content-analysis", str(self.root / "planning/content.json"), "--visual-plan", str(self.root / "planning/plan.json"),
            "--out-dir", str(self.root / "out")]
        result = subprocess.run(command, capture_output=True)
        report = json.loads((self.root / "out/plan-validation-report.json").read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, report["errors"])
        shots[1]["material_type"] = "verified-media"
        (self.root / "planning/plan.json").write_text(json.dumps({"shots": shots}), encoding="utf-8")
        result = subprocess.run(command, capture_output=True)
        report = json.loads((self.root / "out/plan-validation-report.json").read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 2)
        self.assertTrue(any("真实证据" in error for error in report["errors"]))

    def test_missing_decision_is_blocked(self):
        del self.shot["production"]["runtime_decision"]
        self.assertTrue(validate_runtime_decision(self.shot, self.root))

    def test_new_creation_defaults_to_hyperframes(self):
        self.shot["production"]["runtime_decision"] = {
            "mode": "new-default", "reason": "没有合格的现成实现。",
        }
        self.assertTrue(validate_runtime_decision(self.shot, self.root))
        self.shot["production"]["primary_tool"] = "hyperframes"
        self.assertEqual(validate_runtime_decision(self.shot, self.root), [])

    def test_switch_cannot_masquerade_as_native_reuse(self):
        self.shot["production"]["primary_tool"] = "hyperframes"
        self.assertTrue(validate_runtime_decision(self.shot, self.root))
        self.shot["production"]["runtime_decision"]["mode"] = "port"
        self.assertEqual(validate_runtime_decision(self.shot, self.root), [])

    def test_nondefault_requires_reason_and_existing_evidence(self):
        decision = self.shot["production"]["runtime_decision"]
        decision["alternative_reason"] = ""
        decision["evidence"] = ["missing.json"]
        errors = validate_runtime_decision(self.shot, self.root)
        self.assertTrue(any("alternative_reason" in error for error in errors))
        self.assertTrue(any("missing.json" in error for error in errors))

    def test_source_must_match_selected_template(self):
        index = {"templates": [{"id": "three-card", "runtime": "hyperframes"}]}
        self.assertTrue(validate_runtime_decision(self.shot, self.root, index))
        self.shot["production"]["runtime_decision"]["source_ref"] = "another-card"
        self.assertTrue(validate_runtime_decision(self.shot, self.root))

    def test_user_request_requires_recorded_instruction(self):
        decision = self.shot["production"]["runtime_decision"]
        decision["mode"] = "user-request"
        self.assertTrue(validate_runtime_decision(self.shot, self.root))
        decision["user_request"] = "这个镜头用 Remotion。"
        self.assertEqual(validate_runtime_decision(self.shot, self.root), [])

    def test_h3_reference_workflow_requires_references_not_first_frame(self):
        self.shot["production"] = {
            "primary_tool": "comfyui-minimax-h3-r2v",
            "runtime_decision": {"mode": "capability-exception", "reason": "需要参考驱动的连续动作"},
            "video_generation": {
                "workflow": "workflows/minimax_h3_r2v_turbo_api.json",
                "motion_prompt": "人物走向桌边",
                "reference_frames": ["assets/person.png", "assets/scene.png"],
            },
        }
        self.assertEqual(validate_runtime_decision(self.shot, self.root), [])
        self.shot["production"]["video_generation"]["reference_frames"].pop()
        self.assertTrue(any("2 张参考图" in error for error in validate_runtime_decision(self.shot, self.root)))

    def test_qwen21_keyframe_edit_is_checked_as_local_image_workflow(self):
        self.shot["production"] = {
            "primary_tool": "comfyui-qwen21-edit",
            "runtime_decision": {"mode": "user-request", "reason": "用户更改出图要求", "user_request": "本次改用本地 Qwen 编辑。"},
            "image_generation": {"workflow": "workflows/qwen_image_2_1_edit_keyframe_api.json", "prompt": "保持人物，只改变手势"},
        }
        self.assertEqual(validate_runtime_decision(self.shot, self.root), [])
        del self.shot["production"]["image_generation"]["prompt"]
        self.assertTrue(any("缺少 prompt" in error for error in validate_runtime_decision(self.shot, self.root)))

    def test_image_outage_cannot_fallback_or_claim_capability_exception(self):
        for runtime in ("comfyui-qwen21-edit", "comfyui-z-image-turbo", "chatcut-image"):
            for mode in ("fallback", "capability-exception", "user-request"):
                with self.subTest(runtime=runtime, mode=mode):
                    self.shot["production"] = {
                        "primary_tool": runtime,
                        "runtime_decision": {"mode": mode, "reason": "内置工具不可用", "source_runtime": "gpt-image2"},
                        "image_generation": {"workflow": "local.json", "prompt": "画面"},
                    }
                    self.assertTrue(any("中断整个视频工作流" in e for e in validate_runtime_decision(self.shot, self.root)))

    def test_builtin_image_routes_have_no_automatic_fallback(self):
        for runtime in ("gpt-image2", "image_gen"):
            self.shot["production"] = {"primary_tool": runtime, "fallback_tools": []}
            self.assertEqual(validate_runtime_decision(self.shot, self.root), [])
            for fallback in ("comfyui-qwen21-t2i", "chatcut-image", "existing-media"):
                with self.subTest(runtime=runtime, fallback=fallback):
                    self.shot["production"]["fallback_tools"] = [fallback]
                    self.assertTrue(validate_runtime_decision(self.shot, self.root))

    def test_video_route_cannot_hide_image_fallback(self):
        self.shot["production"] = {"primary_tool": "chatcut-video", "fallback_tools": ["chatcut-image"]}
        self.assertTrue(validate_runtime_decision(self.shot, self.root))

    def test_plain_crop_remains_available_without_image_generation(self):
        self.shot["production"] = {
            "primary_tool": "comfyui-crop-image",
            "runtime_decision": {"mode": "capability-exception", "reason": "裁切已有图片"},
            "image_generation": {"workflow": "crop_image.json"},
        }
        self.assertEqual(validate_runtime_decision(self.shot, self.root), [])

    def test_plan_cli_accepts_mixed_runtimes_and_rejects_missing_decision(self):
        (self.root / "config").mkdir()
        (self.root / "planning").mkdir()
        cues, shots = [], []
        for index, runtime in enumerate(("hyperframes", "remotion")):
            start, end = index * 2000, (index + 1) * 2000
            cue = {"id": index + 1, "start_ms": start, "end_ms": end, "text": f"第{index + 1}点"}
            cues.append(cue)
            shots.append({
                "id": f"S{index + 1:03}", "start_ms": start, "end_ms": end,
                "cue_ids": [cue["id"]], "verbatim_text": cue["text"],
                "screen_role": "B", "screen_subtype": "diagram",
                "material_type": "no-material", "presentation_type": "infographic",
                "semantic_structure": "expansion", "item_count": 1,
                "semantic_pattern": f"pattern-{runtime}",
                "visual_structure": f"structure-{runtime}",
                "template_id": f"template-{runtime}", "viewer_takeaway": "理解当前项目",
                "visual_design": {"composition": f"composition-{runtime}", "final_state": "图形和短标签可见"},
                "changes": [{"at_ms": start, "event": "建立当前信息"}],
                "narration_beats": [{"at_ms": start, "cue_ids": [cue["id"]], "trigger_text": cue["text"], "information_change": "新增信息", "state_after": "关系成立"}],
                "materials": [{"type": "no-material"}],
                "production": {
                    "primary_tool": runtime, "fallback_tools": [], "asset_status": "to-generate",
                    "runtime_decision": {
                        "mode": "native-reuse", "source_runtime": runtime,
                        "source_ref": f"template-{runtime}", "reason": "已检查候选",
                        "alternative_reason": "原生改造量更小", "evidence": ["review.json"],
                    },
                },
            })
        documents = {
            "config/project.json": {"video": {"fps": 30}, "sample": {"start_ms": 0, "end_ms": 4000}, "timeline_policy": {"initial_gap": "show-first-shot", "inter_shot_gap": "hold-previous-shot", "tail_gap": "hold-last-shot"}},
            "planning/preflight.json": {"srt": {"cues": cues}, "audio": {"duration_ms": 4000}},
            "planning/content.json": {"semantic_segments": shots},
            "planning/plan.json": {"shots": shots},
            "planning/templates.json": {"templates": [{"id": f"template-{runtime}", "runtime": runtime, "animation_status": "animation-verified"} for runtime in ("hyperframes", "remotion")]},
        }
        bind_preflight(self.root, documents["config/project.json"], documents["planning/preflight.json"])
        for relative, data in documents.items():
            (self.root / relative).write_text(json.dumps(data), encoding="utf-8")
        command = [sys.executable, "-B", str(ROOT / "scripts/validate_plan.py"), "--project", str(self.root / "config/project.json"), "--preflight", str(self.root / "planning/preflight.json"), "--content-analysis", str(self.root / "planning/content.json"), "--visual-plan", str(self.root / "planning/plan.json"), "--template-index", str(self.root / "planning/templates.json"), "--out-dir", str(self.root / "out")]
        result = subprocess.run(command, capture_output=True)
        report = json.loads((self.root / "out/plan-validation-report.json").read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, report["errors"])
        del shots[1]["production"]["runtime_decision"]
        (self.root / "planning/plan.json").write_text(json.dumps({"shots": shots}), encoding="utf-8")
        result = subprocess.run(command, capture_output=True)
        report = json.loads((self.root / "out/plan-validation-report.json").read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 2)
        self.assertTrue(any("S002 runtime_decision" in error for error in report["errors"]))

    def test_nearby_broll_structure_reuse_warns_without_rejection(self):
        shots = [
            {"id": "S001", "screen_role": "B", "visual_structure": "document-assembly", "semantic_pattern": "assemble", "template_id": "one", "visual_design": {"composition": "desk"}},
            {"id": "S002", "screen_role": "A"},
            {"id": "S003", "screen_role": "B", "visual_structure": "question-radar", "semantic_pattern": "radar", "template_id": "two", "visual_design": {"composition": "radial"}},
            {"id": "S004", "screen_role": "B", "visual_structure": "document-assembly", "semantic_pattern": "assemble-new-name", "template_id": "three", "visual_design": {"composition": "new-desk"}},
        ]
        errors = []
        warnings = []
        validate_broll_structure_variety(shots, [], errors, warnings)
        self.assertEqual(errors, [])
        self.assertTrue(any("S004" in warning and "S001" in warning for warning in warnings))

    def test_structure_reuse_requires_complete_exception(self):
        shots = [
            {"id": "S001", "screen_role": "B", "visual_structure": "learning-loop", "visual_design": {}},
            {"id": "S002", "screen_role": "B", "visual_structure": "learning-loop", "visual_design": {}},
        ]
        errors = []
        warnings = []
        validate_broll_structure_variety(
            shots,
            [{"shot_id": "S002", "compared_shot_id": "S001", "semantic_reason": "章节回顾", "visible_difference": "布局不变，回顾已讲的完整循环"}],
            errors,
            warnings,
        )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_generic_structure_name_is_rejected(self):
        errors = []
        validate_broll_structure_variety(
            [{"id": "S001", "screen_role": "B", "visual_structure": "三卡", "visual_design": {}}],
            [],
            errors,
        )
        self.assertTrue(any("过于笼统" in error for error in errors))


class RuntimeTemplateTests(unittest.TestCase):
    def template(self, runtime="remotion"):
        return {
            "id": "three-card", "semantic_structure": "expansion",
            "semantic_pattern": "three-card-reveal", "item_range": [3, 3],
            "duration_ms": [3000, 9000], "aspect_ratios": ["16:9"],
            "runtime": runtime, "animation_status": "animation-verified",
            "preview": "preview.mp4", "source_file": "scene.tsx",
            "source": {"license": "Apache-2.0", "original_framework": "Remotion"},
            "animation_phases": ["第一点", "第二点", "第三点"],
        }

    def test_remotion_template_can_be_registered_and_selected(self):
        template = self.template()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "templates").mkdir()
            (root / "scene.tsx").write_text("export {};", encoding="utf-8")
            index_path = root / "templates" / "template-index.json"
            index = {"templates": [template]}
            index_path.write_text(json.dumps(index), encoding="utf-8")
            self.assertEqual(validate_templates(index_path)["status"], "pass")
            report = select(index, "expansion", 3, 6000, "16:9")
            self.assertEqual(report["selected"]["runtime"], "remotion")
            self.assertTrue(report["selection_is_provisional"])

    def test_unverified_remotion_stays_a_research_candidate(self):
        template = self.template()
        template["animation_status"] = "implementation-required"
        report = select({"templates": [template]}, "expansion", 3, 6000, "16:9")
        self.assertIsNone(report["selected"])

    def test_legacy_hyperframes_and_precise_pattern_are_preserved(self):
        legacy = self.template()
        legacy.pop("runtime")
        legacy["hyperframes_status"] = legacy.pop("animation_status")
        legacy["id"] = "legacy-hf"
        generic = self.template()
        generic["semantic_pattern"] = "other-pattern"
        report = select({"templates": [generic, legacy]}, "expansion", 3, 6000, "16:9", semantic_pattern="three-card-reveal")
        self.assertEqual(report["selected"]["template_id"], "legacy-hf")
        self.assertEqual(report["selected"]["runtime"], "hyperframes")


if __name__ == "__main__":
    unittest.main()
