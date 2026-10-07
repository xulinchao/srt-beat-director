from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from broll_expression import MATCHING_POLICY
from select_broll_template import select
from validate_broll_research import validate


def brief():
    return {'subjects': ['两块木板'], 'element_relation': '位置固定，文字附着板面',
            'main_motion': '翻面替换文字', 'phase_order': ['旧内容', '翻面', '新内容'],
            'invariants': ['位置保持'], 'motion_tags': ['content-flip'],
            'search_queries': ['flip cards to replace text', 'front back rotation reveal']}


def template(id, structure, tags):
    # Unit fixtures exercise routing; these are not certified production assets.
    return {'id': id, 'semantic_structure': structure, 'motion_tags': tags,
            'item_range': [2, 2], 'duration_ms': [3000, 8000], 'aspect_ratios': ['16:9'],
            'runtime': 'remotion', 'animation_status': 'animation-verified',
            'source_file': 'fixture.tsx', 'preview': 'fixture.mp4',
            'animation_phases': ['old', 'flip', 'new']}


class ExpressionSelectorTests(unittest.TestCase):
    def choose(self, index, **kwargs):
        return select(index, 'replacement', 2, 6000, '16:9', expression_brief=brief(), **kwargs)

    def test_motion_match_can_cross_semantic_categories(self):
        index = {'templates': [template('same-category', 'replacement', ['shape-morph']),
                               template('right-motion', 'comparison', ['content-flip'])]}
        result = self.choose(index)
        self.assertEqual(result['selected']['template_id'], 'right-motion')

    def test_coarse_match_without_motion_is_not_direct_reuse(self):
        result = self.choose({'templates': [template('plain', 'replacement', [])]})
        self.assertIsNone(result['selected'])
        self.assertTrue(result['research_record_required_before_implementation'])

    def test_capacity_miss_keeps_motion_reference_without_certifying_adaptation(self):
        item = template('longer', 'comparison', ['content-flip'])
        item['duration_ms'] = [10000, 15000]
        result = self.choose({'templates': [item]})
        self.assertIsNone(result['selected'])
        self.assertTrue(result['local_candidates'][0]['adaptation_required'])

    def test_cross_category_external_candidate_is_returned(self):
        mapping = {'structures': [{'id': 'replacement', 'external_candidates': []},
                                   {'id': 'comparison', 'external_candidates': [
                                       {'id': 'flip', 'motion_tags': ['content-flip']}]}]}
        result = self.choose({'templates': []}, semantic_mapping=mapping)
        self.assertEqual(result['external_candidates'][0]['id'], 'flip')

    def test_semantic_only_candidate_is_not_presented_as_motion_match(self):
        mapping = {'structures': [{'id': 'replacement', 'external_candidates': [
            {'id': 'unrelated', 'motion_tags': ['quantity-count']}]}]}
        result = self.choose({'templates': []}, semantic_mapping=mapping)
        self.assertEqual(result['external_candidates'][0]['match_basis'], 'semantic-only')
        self.assertEqual(result['external_candidates'][0]['matched_motion_tags'], [])
        self.assertTrue(any('动作标签命中' in warning for warning in result['selection_warnings']))

    def test_empty_catalog_never_authorizes_direct_custom(self):
        result = self.choose({'templates': []})
        self.assertFalse(result['custom_build_allowed'])
        self.assertTrue(result['research_record_required_before_implementation'])
        self.assertTrue(result['expanded_search_required_before_custom'])

    def test_incomplete_expression_fails(self):
        with self.assertRaises(ValueError):
            select({'templates': []}, 'replacement', 2, 6000, '16:9', expression_brief={})


class ExpressionResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.research = self.root / 'planning/broll-research'
        self.selection = self.root / 'planning/template-selection'
        self.repo = self.root / 'repositories/demo'
        for directory in [self.research, self.selection, self.repo / 'refs', self.repo / 'src']:
            directory.mkdir(parents=True, exist_ok=True)
        (self.repo / 'refs/flip.md').write_text('unit fixture, not a real source')
        (self.repo / 'src/flip.tsx').write_text('unit fixture')
        (self.research / 'preview.png').write_bytes(b'unit fixture, not a rendered preview')
        self.plan = {'broll_matching_policy': MATCHING_POLICY, 'shots': [
            {'id': 'S001', 'screen_role': 'B', 'material_type': 'no-material',
             'presentation_type': 'infographic', 'semantic_structure': 'replacement',
             'template_id': 'new:custom'}]}
        self.selector = select({'templates': []}, 'replacement', 2, 6000, '16:9', expression_brief=brief())
        self.record = {'schema_version': '0.2', 'shot_id': 'S001',
                       'selector_report': 'planning/template-selection/S001.json',
                       'expression_brief': brief(), 'source_policy': 'single-source',
                       'decision': 'custom-after-external-review', 'selected_candidate': None,
                       'inspected_candidates': [], 'custom_reason': 'No motion fit after actual expanded search',
                       'borrowed_motion_principles': ['readable old/change/new states'],
                       'extracted_skeleton': {'element_relation': 'fixed position', 'main_motion': 'flip',
                                              'phase_order': ['old', 'change', 'new']}}

    def run_validation(self, mapping=None, save_record=True):
        (self.selection / 'S001.json').write_text(json.dumps(self.selector), encoding='utf-8')
        if save_record:
            (self.research / 'S001.json').write_text(json.dumps(self.record), encoding='utf-8')
        return validate(self.plan, {'templates': []}, mapping or {'structures': []}, self.research, self.root / 'repositories')

    def expanded_search(self):
        return [{'source': 'hyperframes-catalog', 'query': 'flip cards to replace text',
                 'outcome': 'unit fixture: no candidate', 'candidate_ids': []},
                {'source': 'remotion-repository', 'query': 'front back rotation reveal',
                 'outcome': 'unit fixture: no suitable source', 'candidate_ids': []}]

    def test_empty_catalog_still_requires_research(self):
        result = self.run_validation(save_record=False)
        self.assertEqual(result['status'], 'fail')

    def test_custom_without_expanded_search_is_blocked(self):
        result = self.run_validation()
        self.assertTrue(any('expanded_search' in e for e in result['errors']))

    def test_custom_with_one_source_is_blocked(self):
        self.record['expanded_search'] = self.expanded_search()
        self.record['expanded_search'][1]['source'] = 'hyperframes-catalog'
        result = self.run_validation()
        self.assertTrue(any('两个搜索来源' in e for e in result['errors']))

    def test_custom_after_expanded_search_can_pass_protocol(self):
        self.record['expanded_search'] = self.expanded_search()
        result = self.run_validation()
        self.assertEqual(result['status'], 'pass', result['errors'])

    def selected_record(self):
        discovered = {'id': 'newly-found-flip', 'repository': 'demo', 'path': 'refs/flip.md',
                      'license': 'Apache-2.0', 'status': 'port-required',
                      'source_url': 'https://example.com/unit-fixture'}
        self.record.update({'decision': 'study-and-reimplement', 'selected_candidate': discovered['id'],
                            'implementation_source': {'candidate_id': discovered['id']},
                            'discovered_candidates': [discovered],
                            'inspected_candidates': [{'id': discovered['id'], 'repository': 'demo',
                                'shot_card': 'refs/flip.md', 'implementation_files': ['src/flip.tsx'],
                                'license': 'Apache-2.0', 'fit': 'selected', 'assessment': 'unit fixture: motion fit',
                                'preview_evidence': {'status': 'inspected', 'artifact': 'planning/broll-research/preview.png'}}]})
        self.plan['shots'][0]['template_id'] = 'external:newly-found-flip'

    def test_unlisted_source_with_files_and_preview_can_pass(self):
        self.selected_record()
        result = self.run_validation()
        self.assertEqual(result['status'], 'pass', result['errors'])

    def test_selected_source_without_preview_is_blocked(self):
        self.selected_record()
        del self.record['inspected_candidates'][0]['preview_evidence']
        result = self.run_validation()
        self.assertTrue(any('实际预览' in e for e in result['errors']))

    def test_discovered_source_cannot_escape_repository(self):
        self.selected_record()
        self.record['discovered_candidates'][0]['path'] = '../outside.md'
        self.record['inspected_candidates'][0]['shot_card'] = '../outside.md'
        result = self.run_validation()
        self.assertTrue(any('路径越界' in e for e in result['errors']))

    def test_expression_cannot_be_changed_between_selection_and_research(self):
        self.record['expanded_search'] = self.expanded_search()
        self.record['expression_brief'] = copy.deepcopy(brief())
        self.record['expression_brief']['main_motion'] = 'unrelated motion'
        result = self.run_validation()
        self.assertTrue(any('必须与选择报告一致' in e for e in result['errors']))

    def test_unknown_policy_is_not_silently_downgraded(self):
        self.plan['broll_matching_policy'] = 'unknown'
        self.record['expanded_search'] = self.expanded_search()
        result = self.run_validation()
        self.assertEqual(result['status'], 'fail')

    def test_search_result_cannot_be_ignored_before_custom(self):
        self.record['expanded_search'] = self.expanded_search()
        self.record['expanded_search'][0]['candidate_ids'] = ['not-assessed']
        result = self.run_validation()
        self.assertTrue(any('尚未评估' in e for e in result['errors']))

    def test_registered_source_found_in_expanded_search_can_be_selected(self):
        self.selected_record()
        source = self.record.pop('discovered_candidates')[0]
        self.record['expanded_search'] = self.expanded_search()
        self.record['expanded_search'][0]['candidate_ids'] = [source['id']]
        mapping = {'structures': [{'id': 'comparison', 'external_candidates': [source]}]}
        result = self.run_validation(mapping=mapping)
        self.assertEqual(result['status'], 'pass', result['errors'])

    def test_certified_local_id_cannot_bypass_expression_selection(self):
        item = template('local-flip', 'replacement', ['content-flip'])
        self.plan['shots'][0]['template_id'] = item['id']
        result = validate(self.plan, {'templates': [item]}, {'structures': []},
                          self.research, self.root / 'repositories')
        self.assertTrue(any('本地认证 ID 不能绕过' in e for e in result['errors']))

    def test_certified_local_with_current_expression_report_passes(self):
        item = template('local-flip', 'replacement', ['content-flip'])
        self.plan['shots'][0]['template_id'] = item['id']
        selector = select({'templates': [item]}, 'replacement', 2, 6000, '16:9', expression_brief=brief())
        (self.selection / 'S001.json').write_text(json.dumps(selector), encoding='utf-8')
        result = validate(self.plan, {'templates': [item]}, {'structures': []},
                          self.research, self.root / 'repositories')
        self.assertEqual(result['status'], 'pass', result['errors'])


class ReferenceConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repositories = self.root / 'repositories'
        self.component = self.repositories / 'hyperframes/registry/components/content-flip'
        self.component.mkdir(parents=True)
        (self.component / 'registry-item.json').write_text(json.dumps({
            'name': 'content-flip', 'description': 'Flip content to reveal replacement text',
            'tags': ['content-flip']}), encoding='utf-8')
        (self.component / 'demo.html').write_text('<html>preview fixture</html>', encoding='utf-8')
        (self.repositories / 'hyperframes/LICENSE').write_text('unit fixture license', encoding='utf-8')
        self.selection = self.root / 'planning/template-selection'
        self.research = self.root / 'planning/broll-research'
        self.selection.mkdir(parents=True)
        self.research.mkdir(parents=True)
        (self.root / 'config').mkdir()
        (self.root / 'config/project.json').write_text(json.dumps({
            'repositories_root': self.repositories.as_posix()}), encoding='utf-8')
        (self.root / 'planning/preview.mp4').write_bytes(b'unit fixture preview')
        self.shot = {'id': 'S001', 'screen_role': 'B', 'material_type': 'no-material',
                     'presentation_type': 'infographic', 'semantic_structure': 'replacement',
                     'item_count': 2, 'template_id': 'external:content-flip',
                     'production': {'primary_tool': 'hyperframes'}}
        self.report = select({'templates': []}, 'replacement', 2, 6000, '16:9',
                             expression_brief=brief(), repositories_root=self.repositories)
        candidate = next(item for item in self.report['reference_candidates'] if item['id'] == 'content-flip')
        self.report['reference_confirmation'] = {
            'confirmed_source_id': candidate['id'],
            'confirmed_file_path': candidate['reference_path'],
            'preview_path': 'planning/preview.mp4',
            'motion_adaptation_reason': 'A flip replaces the text at the same position',
            'phase_adaptation_reason': 'Old text, flip, new text remain readable',
            'native_framework': candidate['framework'],
            'license_basis': {'license_id': 'fixture-license', 'evidence_path': 'LICENSE'},
        }

    def check(self):
        (self.selection / 'S001.json').write_text(json.dumps(self.report), encoding='utf-8')
        plan = {'broll_matching_policy': MATCHING_POLICY, 'shots': [self.shot]}
        return validate(plan, {'templates': []}, {'structures': []}, self.research, self.repositories)

    def test_recall_does_not_auto_select_a_reference(self):
        self.assertEqual(self.report['status'], 'candidates-recalled')
        self.assertIsNone(self.report['selected'])
        self.assertEqual(self.report['reference_candidates'][0]['framework'], 'hyperframes')

    def test_confirmed_reference_passes_without_external_research_record(self):
        result = self.check()
        self.assertEqual(result['status'], 'pass', result['errors'])

    def test_unconfirmed_reference_is_blocked(self):
        self.report['reference_confirmation'] = None
        self.assertTrue(any('尚未确认' in error for error in self.check()['errors']))

    def test_known_invariant_conflict_cannot_use_reference_fast_path(self):
        self.report['expression_brief']['requirements'] = {'preserves_content': True}
        self.report['reference_candidates'][0]['capabilities'] = {'preserves_content': False}
        self.assertTrue(any('显式运动约束冲突' in error for error in self.check()['errors']))

    def test_mismatched_plan_id_is_blocked(self):
        self.shot['template_id'] = 'external:other'
        self.assertTrue(any('template_id' in error for error in self.check()['errors']))

    def test_missing_or_outside_source_is_blocked(self):
        (self.component / 'demo.html').unlink()
        self.assertTrue(any('参考文件不存在' in error for error in self.check()['errors']))
        outside = self.root / 'other.html'
        outside.write_text('outside', encoding='utf-8')
        self.report['reference_candidates'][0]['reference_path'] = outside.as_posix()
        self.report['reference_confirmation']['confirmed_file_path'] = outside.as_posix()
        self.assertTrue(any('不在配置的来源仓库' in error for error in self.check()['errors']))

    def test_missing_preview_and_wrong_framework_are_blocked(self):
        self.report['reference_confirmation']['preview_path'] = 'planning/missing.mp4'
        self.report['reference_confirmation']['native_framework'] = 'remotion'
        errors = self.check()['errors']
        self.assertTrue(any('预览证据文件不存在' in error for error in errors))
        self.assertTrue(any('native_framework' in error for error in errors))

    def test_new_template_cannot_use_reference_confirmation(self):
        self.shot['template_id'] = 'new:custom'
        self.assertTrue(any('缺少外部骨架研究记录' in error for error in self.check()['errors']))

    def test_custom_after_recalled_candidates_needs_reference_rejection(self):
        self.shot['template_id'] = 'new:custom'
        record = {'schema_version': '0.2', 'shot_id': 'S001',
                  'selector_report': 'planning/template-selection/S001.json',
                  'expression_brief': brief(), 'source_policy': 'single-source',
                  'decision': 'custom-after-external-review', 'selected_candidate': None,
                  'inspected_candidates': [], 'custom_reason': 'No usable reference motion',
                  'borrowed_motion_principles': ['Keep the final state readable'],
                  'extracted_skeleton': {'element_relation': 'fixed position',
                                         'main_motion': 'replace content',
                                         'phase_order': ['old', 'change', 'new']},
                  'expanded_search': [
                      {'source': 'source-one', 'query': 'flip content', 'outcome': 'no fit', 'candidate_ids': []},
                      {'source': 'source-two', 'query': 'rotate panel', 'outcome': 'no fit', 'candidate_ids': []},
                  ]}
        (self.research / 'S001.json').write_text(json.dumps(record), encoding='utf-8')
        self.assertTrue(any('参考仓库候选及拒绝理由' in error for error in self.check()['errors']))
        record['reference_candidate_reviews'] = [
            {'candidate_id': 'content-flip', 'rejection_reason': 'The preview has too little time for the new text'}]
        (self.research / 'S001.json').write_text(json.dumps(record), encoding='utf-8')
        self.assertEqual(self.check()['status'], 'pass', self.check()['errors'])

    def test_license_basis_must_point_to_existing_source_file(self):
        self.report['reference_confirmation']['license_basis']['evidence_path'] = '../unrelated.txt'
        self.assertTrue(any('许可证依据文件不存在' in error for error in self.check()['errors']))

    def test_motion_canvas_is_not_mislabeled_hyperframes(self):
        scene = self.repositories / 'motion-canvas/packages/examples/src/scene.ts'
        scene.parent.mkdir(parents=True)
        scene.write_text('// Flip content between two states\nexport default {}', encoding='utf-8')
        confirmation = self.report['reference_confirmation']
        self.report = select({'templates': []}, 'replacement', 2, 6000, '16:9',
                             expression_brief=brief(), repositories_root=self.repositories)
        candidate = next(item for item in self.report['reference_candidates']
                         if item['reference_source'] == 'motion-canvas')
        self.assertEqual(candidate['framework'], 'motion-canvas')
        self.report['reference_confirmation'] = confirmation
        confirmation.update({
            'confirmed_source_id': candidate['id'], 'confirmed_file_path': candidate['reference_path'],
            'native_framework': 'motion-canvas'})
        self.shot['template_id'] = f"external:{candidate['id']}"
        self.assertTrue(any('尚无原生制作路由' in error for error in self.check()['errors']))

    def test_plan_cli_rejects_unconfirmed_reference_even_with_record_path_claim(self):
        cue = {'id': 1, 'start_ms': 0, 'end_ms': 2000, 'text': '翻面替换'}
        self.shot.update({
            'start_ms': 0, 'end_ms': 2000, 'cue_ids': [1], 'verbatim_text': cue['text'],
            'screen_subtype': 'diagram', 'semantic_pattern': 'content-flip',
            'visual_structure': 'same-position-flip', 'viewer_takeaway': '旧信息变为新信息',
            'visual_design': {'composition': 'two boards', 'final_state': '新文字可读'},
            'changes': [{'at_ms': 0, 'event': '建立旧状态'}],
            'narration_beats': [{'at_ms': 0, 'cue_ids': [1], 'trigger_text': cue['text'],
                                 'information_change': '旧信息出现', 'state_after': '旧信息可读'}],
            'materials': [{'type': 'no-material'}],
            'broll_research_record': 'planning/broll-research/S001.json',
        })
        self.report['query']['duration_ms'] = 2000
        (self.root / 'evidence.json').write_text('{}', encoding='utf-8')
        self.shot['production'].update({
            'fallback_tools': [], 'asset_status': 'to-generate',
            'runtime_decision': {'mode': 'native-reuse', 'source_runtime': 'hyperframes',
                'source_ref': self.shot['template_id'], 'reason': '已看过参考预览',
                'alternative_reason': '原生实现保留动作', 'evidence': ['evidence.json']},
        })
        project = {'repositories_root': self.repositories.as_posix(), 'video': {'fps': 30},
                   'sample': {'start_ms': 0, 'end_ms': 2000},
                   'timeline_policy': {'initial_gap': 'show-first-shot',
                                       'inter_shot_gap': 'hold-previous-shot',
                                       'tail_gap': 'hold-last-shot'}}
        (self.root / 'config/project.json').write_text(json.dumps(project), encoding='utf-8')
        fixtures = {
            'planning/preflight.json': {'srt': {'cues': [cue]}, 'audio': {'duration_ms': 2000}},
            'planning/content.json': {'semantic_segments': [self.shot]},
            'planning/plan.json': {'broll_matching_policy': MATCHING_POLICY, 'shots': [self.shot]},
            'planning/templates.json': {'templates': []},
        }
        from project_fixtures import bind_preflight
        bind_preflight(self.root, project, fixtures['planning/preflight.json'])
        (self.root / 'config/project.json').write_text(json.dumps(project), encoding='utf-8')
        for relative, value in fixtures.items():
            (self.root / relative).write_text(json.dumps(value), encoding='utf-8')
        command = [sys.executable, '-B', str(ROOT / 'scripts/validate_plan.py'),
                   '--project', str(self.root / 'config/project.json'),
                   '--preflight', str(self.root / 'planning/preflight.json'),
                   '--content-analysis', str(self.root / 'planning/content.json'),
                   '--visual-plan', str(self.root / 'planning/plan.json'),
                   '--template-index', str(self.root / 'planning/templates.json'),
                   '--out-dir', str(self.root / 'out')]
        self.report['reference_confirmation'] = None
        (self.selection / 'S001.json').write_text(json.dumps(self.report), encoding='utf-8')
        result = subprocess.run(command, capture_output=True)
        report = json.loads((self.root / 'out/plan-validation-report.json').read_text(encoding='utf-8'))
        self.assertEqual(result.returncode, 2)
        self.assertTrue(any('尚未确认' in error for error in report['errors']))
        self.shot['broll_research_record'] = None
        (self.root / 'planning/plan.json').write_text(json.dumps({
            'broll_matching_policy': MATCHING_POLICY, 'shots': [self.shot]}), encoding='utf-8')
        self.report['reference_confirmation'] = {
            'confirmed_source_id': 'content-flip',
            'confirmed_file_path': self.report['reference_candidates'][0]['reference_path'],
            'preview_path': 'planning/preview.mp4',
            'motion_adaptation_reason': 'Flip replaces content at the same position',
            'phase_adaptation_reason': 'Old, flip and new states remain readable',
            'native_framework': 'hyperframes',
            'license_basis': {'license_id': 'fixture-license', 'evidence_path': 'LICENSE'},
        }
        (self.selection / 'S001.json').write_text(json.dumps(self.report), encoding='utf-8')
        result = subprocess.run(command, capture_output=True)
        report = json.loads((self.root / 'out/plan-validation-report.json').read_text(encoding='utf-8'))
        self.assertEqual(result.returncode, 0, report['errors'])


