import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from height_choice import build_choice, configure_profile, save_local_profile
from height_policy_core import evaluate_height_policy, validate_height_choice
from auto_workflow import ensure_height_choice_before_audit, verify_height_report_matches_decision


class HeightChoiceTests(unittest.TestCase):
    def human(self):
        return dict(model_type='humanoid', exclude_accessories_from_height=True,
                    agent_reference_body_height=100)

    def nonhuman(self):
        return dict(model_type='nonhumanoid', exclude_accessories_from_height=True)

    def test_requires_user_choice_before_measurement(self):
        result = evaluate_height_policy(self.human(), 100)
        self.assertEqual(result['status'], 'PENDING')
        self.assertIn('NEEDS_HEIGHT_CHOICE', result['reason'])

    def test_user_can_match_default_agent(self):
        p, s = build_choice(self.human(), mode='match_agent', confirmed=True)
        self.assertEqual(s['target_body_height'], 100)
        self.assertEqual(evaluate_height_policy(p, 100)['status'], 'PASS')

    def test_custom_target_can_be_different_from_default_agent(self):
        p, s = build_choice(self.human(), mode='custom_target', target_height=120, confirmed=True)
        self.assertEqual(s['target_body_height'], 120)
        self.assertEqual(evaluate_height_policy(p, 120)['status'], 'PASS')
        self.assertEqual(evaluate_height_policy(p, 100)['status'], 'FAIL')

    def test_uniform_scale_has_no_limb_scaling(self):
        p, s = build_choice(self.human(), mode='uniform_scale', original_body_height=100,
                            uniform_scale=1.2, confirmed=True)
        self.assertEqual(s['target_body_height'], 120)
        r = evaluate_height_policy(p, 120)
        self.assertEqual(r['status'], 'PASS')
        self.assertAlmostEqual(r['recommended_uniform_scale_for_review'], 1)
        self.assertIn('XYZ', r['interpretation'])

    def test_keep_original_requires_source_baseline(self):
        with self.assertRaisesRegex(ValueError, 'original_body_height'):
            build_choice(self.human(), mode='keep_original', confirmed=True)

    def test_no_implicit_confirmation(self):
        with self.assertRaisesRegex(ValueError, '未获得明确用户确认'):
            build_choice(self.human(), mode='match_agent')

    def test_reject_nonhuman_matching_agent(self):
        with self.assertRaises(ValueError):
            build_choice(self.nonhuman(), mode='match_agent', reference_height=100, confirmed=True)

    def test_nonhuman_custom_target_must_also_match_skeleton(self):
        p, _ = build_choice(self.nonhuman(), mode='custom_target', target_height=145, confirmed=True)
        r = evaluate_height_policy(p, 145, rig_height=110)
        self.assertEqual(r['body_target_status'], 'PASS')
        self.assertEqual(r['skeleton_body_status'], 'FAIL')
        self.assertEqual(r['status'], 'FAIL')

    def test_nonhuman_uniform_global_does_not_fix_skeleton_mismatch(self):
        p, _ = build_choice(self.nonhuman(), mode='uniform_scale', original_body_height=100,
                            uniform_scale=1.5, confirmed=True)
        r = evaluate_height_policy(p, 150, rig_height=110)
        self.assertEqual(r['status'], 'FAIL')

    def test_save_refuses_example_template(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'height_profile.humanoid.example.json'
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'local.json'):
                save_local_profile(path, self.human())

    def test_save_and_backup_local(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'height.local.json'
            path.write_text(json.dumps(self.human()), encoding='utf-8')
            result = configure_profile(path, mode='custom_target', target_height=175,
                                       confirmed=True, save=True)
            self.assertEqual(result['target_body_height'], 175)
            self.assertTrue(Path(result['backup_file']).is_file())
            self.assertEqual(json.loads(path.read_text())['height_choice']['mode'], 'custom_target')

    def test_stale_height_audit_cannot_be_deployed(self):
        report = {'checks': {'source_height': {
            'selection_confirmed': True, 'height_choice_mode': 'match_agent',
            'target_body_height': 100}}}
        approved = {'status': 'USER_CONFIRMED', 'mode': 'match_agent', 'target_body_height': 100}
        verify_height_report_matches_decision(report, approved)
        with self.assertRaisesRegex(ValueError, '目标高度已变更'):
            verify_height_report_matches_decision(report, dict(approved, target_body_height=110))
        with self.assertRaisesRegex(ValueError, '高度策略已变更'):
            verify_height_report_matches_decision(report, dict(approved, mode='custom_target'))

    def test_noninteractive_run_cannot_skip_choice(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'height.local.json'
            path.write_text(json.dumps(self.human()))
            cfg_path = Path(d)/'workflow.local.json'
            cfg_path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'NEEDS_HEIGHT_CHOICE'):
                ensure_height_choice_before_audit(cfg_path, {'target':'player_runtime',
                    'height_profile':str(path)}, allow_interactive=False)
            p, _ = build_choice(self.human(), mode='match_agent', confirmed=True)
            path.write_text(json.dumps(p))
            result = ensure_height_choice_before_audit(cfg_path, {'target':'player_runtime',
                    'height_profile':str(path)}, allow_interactive=False)
            self.assertEqual(result['status'], 'USER_CONFIRMED')


if __name__ == '__main__':
    unittest.main()
