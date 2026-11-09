"""Pure validation and reporting helpers for an authorized, local-only CS2 GUI test.

No remote servers, no matchmaking, no arbitrary command execution. Runtime observations
are *evidence for review*, never a substitute for ModelDoc/Hitbox/AG2 inspection.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
from pathlib import Path

SUPPORTED_STEPS = {"idle", "walk", "run", "crouch", "jump", "aim", "fire", "reload", "weapon_swap", "turn_left", "turn_right", "inspect", "knife_attack", "deploy", "death"}
DEFAULT_STEPS = [
    {"id": "idle", "action": "idle", "seconds": 1.0},
    {"id": "walk", "action": "walk", "seconds": 1.1},
    {"id": "run", "action": "run", "seconds": 1.1},
    {"id": "crouch", "action": "crouch", "seconds": 1.1},
    {"id": "jump", "action": "jump", "seconds": 0.6},
    {"id": "aim", "action": "aim", "seconds": 0.8},
    {"id": "fire", "action": "fire", "seconds": 0.7},
    {"id": "reload", "action": "reload", "seconds": 1.5},
    {"id": "weapon_swap", "action": "weapon_swap", "seconds": 0.8},
    {"id": "turn_left", "action": "turn_left", "seconds": 0.8},
]
SAFE_KEY_NAMES = {"w", "a", "s", "d", "shift", "ctrl", "space", "r", "f", "1", "2", "3", "left", "right", "alt"}
VALID_READY = {"image_template", "log_regex"}
SAFE_MODEL = re.compile(r"[A-Za-z0-9_.-]{1,60}\Z")
SAFE_WINDOW_TITLE = re.compile(r"[^\x00-\x1f]{4,80}\Z")
SAFE_STEP = re.compile(r"[a-z][a-z0-9_]{0,40}\Z")


def loopback_address(endpoint: str) -> tuple[str, int]:
    """Strict endpoint allowlist. No private LAN, domains or DNS lookup by default."""
    if not isinstance(endpoint, str) or not re.fullmatch(r"(localhost|127\.0\.0\.1):\d{1,5}", endpoint):
        raise ValueError("server_endpoint 只能是 localhost:<port> 或 127.0.0.1:<port>")
    host, port_s = endpoint.rsplit(":", 1)
    port = int(port_s)
    if not 1024 <= port <= 65535:
        raise ValueError("本地服务器端口必须是 1024~65535")
    if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
        raise ValueError("仅允许本机回环地址")
    return host, port


def validate_test_config(game: dict, *, target="player_runtime", execute=False) -> dict:
    if not isinstance(game, dict) or not game.get("enabled"):
        raise ValueError("game_test.enabled 必须为 true")
    if target != "player_runtime":
        raise ValueError("游戏自动操作目前只支持 player_runtime 私人服务器；地图 prop 请在 Hammer 验收")
    if execute and not game.get("allow_desktop_control"):
        raise ValueError("真实执行必须显式设置 allow_desktop_control=true；不会静默接管桌面")
    host, port = loopback_address(game.get("server_endpoint", ""))
    name = game.get("model_name", "")
    if not isinstance(name, str) or not SAFE_MODEL.fullmatch(name):
        raise ValueError("model_name 必须是已配置在私人服务器插件内的简单模型名（字母/数字/下划线/点/横线）")
    view_cmd = game.get("thirdperson_command", "say !tp")
    if view_cmd not in ("say !tp", "thirdperson", "none"):
        raise ValueError("thirdperson_command 只可为 'say !tp'、'thirdperson' 或 'none'")
    title = game.get("window_title_contains", "Counter-Strike 2")
    if not isinstance(title, str) or not SAFE_WINDOW_TITLE.fullmatch(title):
        raise ValueError("window_title_contains 非法")
    console_key = game.get("console_key", "`")
    if console_key not in ("`", "~", "f10", "f11", "f12"):
        raise ValueError("console_key 只能是 `、~、f10、f11、f12，需与实际游戏绑定一致")
    keys = game.get("keys", {})
    if not isinstance(keys, dict):
        raise ValueError("keys 必须为对象")
    defaults = {"forward": "w", "walk_modifier": "shift", "crouch": "ctrl", "jump": "space",
                "reload": "r", "primary": "1", "secondary": "2", "turn_left": "a", "turn_right": "d", "inspect": "f", "knife": "3"}
    bindings = {k: keys.get(k, v) for k, v in defaults.items()}
    if any(key not in SAFE_KEY_NAMES for key in bindings.values()):
        raise ValueError("按键配置仅支持安全按键白名单，不能使用自定义宏")
    steps = game.get("steps", DEFAULT_STEPS)
    if not isinstance(steps, list) or not steps or len(steps) > 40:
        raise ValueError("steps 应为 1~40 个动作")
    ids = set()
    clean_steps = []
    death_test = game.get("death_test", {})
    if not isinstance(death_test, dict):
        raise ValueError("death_test 必须为对象")
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError("steps 中每项必须为对象")
        name_id, action = step.get("id"), step.get("action")
        if not isinstance(name_id, str) or not SAFE_STEP.fullmatch(name_id) or name_id in ids:
            raise ValueError("每个步骤 id 必须是唯一安全字符串")
        ids.add(name_id)
        if action not in SUPPORTED_STEPS:
            raise ValueError("不支持的动作: " + str(action))
        view = step.get("view", "thirdperson")
        if view not in {"firstperson", "thirdperson"}:
            raise ValueError("view 必须为 firstperson/thirdperson")
        if action == "death":
            if index != len(steps) - 1:
                raise ValueError("死亡测试必须是最后一步；死亡后不假设已自动复活")
            if not (death_test.get("enabled") and death_test.get("allow_self_kill") and death_test.get("sv_cheats_confirmed")):
                raise ValueError("仅可在确认 sv_cheats 1 的私人服、显式允许 self kill 后执行 death")
            if view != "thirdperson":
                raise ValueError("死亡世界模型需要第三人称证据；第一人称死亡切换由独立验收项复核")
        try:
            duration = float(step.get("seconds", 0.8))
        except (ValueError, TypeError):
            raise ValueError("seconds 必须为数字") from None
        if not 0.1 <= duration <= 8:
            raise ValueError("每步测试时长必须为 0.1~8 秒")
        captures=step.get("captures",1)
        if isinstance(captures,bool) or not isinstance(captures,int) or not 1 <= captures <= 3:
            raise ValueError("captures 必须是整数 1~3")
        if captures>1 and duration<0.6:
            raise ValueError("多帧动作采样至少需要 0.6 秒")
        clean_steps.append({"id": name_id, "action": action, "seconds": duration, "view": view, "captures": captures})
    if sum(r["captures"] for r in clean_steps) > 90:
        raise ValueError("动作截图总数不得超过 90")
    if sum(r["seconds"] for r in clean_steps) > 150:
        raise ValueError("动作总时长不能超过 150 秒")
    if any(s["view"] == "thirdperson" for s in clean_steps) and view_cmd == "none":
        # Existing v3 default had implicit third-person screenshots. Keep backward
        # compatibility for manual third-person setups but never assert view is confirmed.
        pass
    ready = game.get("readiness", {})
    if not isinstance(ready, dict) or ready.get("strategy") not in VALID_READY:
        raise ValueError("readiness.strategy 必须为 image_template 或 log_regex，拒绝仅根据等待时间猜测游戏已就绪")
    timeout = int(ready.get("timeout_seconds", 90))
    if not 5 <= timeout <= 240:
        raise ValueError("readiness.timeout_seconds 必须在 5~240 之间")
    if ready["strategy"] == "image_template":
        if not ready.get("image_path"):
            raise ValueError("image_template 模式必须有已校准的 image_path")
        confidence = float(ready.get("confidence", 0.85))
        if not 0.6 <= confidence <= 0.99:
            raise ValueError("image_template.confidence 应在 0.6~0.99")
    else:
        pattern = ready.get("pattern", "")
        if not isinstance(pattern, str) or not (4 <= len(pattern) <= 160):
            raise ValueError("log_regex 需要明确的当前版本游戏连接完成日志 pattern")
        # Avoid regex bombs and general command strings; a literal phrase is adequate for this application.
        if not re.fullmatch(r"[\w\s\-\[\]():.]+", pattern):
            raise ValueError("日志就绪标记仅接受简单字面文本；请不要输入复杂正则")
        if not ready.get("log_path"):
            raise ValueError("log_regex 模式必须配置游戏本地日志绝对路径")
    log_files = game.get("log_files", [])
    if not isinstance(log_files, list) or len(log_files) > 8 or any(not isinstance(x, str) or not x for x in log_files):
        raise ValueError("log_files 应为不超过 8 个本地日志路径的数组")
    if execute and game.get("client_launch", True) not in (True, False):
        raise ValueError("client_launch 应为布尔值")
    return {"server_endpoint": f"{host}:{port}", "model_name": name, "thirdperson_command": view_cmd,
            "window_title_contains": title, "console_key": console_key,
            "keys": bindings, "steps": clean_steps, "readiness": ready,
            "client_launch": bool(game.get("client_launch", True)),
            "death_test": {"enabled": bool(death_test.get("enabled")),
                           "observer_evidence_path": death_test.get("observer_evidence_path", ""),
                           "confirmation": "USER_CONFIRMED_LOCAL_CHEATS" if death_test.get("sv_cheats_confirmed") else "PENDING"}}


def safe_console_command(kind: str, model_name: str = "") -> str:
    if kind == "model":
        if not SAFE_MODEL.fullmatch(model_name):
            raise ValueError("模型名不得包含控制台分号/换行/空格等字符")
        return f"say !model {model_name} all"
    if kind == "thirdperson":
        return "say !tp"
    if kind == "firstperson":
        return "firstperson"
    if kind == "self_death":
        return "kill"  # caller must enforce explicit localhost + death_test consent
    raise ValueError("不允许执行任意控制台指令")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_tests(tests: list[dict]) -> str:
    if not tests:
        return "PENDING_NO_RUNTIME_EVIDENCE"
    if any(t["status"].startswith("FAIL") for t in tests):
        return "FAIL_REVIEW_REQUIRED"
    if all(t["status"] == "CAPTURED_PENDING_VISUAL_REVIEW" for t in tests):
        return "CAPTURED_PENDING_VISUAL_REVIEW"
    return "PARTIAL_CAPTURE_PENDING_REVIEW"
