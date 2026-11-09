"""Authorized GUI-only CS2 private server smoke test, with screenshot evidence.

Requires Windows + optional pyautogui/Pillow/opencv-python (for image confidence).
No game memory access, injection, cheat bypass, matchmaking or remote server control.
All screenshots are evidence for human review; never auto-PASS visual/Hitbox/AG2.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from game_qa_core import (
    file_sha256, safe_console_command, summarize_tests, validate_test_config,
)
from game_evidence_audit import audit_logs, audit_visual
from game_evidence_merge import merge


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_path(config_file: Path, value: str) -> Path:
    if not value:
        raise ValueError("所需的路径为空")
    p = Path(value).expanduser()
    return (p if p.is_absolute() else config_file.parent / p).resolve()


def client_binary(cs2_root: Path) -> Path:
    if not (cs2_root / "game/csgo/gameinfo.gi").is_file():
        raise ValueError("cs2_root 非有效 CS2 根目录")
    exe = cs2_root / "game/bin/win64/cs2.exe"
    if not exe.is_file():
        raise ValueError("未找到 CS2 客户端 cs2.exe")
    return exe


def client_command(exe: Path, endpoint: str) -> list[str]:
    # Only fixed, local-only launch args. Do not relay arbitrary user command lines.
    return [str(exe), "-console", "-condebug", "+connect", endpoint]


class WindowsGUI:
    """Desktop actions require interactive foreground Windows session and explicit consent."""

    def __init__(self, title: str):
        if platform.system() != "Windows":
            raise RuntimeError("自动键鼠控制仅支持 Windows 交互桌面；当前系统无法控制游戏")
        try:
            import pyautogui as pg
        except ImportError as exc:
            raise RuntimeError("缺少 pyautogui；先 pip install -r requirements-game.txt") from exc
        self.pg = pg
        self.pg.FAILSAFE = True  # move cursor to upper-left to abort
        self.pg.PAUSE = 0.04
        self.title = title.casefold()

    def focused_window(self):
        win = self.pg.getActiveWindow()
        if win is None or self.title not in (win.title or "").casefold():
            raise RuntimeError("CS2 未在前台，已停止键鼠操作，防止误操作其他应用")
        if win.width < 300 or win.height < 240:
            raise RuntimeError("CS2 窗口尺寸异常，停止采集")
        return win

    def try_focus(self):
        wins = [w for w in self.pg.getAllWindows()
                if self.title in (w.title or "").casefold() and w.width >= 300 and w.height >= 240]
        if not wins:
            return False
        try:
            wins[0].activate()
        except Exception:
            pass
        try:
            self.focused_window()
            return True
        except RuntimeError:
            return False

    def region(self):
        win = self.focused_window()
        screen_w, screen_h = self.pg.size()
        x0, y0 = max(0, int(win.left)), max(0, int(win.top))
        x1 = min(int(screen_w), int(win.left + win.width))
        y1 = min(int(screen_h), int(win.top + win.height))
        if x1 <= x0 or y1 <= y0:
            raise RuntimeError("CS2 窗口不在有效显示区域")
        return (x0, y0, x1 - x0, y1 - y0)

    def locate_template(self, image_path, confidence):
        self.focused_window()
        try:
            return self.pg.locateOnScreen(str(image_path), confidence=confidence, region=self.region()) is not None
        except self.pg.ImageNotFoundException:
            return False
        except (TypeError, NotImplementedError) as exc:
            raise RuntimeError("模板匹配需要 opencv-python + pyautogui") from exc

    def console(self, command, console_key):
        self.focused_window()
        try:
            self.pg.press(console_key)
            time.sleep(0.18)
            self.focused_window()
            self.pg.write(command, interval=0.025)
            self.focused_window()
            self.pg.press("enter")
            time.sleep(0.17)
        finally:
            # Attempt to close console only if CS2 is still foreground.
            self.focused_window()
            self.pg.press(console_key)

    def capture(self, path: Path):
        self.focused_window()
        path.parent.mkdir(parents=True, exist_ok=True)
        image = self.pg.screenshot(region=self.region())
        image.save(path)
        grayscale = image.convert("L")
        lo, hi = grayscale.getextrema()
        return {"path": str(path), "sha256": file_sha256(path),
                "width": image.width, "height": image.height,
                "status": "WARN_LOW_DETAIL" if hi - lo < 12 else "CAPTURED_PENDING_VISUAL_REVIEW",
                "note": "截图仅是视觉证据，不能据此自动判定骨骼、Hitbox、碰撞或 AG2 动画通过"}

    def perform(self, action: str, seconds: float, keys: dict, screenshot: Path, captures: int = 1):
        pg = self.pg
        held = []
        mouse_button = None
        self.focused_window()
        try:
            if action in {"walk", "run"}:
                if action == "walk":
                    pg.keyDown(keys["walk_modifier"])
                    held.append(keys["walk_modifier"])
                pg.keyDown(keys["forward"])
                held.append(keys["forward"])
            elif action == "crouch":
                pg.keyDown(keys["crouch"])
                held.append(keys["crouch"])
            elif action == "jump":
                pg.press(keys["jump"])
            elif action == "aim":
                pg.mouseDown(button="right")
                mouse_button = "right"
            elif action == "fire":
                pg.mouseDown(button="left")
                mouse_button = "left"
            elif action == "reload":
                pg.press(keys["reload"])
            elif action == "weapon_swap":
                pg.press(keys["secondary"])
            elif action == "inspect":
                pg.press(keys["inspect"])
            elif action == "knife_attack":
                pg.press(keys["knife"])
                pg.mouseDown(button="left")
                mouse_button = "left"
            elif action == "deploy":
                pg.press(keys["primary"])
            elif action in {"turn_left", "turn_right"}:
                # CS2 raw mouse input can ignore synthetic motion. This is advisory only.
                pg.moveRel(-150 if action == "turn_left" else 150, 0, duration=min(0.4, seconds / 2))
            if captures <= 1:
                time.sleep(seconds)
                shot = self.capture(screenshot)
                shot["sequence_screenshots"] = [shot["path"]]
                return shot
            # Capture evenly spaced observations while input is held.
            # Not real video; frame rates and animation states are not guaranteed.
            sequence=[]
            previous=0.0
            for i in range(captures):
                target=seconds*(i+1)/captures
                time.sleep(max(0.0,target-previous))
                previous=target
                filename=(screenshot if i==captures-1 else screenshot.with_name(screenshot.stem+f"__sample_{i+1}.png"))
                shot=self.capture(filename)
                sequence.append(shot["path"])
            shot["sequence_screenshots"]=sequence
            return shot
        finally:
            for key in reversed(held):
                pg.keyUp(key)
            if mouse_button:
                pg.mouseUp(button=mouse_button)
            if action == "weapon_swap":
                try:
                    self.focused_window()
                    pg.press(keys["primary"])
                except RuntimeError:
                    pass


def wait_for_ready(gui, ready: dict, config_file: Path, *, launched_at: float, log_start_offset: int = 0):
    strategy = ready["strategy"]
    deadline = time.monotonic() + int(ready.get("timeout_seconds", 90))
    img_path = resolve_path(config_file, ready["image_path"]) if strategy == "image_template" else None
    if img_path is not None and not img_path.is_file():
        raise ValueError(f"就绪检测模板不存在: {img_path}")
    log_path = resolve_path(config_file, ready["log_path"]) if strategy == "log_regex" else None
    marker = ready.get("pattern", "")
    while time.monotonic() < deadline:
        # If the user switches to another app after readiness, perform() will fail safe.
        focused = gui.try_focus()
        if focused and strategy == "image_template":
            if gui.locate_template(img_path, float(ready.get("confidence", 0.85))):
                return {"status": "READY_IMAGE_MATCHED", "evidence": str(img_path), "at_unix": time.time()}
        if focused and strategy == "log_regex" and log_path.is_file():
            # Consume only bytes appended after this run began, not historical log entries.
            with log_path.open("rb") as stream:
                stream.seek(min(log_start_offset, log_path.stat().st_size))
                data = stream.read(2_000_000).decode("utf-8", errors="replace")
            if marker.casefold() in data.casefold():
                return {"status": "READY_LOG_MATCHED_UNVERIFIED", "evidence": str(log_path), "at_unix": time.time()}
        time.sleep(0.75)
    raise TimeoutError("等待游戏就绪标记超时；不能证明已经进入地图，停止自动操作")


def make_report(config_file, game, normalized, report_dir, *, execute, cs2_root, gui_factory=WindowsGUI, popen=subprocess.Popen):
    """Runnable with mock GUI + mock Popen for unit tests; no private system access in dry run."""
    now = datetime.now(timezone.utc).isoformat()
    result = {"schema_version": 2, "tool": "cs2_game_qa_v5", "started_at_utc": now,
              "mode": "EXECUTE" if execute else "DRY_RUN", "status": "PENDING",
              "server_endpoint": normalized["server_endpoint"], "model_name": normalized["model_name"],
              "steps_planned": normalized["steps"], "test_results": [], "images": [],
              "engine_gates": {"ag2_binding_live": "PENDING", "hitboxes_reviewed": "PENDING",
                               "physics_collision_reviewed": "PENDING", "movement_animation_live": "PENDING",
                               "weapon_alignment_live": "PENDING", "local_server_mounted": "PENDING",
                               "viewmodel_arms_live": "PENDING", "original_limb_proportions_live": "PENDING",
                               "death_transition_live": "PENDING", "ragdoll_physics_live": "PENDING",
                               "respawn_live": "PENDING", "accessory_motion_live":"PENDING",
                               "joint_deformation_live":"PENDING"},
              "warning": "脚本不读取游戏内存/Hitbox/物理数据；截图及操作已发出均不证明动作生效。需要真实游戏录像/引擎日志及人工复核。"}
    if not execute:
        result["status"] = "DRY_RUN_COMPLETE"
        write_json(report_dir / "game_qa_report.json", result)
        return result
    log_files = []
    for val in game.get("log_files", []):
        path = resolve_path(config_file, val)
        log_files.append((path, path.stat().st_size if path.is_file() else 0))
    try:
        if game.get("client_launch", True):
            exe = client_binary(cs2_root)
            cmd = client_command(exe, normalized["server_endpoint"])
            result["client_command"] = cmd
        else:
            cmd = None
            result["client_command"] = "ALREADY_RUNNING_CLIENT_EXPECTED"
        ready = normalized["readiness"]
        log_start_offset = 0
        if ready["strategy"] == "log_regex":
            path = resolve_path(config_file, ready["log_path"])
            log_start_offset = path.stat().st_size if path.is_file() else 0
        # Validate image evidence and GUI dependencies before launching a client.
        if ready["strategy"] == "image_template":
            template = resolve_path(config_file, ready["image_path"])
            if not template.is_file():
                raise ValueError(f"就绪图像模板不存在: {template}")
        gui = gui_factory(normalized["window_title_contains"])
        if cmd:
            proc = popen(cmd, cwd=str(cs2_root / "game/bin/win64"),
                         shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            result["client_pid"] = proc.pid
        result["readiness"] = wait_for_ready(gui, ready, config_file,
                                             launched_at=time.time(), log_start_offset=log_start_offset)
        gui.console(safe_console_command("model", normalized["model_name"]), normalized["console_key"])
        result["model_select"] = "COMMAND_SENT_NOT_CONFIRMED"
        time.sleep(1)
        view_cmd = normalized["thirdperson_command"]
        if view_cmd != "none":
            gui.console(view_cmd, normalized["console_key"])
            result["thirdperson"] = "COMMAND_SENT_NOT_CONFIRMED"
            time.sleep(0.4)
        shots_dir = report_dir / "screenshots"
        current_view = "thirdperson" if view_cmd != "none" else "UNVERIFIED"
        for step in normalized["steps"]:
            shot_path = shots_dir / f"{step['id']}.png"
            try:
                if step["view"] != current_view:
                    desired = (safe_console_command("firstperson") if step["view"] == "firstperson"
                               else normalized["thirdperson_command"])
                    if desired == "none":
                        raise RuntimeError("第三人称测试需要已校准的命令或人工确认，当前为 none")
                    gui.console(desired, normalized["console_key"])
                    current_view = step["view"]  # command sent, NOT visually confirmed
                    time.sleep(0.35)
                action = step["action"]
                if action == "death":
                    # Explicit local-only self kill; image of own death is NOT evidence
                    # that observer saw correct ragdoll. Require a separate observer clip.
                    gui.console(safe_console_command("self_death"), normalized["console_key"])
                    shot = gui.perform("idle", step["seconds"], normalized["keys"], shot_path)
                    status = "TRIGGER_SENT_PENDING_OBSERVER_EVIDENCE"
                    extra = {"trigger": "kill", "observer_evidence":
                             normalized["death_test"].get("observer_evidence_path", ""),
                             "note": "自身视角截图不证明第三人称死亡过渡/布娃娃；须额外观察者录像或服务器物理证据"}
                else:
                    if step.get("captures",1)>1:
                        # Dry-run mocks without multi-frame GUI support are not
                        # allowed to silently claim a completed burst.
                        try:
                            shot=gui.perform(action,step["seconds"],normalized["keys"],shot_path,
                                             captures=step["captures"])
                        except TypeError as exc:
                            raise RuntimeError("当前 GUI 测试适配器不支持多帧采样") from exc
                    else:
                        shot = gui.perform(action, step["seconds"], normalized["keys"], shot_path)
                    status = shot["status"]
                    extra = {}
                item = {"id": step["id"], "action": action, "view": step["view"],
                        "seconds": step["seconds"], "status": status,
                        "screenshot": shot["path"], "sha256": shot["sha256"],
                        "sequence_screenshots": shot.get("sequence_screenshots", [shot["path"]]), **extra}
                result["images"].append(shot)
                result["test_results"].append(item)
                write_json(report_dir / "game_qa_report.json", result)
            except Exception as exc:
                result["test_results"].append({"id": step["id"], "action": step["action"],
                                               "status": "FAIL_CAPTURE_OR_INPUT", "error": str(exc)})
                raise
        result["status"] = summarize_tests(result["test_results"])
        result["log_audit"] = audit_logs(log_files) if log_files else {"status": "PENDING_NO_ENGINE_LOGS"}
        baseline_path = game.get("visual_baseline", "")
        if baseline_path:
            ref = resolve_path(config_file, baseline_path)
            if ref.is_file():
                result["visual_audit"] = audit_visual(result, json.loads(ref.read_text(encoding="utf-8")), ref.parent)
            else:
                result["visual_audit"] = {"status": "PENDING_BASELINE_NOT_FOUND", "path": str(ref)}
        else:
            result["visual_audit"] = {"status": "PENDING_NO_BASELINE"}
        if result["log_audit"]["status"].startswith("WARN") or result["visual_audit"]["status"].startswith("WARN"):
            result["status"] = "REVIEW_WARNINGS_PRESENT"
    except Exception as exc:
        result["status"] = "BLOCKED"
        result["error"] = str(exc)
    finally:
        if "log_audit" not in result and log_files:
            result["log_audit"] = audit_logs(log_files)
        result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(report_dir / "game_qa_report.json", result)
        template = Path(__file__).resolve().parents[1] / "templates/engine_validation.template.json"
        if template.is_file():
            engine = merge(result, json.loads(template.read_text(encoding="utf-8")))
            write_json(report_dir / "engine_validation.pending.json", engine)
    return result


def run_from_files(config_path: str, cs2_root: str, output: str, *, execute=False, gui_factory=WindowsGUI, popen=subprocess.Popen):
    path = Path(config_path).expanduser().resolve()
    game = json.loads(path.read_text(encoding="utf-8"))
    normalized = validate_test_config(game, execute=execute)
    result_dir = Path(output).expanduser().resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    root = Path(cs2_root).expanduser().resolve()
    return make_report(path, game, normalized, result_dir, execute=execute,
                       cs2_root=root, gui_factory=gui_factory, popen=popen)


def main():
    parser = argparse.ArgumentParser(description="CS2 本地服务器自动键鼠动作/截图采样：非游戏模型自动通过判定")
    parser.add_argument("--config", required=True, help="私人游戏 QA 配置（由 game_test.example.json 复制）")
    parser.add_argument("--cs2-root", required=True, help="Steam 安装的 CS2 根目录")
    parser.add_argument("--out-dir", required=True, help="私有报告与截图保存目录")
    parser.add_argument("--execute", action="store_true", help="显式授权接管当前 Windows 游戏窗口并操作")
    a = parser.parse_args()
    result = run_from_files(a.config, a.cs2_root, a.out_dir, execute=a.execute)
    print(json.dumps({"status": result["status"], "file": str(Path(a.out_dir)/"game_qa_report.json")}, ensure_ascii=False))
    if result["status"] == "BLOCKED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
