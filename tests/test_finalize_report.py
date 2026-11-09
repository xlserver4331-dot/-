import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "finalize_report.py"


class FinalizeTests(unittest.TestCase):
    def run_case(self, blender, engine):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "blender.json").write_text(json.dumps(blender), encoding="utf-8")
            (d / "engine.json").write_text(json.dumps(engine), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(SCRIPT), "--blender", str(d / "blender.json"), "--engine", str(d / "engine.json"), "--out", str(d / "final.json")], capture_output=True, text=True)
            result = json.loads((d / "final.json").read_text(encoding="utf-8"))
            return proc.returncode, result

    def test_pending_without_runtime(self):
        rc, report = self.run_case({"status": "PASS_PRELIMINARY", "checks": {"bounding_boxes": {"static_comparison": {"status": "PASS"}, "dynamic_comparison": {"status": "PASS"}}}}, {"target": "player_runtime", "tests": {}})
        self.assertNotEqual(rc, 0)
        self.assertEqual(report["overall_status"], "PENDING_OR_WARN")

    def test_no_evidence_means_pending(self):
        tests = {x: {"status": "PASS", "evidence": ""} for x in ["modeldoc_compiled", "mesh_materials_visible", "static_bounds_reviewed", "physics_collision_reviewed", "hammer_local_preview"]}
        rc, report = self.run_case({"status": "PASS_PRELIMINARY", "checks": {"bounding_boxes": {"static_comparison": {"status": "PASS"}, "dynamic_comparison": {"status": "PENDING"}}}}, {"target": "prop_preview", "authorized_to_use_model": True, "tests": tests})
        self.assertNotEqual(rc, 0)
        self.assertTrue(any(row["status"] == "PENDING" for row in report["engine_tests"]))

    def test_successful_prop(self):
        tests = {x: {"status": "PASS", "evidence": "screenshot-or-log-001"} for x in ["modeldoc_compiled", "mesh_materials_visible", "static_bounds_reviewed", "physics_collision_reviewed", "hammer_local_preview"]}
        rc, report = self.run_case({"status": "PASS_PRELIMINARY", "checks": {"bounding_boxes": {"static_comparison": {"status": "PASS"}}}}, {"target": "prop_preview", "authorized_to_use_model": True, "tests": tests})
        self.assertEqual(rc, 0)
        self.assertEqual(report["overall_status"], "PASS_WITH_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
