"""Fake desktop/CS2 runner tests. They do not start the game or control a real PC."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from game_qa_core import (DEFAULT_STEPS, loopback_address, safe_console_command,
                          summarize_tests, validate_test_config)
from game_qa import client_command, run_from_files
from game_evidence_audit import audit_logs, audit_visual, crop_image
from game_evidence_merge import merge


class FakeGui:
    fail = False
    commands = []

    def __init__(self, title):
        self.title = title
        FakeGui.commands = []

    def try_focus(self):
        return True

    def locate_template(self, img, confidence):
        return True

    def console(self, cmd, key):
        FakeGui.commands.append((cmd, key))

    def perform(self, action, seconds, keys, screenshot):
        if FakeGui.fail:
            raise RuntimeError("CS2 未在前台；模拟失焦")
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        screenshot.write_bytes(b"fake png bytes to simulate evidence")
        return {"path": str(screenshot), "sha256": "a" * 64,
                "width": 800, "height": 600, "status": "CAPTURED_PENDING_VISUAL_REVIEW"}


class FakeProc:
    pid = 12345


class GameQaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / "CS2"
        (self.root / "game/csgo").mkdir(parents=True)
        (self.root / "game/csgo/gameinfo.gi").write_text("fake")
        (self.root / "game/bin/win64").mkdir(parents=True)
        (self.root / "game/bin/win64/cs2.exe").write_bytes(b"fake")
        self.template = base / "ready.png"
        self.template.write_bytes(b"fake")
        self.config = base / "test.json"
        self.game = {
            "enabled": True, "allow_desktop_control": True,
            "server_endpoint": "127.0.0.1:27015", "model_name": "test_char",
            "readiness": {"strategy": "image_template", "image_path": str(self.template),
                          "confidence": 0.9, "timeout_seconds": 5},
            "client_launch": True,
            "steps": [{"id": "idle", "action": "idle", "seconds": 0.1},
                      {"id": "walk", "action": "walk", "seconds": 0.1}],
        }
        self.save()
        FakeGui.fail = False
        self.report_dir = base / "out"

    def save(self):
        self.config.write_text(json.dumps(self.game), encoding="utf-8")

    def test_local_only_rejects_network(self):
        for value in ("10.1.1.10:27015", "8.8.8.8:27015", "example.com:27015", "127.0.0.1:80", "127.0.0.1;quit:27015", "::1:27015"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                loopback_address(value)
        self.assertEqual(loopback_address("localhost:27015"), ("localhost", 27015))

    def test_commands_are_not_arbitrary(self):
        self.assertEqual(safe_console_command("model", "a_b"), "say !model a_b all")
        for value in ("test;quit", "bad\nexec autoexec", "some name"):
            with self.assertRaises(ValueError):
                safe_console_command("model", value)
        with self.assertRaises(ValueError):
            safe_console_command("exec", "file")

    def test_user_consent_blocks_execute_only(self):
        self.game["allow_desktop_control"] = False
        self.assertEqual(len(validate_test_config(self.game, execute=False)["steps"]), 2)
        with self.assertRaises(ValueError):
            validate_test_config(self.game, execute=True)

    def test_dangerous_options_and_long_sequence_rejected(self):
        self.game["thirdperson_command"] = "say !tp;quit"
        with self.assertRaises(ValueError):
            validate_test_config(self.game)
        self.game["thirdperson_command"] = "none"
        self.game["steps"] = [{"id": "a", "action": "kill", "seconds": 1}]
        with self.assertRaises(ValueError):
            validate_test_config(self.game)
        self.game["steps"] = [{"id": "a", "action": "walk", "seconds": 100}]
        with self.assertRaises(ValueError):
            validate_test_config(self.game)

    def test_dry_run_does_not_launch_or_operate(self):
        self.game["allow_desktop_control"] = False
        self.save()
        out = run_from_files(self.config, self.root, self.report_dir,
                             execute=False, gui_factory=lambda _: self.fail("GUI should not initialize"),
                             popen=lambda *args, **kw: self.fail("No process launch in dry run"))
        self.assertEqual(out["status"], "DRY_RUN_COMPLETE")
        self.assertFalse((self.report_dir / "screenshots").exists())

    def test_simulated_full_session(self):
        self.save()
        commands = []
        def popen(cmd, **kwargs):
            commands.append(cmd)
            return FakeProc()
        out = run_from_files(self.config, self.root, self.report_dir,
                             execute=True, gui_factory=FakeGui, popen=popen)
        self.assertEqual(out["status"], "CAPTURED_PENDING_VISUAL_REVIEW")
        self.assertEqual(len(out["images"]), 2)
        self.assertTrue((self.report_dir / "screenshots/idle.png").is_file())
        self.assertEqual(commands[0][-2:], ["+connect", "127.0.0.1:27015"])
        self.assertEqual(FakeGui.commands[0][0], "say !model test_char all")
        self.assertEqual(out["engine_gates"]["hitboxes_reviewed"], "PENDING")

    def test_v4_simulated_firstperson_then_authorized_death_is_not_a_pass(self):
        self.game["steps"] = [
            {"id": "hands", "action": "inspect", "view": "firstperson", "seconds": 0.1},
            {"id": "dead", "action": "death", "view": "thirdperson", "seconds": 0.1},
        ]
        self.game["death_test"] = {"enabled": True, "allow_self_kill": True,
                                    "sv_cheats_confirmed": True}
        self.save()
        out = run_from_files(self.config, self.root, self.report_dir, execute=True,
                             gui_factory=FakeGui, popen=lambda *a, **kw: FakeProc())
        self.assertNotEqual(out["status"], "PASS")
        self.assertIn(("kill", "`"), FakeGui.commands)
        self.assertIn(("firstperson", "`"), FakeGui.commands)
        self.assertEqual(out["test_results"][-1]["status"], "TRIGGER_SENT_PENDING_OBSERVER_EVIDENCE")
        evidence = json.loads((self.report_dir / "engine_validation.pending.json").read_text())
        self.assertEqual(evidence["tests"]["ragdoll_physics_live"]["status"], "PENDING")
        self.assertIn("hands.png", evidence["tests"]["viewmodel_arms_live"]["evidence"])

    def test_simulated_focus_loss_stops(self):
        FakeGui.fail = True
        self.save()
        out = run_from_files(self.config, self.root, self.report_dir, execute=True,
                             gui_factory=FakeGui, popen=lambda *a, **k: FakeProc())
        self.assertEqual(out["status"], "BLOCKED")
        self.assertIn("失焦", out["error"])
        self.assertTrue((self.report_dir / "game_qa_report.json").exists())

    def test_wait_requires_real_configured_signal(self):
        self.game["readiness"] = {"strategy": "none"}
        with self.assertRaises(ValueError):
            validate_test_config(self.game)

    def test_log_audit_only_new_bytes(self):
        log = Path(self.tmp.name) / "engine.log"
        log.write_text("failed to load model example.vmdl\n", encoding="utf8")
        prior = log.stat().st_size
        self.assertEqual(audit_logs([(log, prior)])["status"], "NO_MATCHES_NOT_A_PASS")
        with log.open("a", encoding="utf8") as f:
            f.write("missing material test.vmat\n")
        result = audit_logs([(log, prior)])
        self.assertEqual(result["status"], "WARN_POSSIBLE_ENGINE_ERRORS")
        self.assertEqual(result["matches"][0]["category"], "MISSING_MATERIAL")

    def test_engine_evidence_stays_pending(self):
        template = {"target": "player_runtime", "tests": {
            "movement_animation_live": {"status": "PENDING"},
            "hitboxes_reviewed": {"status": "PENDING"},
            "ag2_binding_live": {"status": "PENDING"},
        }}
        report = {"status": "CAPTURED_PENDING_VISUAL_REVIEW", "model_name": "test_char",
                  "test_results": [{"id": "idle", "screenshot": "screenshots/idle.png"}]}
        merged = merge(report, template)
        self.assertEqual(merged["tests"]["movement_animation_live"]["status"], "PENDING")
        self.assertEqual(merged["tests"]["hitboxes_reviewed"]["status"], "PENDING")
        self.assertIn("idle.png", merged["tests"]["movement_animation_live"]["evidence"])

    def test_status_not_auto_pass(self):
        self.assertEqual(summarize_tests([{"status": "CAPTURED_PENDING_VISUAL_REVIEW"}]),
                         "CAPTURED_PENDING_VISUAL_REVIEW")

    def test_image_difference_warning(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed in unit test environment")
        original = Path(self.tmp.name) / "orig.png"
        changed = Path(self.tmp.name) / "changed.png"
        Image.new("RGB", (24,24), (0,0,0)).save(original)
        Image.new("RGB", (24,24), (255,255,255)).save(changed)
        report = {"test_results": [{"id": "idle", "screenshot": str(changed)}]}
        baseline = {"steps": {"idle": {"reference_image": str(original),
                                       "crop_relative": [0,0,1,1], "max_mean_pixel_delta": 50}}}
        result = audit_visual(report, baseline, Path(self.tmp.name))
        self.assertEqual(result["checks"][0]["status"], "WARN_VISUAL_REGRESSION")


if __name__ == "__main__": unittest.main()
