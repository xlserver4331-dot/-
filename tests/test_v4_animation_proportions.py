"""Pure offline checks; no actual Blender or CS2 runs occur."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from proportion_math import evaluate_proportions, pose_length_deviation, anisotropy
from animation_suite import audit_suite
from game_qa_core import validate_test_config, safe_console_command
from game_evidence_merge import merge
from auto_workflow_core import gate_source_report


def measured(arms=2.0, torso=2.0):
    ref = {"anchor_ids": ["torso"], "segments": {"torso": 1.0, "upper_arm": 1.0, "forearm": 1.0}}
    target = {"segments": {"torso": torso, "upper_arm": arms, "forearm": arms}}
    return evaluate_proportions(ref, target)


class V4Tests(unittest.TestCase):
    def test_original_limb_uniform_scale_allowed(self):
        self.assertEqual(measured(arms=2, torso=2)["status"], "PASS")

    def test_limbs_stretched_to_agent_blocked(self):
        result = measured(arms=2.5, torso=2)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(len(result["violations"]), 2)

    def test_global_scale_derived_from_torso_not_limbs(self):
        result = measured(arms=3, torso=2)
        self.assertEqual(result["uniform_scale_from_torso"], 2)

    def test_missing_anchor_pending(self):
        ref = {"anchor_ids": ["torso"], "segments": {"torso": 1, "upper_arm": 1}}
        self.assertEqual(evaluate_proportions(ref, {"segments": {"upper_arm": 2}})["status"], "PENDING")

    def test_nonuniform_scale_and_pose_stretch(self):
        self.assertGreater(anisotropy([1, 1.15, 1]), 0.1)
        self.assertAlmostEqual(pose_length_deviation(2, 2.2), 0.1)
        self.assertIsNone(pose_length_deviation(0, 4))

    def test_animation_death_ragdoll_runtime_not_mandatory_blender_action(self):
        result = audit_suite({"tracks": {"worldmodel": [
            {"id": "death_transition", "mode": "runtime_only", "kind": "transition"},
            {"id": "ragdoll_fall", "mode": "runtime_only", "kind": "physics"}
        ]}}, set(), set())
        self.assertEqual(result["status"], "PENDING_RUNTIME")
        self.assertEqual(result["tracks"]["worldmodel"][1]["status"], "PENDING_RUNTIME")

    def test_explicit_missing_action_fails(self):
        result = audit_suite({"tracks": {"worldmodel": [{"id": "walk", "mode": "action_required", "source_action": "Walk"}]}}, set(), set())
        self.assertEqual(result["status"], "FAIL")

    def test_authorized_death_last_only(self):
        base = {"enabled": True, "allow_desktop_control": False, "server_endpoint": "127.0.0.1:27015",
                "model_name": "model", "readiness": {"strategy": "image_template", "image_path": "calibrated.png"},
                "death_test": {"enabled": True, "allow_self_kill": True, "sv_cheats_confirmed": True},
                "steps": [{"id": "idle", "action": "idle", "view": "firstperson", "seconds": 0.5},
                          {"id": "dead", "action": "death", "view": "thirdperson", "seconds": 1.0}]}
        result = validate_test_config(base)
        self.assertEqual(result["steps"][-1]["action"], "death")
        self.assertEqual(safe_console_command("self_death"), "kill")
        base["steps"] = list(reversed(base["steps"]))
        with self.assertRaises(ValueError):
            validate_test_config(base)

    def test_death_without_permission_rejected(self):
        cfg = {"enabled": True, "server_endpoint": "127.0.0.1:27015", "model_name": "model",
               "readiness": {"strategy": "image_template", "image_path": "calibrated.png"},
               "steps": [{"id": "death", "action": "death", "view": "thirdperson"}]}
        with self.assertRaises(ValueError):
            validate_test_config(cfg)

    def test_firstperson_hand_and_death_stay_pending(self):
        report = {"model_name": "test", "test_results": [
            {"id": "hands", "view": "firstperson", "action": "reload", "screenshot": "hands.png"},
            {"id": "death", "view": "thirdperson", "action": "death", "screenshot": "death.png"}]}
        template = {"target": "player_runtime", "tests": {}}
        merged = merge(report, template)
        self.assertEqual(merged["tests"]["viewmodel_arms_live"]["status"], "PENDING")
        self.assertIn("hands.png", merged["tests"]["viewmodel_arms_live"]["evidence"])
        self.assertEqual(merged["tests"]["ragdoll_physics_live"]["status"], "PENDING")

    def test_source_gate_blocks_modified_lengths(self):
        report = {"status": "PASS_PRELIMINARY", "checks": {
            "bounding_boxes": {"static_comparison": {"status": "PASS"}, "dynamic_comparison": {"status": "PASS"}},
            "reference_rest_pose": "USER_ATTESTED", "source_proportions": {"status": "FAIL"},
            "animation_suite": {"status": "PENDING_RUNTIME"},
            "accessories": {"status":"PASS_PRELIMINARY"},
            "joint_deformation": {"status":"PASS_PRELIMINARY"},
            "mesh_integrity": {"status":"PASS_PRELIMINARY"},
            "rig_stretch": {"status":"PASS_PRELIMINARY"}}}
        self.assertIn("原始四肢比例", " ".join(gate_source_report(report, "player_runtime")))
        report["checks"]["source_proportions"]["status"] = "PASS"
        self.assertFalse(gate_source_report(report, "player_runtime"))


if __name__ == "__main__":
    unittest.main()
