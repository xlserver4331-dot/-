import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from auto_workflow_core import (
    addon_dirs, deploy_transaction, gate_source_report,
    prepare_file_plan, safe_relative, validate_name, validated_destination,
)
from auto_workflow import get_launch_command


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "cs2"
        (self.root / "game/csgo").mkdir(parents=True)
        (self.root / "game/csgo/gameinfo.gi").write_text("file", encoding="utf-8")
        (self.root / "content/csgo_addons/test_addon").mkdir(parents=True)
        (self.root / "game/csgo_addons/test_addon").mkdir(parents=True)
        self.roots = addon_dirs(self.root, "test_addon")
        self.inputs = Path(self.tmp.name) / "inputs"
        self.inputs.mkdir()
        self.file = self.inputs / "test.vmdl"
        self.file.write_text("first", encoding="utf-8")
        self.config = Path(self.tmp.name) / "settings.json"
        self.cfg = {
            "target": "prop_preview", "cs2_root": str(self.root), "addon_name": "test_addon",
            "deploy_files": [{"source": str(self.file), "area": "content", "relative_path": "models/char.vmdl"}],
            "server_map": "de_dust2", "server_port": 27015, "launch_mode": "dedicated_server",
        }
        self.config.write_text(json.dumps(self.cfg), encoding="utf-8")

    def test_refuse_path_traversal(self):
        for relative in ("../csgo/gameinfo.gi", "/etc/passwd", "models/../../evil.vmdl", "C:/evil.vmdl", "..\\escape.vmdl"):
            with self.assertRaises(ValueError):
                safe_relative(relative) if relative.endswith(".gi") else validated_destination(self.roots, "content", relative)

    def test_refuse_core_file_and_bad_addon(self):
        with self.assertRaises(ValueError):
            validate_name("../csgo")
        with self.assertRaises(ValueError):
            validated_destination(self.roots, "game", "models/char.vmdl")
        with self.assertRaises(ValueError):
            validated_destination(self.roots, "content", "gameinfo.gi")

    def test_dry_plan_and_deploy_with_backup(self):
        roots, plan = prepare_file_plan(self.config, self.cfg)
        self.assertEqual(len(plan), 1)
        dst = plan[0]["destination"]
        self.assertFalse(dst.exists())
        result = deploy_transaction(plan, Path(self.tmp.name) / "backup")
        self.assertTrue(dst.exists())
        self.assertEqual(dst.read_text(), "first")
        self.assertFalse(result[0]["backed_up"])
        self.file.write_text("second", encoding="utf-8")
        result = deploy_transaction(plan, Path(self.tmp.name) / "backup2")
        self.assertEqual(dst.read_text(), "second")
        self.assertTrue(result[0]["backed_up"])
        self.assertEqual((Path(self.tmp.name) / "backup2" / "0000.backup").read_text(), "first")

    def test_transaction_rolls_back_on_copy_failure(self):
        _, plan = prepare_file_plan(self.config, self.cfg)
        first = plan[0]["destination"]
        first.parent.mkdir(parents=True, exist_ok=True)
        first.write_text("original", encoding="utf-8")
        broken = dict(plan[0])
        broken["source"] = self.inputs / "missing.vmdl"
        broken["destination"] = first.parent / "second.vmdl"
        broken["relative_path"] = "models/second.vmdl"
        with self.assertRaises(Exception):
            deploy_transaction([plan[0], broken], Path(self.tmp.name) / "backup-fail")
        self.assertEqual(first.read_text(encoding="utf-8"), "original")
        self.assertFalse(broken["destination"].exists())

    def test_duplicate_targets_rejected(self):
        self.cfg["deploy_files"].append(dict(self.cfg["deploy_files"][0]))
        with self.assertRaises(ValueError):
            prepare_file_plan(self.config, self.cfg)

    def test_symlink_escape_rejected(self):
        root = self.roots["content"]
        (root / "models").symlink_to(self.inputs, target_is_directory=True)
        with self.assertRaises(ValueError):
            validated_destination(self.roots, "content", "models/char.vmdl")

    def test_symlink_addon_rejected(self):
        (self.root / "content/csgo_addons/test_addon").rename(self.root / "content/csgo_addons/original")
        (self.root / "content/csgo_addons/test_addon").symlink_to(self.root / "content/csgo_addons/original", target_is_directory=True)
        with self.assertRaises(ValueError):
            addon_dirs(self.root, "test_addon")

    def test_gate_failures_and_pending(self):
        report = {"status": "WARN", "findings": {"errors": []}, "checks": {
            "bounding_boxes": {"static_comparison": {"status": "PENDING"}, "dynamic_comparison": {"status": "PENDING"}},
            "reference_rest_pose": "PENDING"}}
        self.assertTrue(gate_source_report(report, "prop_preview"))
        self.assertFalse(gate_source_report(report, "prop_preview", True))
        self.assertTrue(gate_source_report(report, "player_runtime", True))
        report["status"] = "FAIL"
        self.assertTrue(gate_source_report(report, "prop_preview", True))

    def test_dedicated_command_explicit_only(self):
        exe = self.root / "game/bin/win64/cs2.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("dummy", encoding="utf-8")
        cmd = get_launch_command(self.config, self.cfg)
        self.assertEqual(cmd[1:3], ["-dedicated", "-console"])
        self.assertEqual(cmd[-2:], ["+map", "de_dust2"])
        self.cfg["server_map"] = "../../bad"
        with self.assertRaises(ValueError):
            get_launch_command(self.config, self.cfg)


if __name__ == "__main__":
    unittest.main()