class ReferenceMatchBasisTests(unittest.TestCase):
    """(m.1)/(m.2) 参考仓库候选：纯类目命中不得被当作 matched。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shots = self.root / 'repositories/video-shotcraft/shots/replacement'
        shots.mkdir(parents=True)
        (shots / 'content-flip-card.md').write_text(
            '---\n'
            'description: flip cards to replace text with a front back rotation\n'
            '---\n'
            '两块板翻面替换文字的镜头卡。\n',
            encoding='utf-8')
        (shots / 'zoom-out-reveal.md').write_text(
            '---\n'
            'description: 镜头逐渐拉远，展示整体版面与空间关系\n'
            '---\n'
            '仅分类相同的拉远镜头。\n',
            encoding='utf-8')

    def recall(self):
        report = select({'templates': []}, 'replacement', 2, 6000, '16:9',
                        expression_brief=brief(), repositories_root=self.root / 'repositories')
        return report, {item['id']: item for item in report['reference_candidates']}

    def test_category_only_candidate_is_not_matched(self):
        _, by_id = self.recall()
        zoom = by_id['zoom-out-reveal']
        # The filename shares "reveal", but this is lexical exploration,
        # not an explicit motion match or a candidate ready for reuse.
        self.assertEqual(zoom['match_basis'], 'lexical')
        self.assertEqual(zoom['matched_motion_tags'], [])
        self.assertEqual(zoom['core_motion_overlap'], [])
        self.assertFalse(zoom['matched'])

    def test_flip_is_not_mistaken_for_zoom_out_reveal(self):
        report, by_id = self.recall()
        self.assertEqual(report['status'], 'candidates-recalled')
        self.assertTrue(by_id['content-flip-card']['matched'])
        self.assertFalse(by_id['zoom-out-reveal']['matched'])
        self.assertIsNone(report['selected'])


if __name__ == '__main__':
    unittest.main()
