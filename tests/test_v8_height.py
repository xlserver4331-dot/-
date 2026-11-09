import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from height_policy_core import evaluate_height_policy
from auto_workflow_core import gate_source_report


class TestDecorationExcludedHeight(unittest.TestCase):
    def human(self, **overrides):
        result = dict(model_type='humanoid', exclude_accessories_from_height=True,
                      agent_reference_body_height=100, height_choice={'mode': 'match_agent', 'confirmed_by_user': True},
                      warn_relative_deviation=.05, fail_relative_deviation=.15)
        result.update(overrides)
        return result

    def alien(self, **overrides):
        result = dict(model_type='nonhumanoid', exclude_accessories_from_height=True,
                      height_choice={'mode': 'keep_original', 'original_body_height': 135, 'confirmed_by_user': True},
                      warn_relative_deviation=.03, fail_relative_deviation=.08)
        result.update(overrides)
        return result

    def test_human_body_equal(self):
        x = evaluate_height_policy(self.human(), 100)
        self.assertEqual(x['status'], 'PASS')
        self.assertAlmostEqual(x['recommended_uniform_scale_for_review'], 1)

    def test_human_uniform_scale_recommendation(self):
        x = evaluate_height_policy(self.human(), 90)
        self.assertEqual(x['status'], 'WARN')
        self.assertAlmostEqual(x['recommended_uniform_scale_for_review'], 100/90)

    def test_human_too_tall(self):
        self.assertEqual(evaluate_height_policy(self.human(), 120)['status'], 'FAIL')

    def test_human_no_agent_reference(self):
        self.assertEqual(evaluate_height_policy(self.human(agent_reference_body_height=None), 100)['status'], 'PENDING')

    def test_human_accessories_must_be_excluded(self):
        self.assertEqual(evaluate_height_policy(self.human(exclude_accessories_from_height=False), 100)['status'], 'FAIL')

    def test_bad_model_type(self):
        self.assertEqual(evaluate_height_policy(self.human(model_type='dinosaur'), 100)['status'], 'FAIL')

    def test_bad_body_height(self):
        self.assertEqual(evaluate_height_policy(self.human(), float('nan'))['status'], 'FAIL')
        self.assertEqual(evaluate_height_policy(self.human(), 0)['status'], 'FAIL')

    def test_nonhuman_equal_bone_and_mesh(self):
        self.assertEqual(evaluate_height_policy(self.alien(), 135, rig_height=135)['status'], 'PASS')

    def test_nonhuman_no_rig_span(self):
        self.assertEqual(evaluate_height_policy(self.alien(), 135)['status'], 'PENDING')

    def test_nonhuman_warning(self):
        self.assertEqual(evaluate_height_policy(self.alien(), 135, rig_height=130)['status'], 'WARN')

    def test_nonhuman_failure(self):
        self.assertEqual(evaluate_height_policy(self.alien(), 135, rig_height=110)['status'], 'FAIL')

    def test_thresholds(self):
        self.assertEqual(evaluate_height_policy(self.human(warn_relative_deviation=.16), 100)['status'], 'FAIL')

    def test_no_automated_nonhuman_scale(self):
        self.assertEqual(evaluate_height_policy(self.alien(), 100, rig_height=100)['status'], 'FAIL')
        self.assertIn('整体缩放不会修复', evaluate_height_policy(self.alien(), 100, rig_height=80)['interpretation'])

    def _base_report(self, status, category='humanoid'):
        return {
            'status': 'WARN', 'findings': {'errors': []},
            'checks': {
                'source_height': {
                    'status': status, 'model_type': category, 'selection_confirmed': True,
                    'relative_deviation': .06, 'failure_threshold': .15,
                },
                'source_proportions': {'status': 'PASS'},
                'accessories': {'status': 'PASS_PRELIMINARY'},
                'joint_deformation': {'status': 'PASS_PRELIMINARY'},
                'mesh_integrity': {'status': 'PASS_PRELIMINARY'},
                'rig_stretch': {'status': 'PASS_PRELIMINARY'},
                'bounding_boxes': {
                    'static_comparison': {'status': 'PASS'},
                    'dynamic_comparison': {'status': 'PASS'},
                },
                'animation_suite': {'status': 'PENDING_RUNTIME'},
                'reference_rest_pose': 'USER_ATTESTED',
            },
        }

    def test_predeploy_missing_height_blocked(self):
        report = self._base_report('PENDING')
        self.assertTrue(any('身高' in msg for msg in gate_source_report(report, 'player_runtime')))

    def test_predeploy_fail_height_blocked(self):
        self.assertTrue(gate_source_report(self._base_report('FAIL'), 'player_runtime'))

    def test_predeploy_valid_height_warn_allowed(self):
        self.assertEqual(gate_source_report(self._base_report('WARN'), 'player_runtime'), [])

    def test_predeploy_invalid_warn_reference_blocked(self):
        report = self._base_report('WARN')
        report['checks']['source_height']['failure_threshold'] = 0
        self.assertTrue(gate_source_report(report, 'player_runtime'))


if __name__ == '__main__':
    unittest.main()
