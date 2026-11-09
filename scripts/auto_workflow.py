"""Orchestrate local CS2 model scan -> conservative fix -> scan -> addon stage -> compile -> launch.

Default is non-destructive. --execute is mandatory for ALL writes to CS2 and process launches.
Does not install plugins, create AG2 graphs, modify gameinfo.gi or mark runtime tests as passed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from height_policy_core import validate_height_choice
from height_choice import configure_profile

from auto_workflow_core import (
    addon_dirs, deploy_transaction, gate_source_report, prepare_file_plan,
    read_json, resolve_config_path, safe_relative, sha256, validate_map,
    validated_destination, write_json,
)

SKILL = Path(__file__).resolve().parents[1]


def timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def get_config(path):
    config_file = Path(path).expanduser().resolve()
    cfg = read_json(config_file)
    if cfg.get("target") not in {"prop_preview", "player_runtime"}:
        raise ValueError("target 必须是 prop_preview 或 player_runtime")
    return config_file, cfg


def path_of(config_file, cfg, name):
    return resolve_config_path(config_file, cfg.get(name, ""))


def doctor(config_file, cfg):
    checks = {}
    blender = path_of(config_file, cfg, "blender_executable")
    model = path_of(config_file, cfg, "blend_file")
    root = path_of(config_file, cfg, "cs2_root")
    checks["blender_executable"] = bool(blender and blender.is_file())
    height = path_of(config_file, cfg, "height_profile")
    checks["height_profile"] = bool(height and height.is_file())
    checks["height_choice_confirmed"] = False
    if checks["height_profile"]:
        try:
            checks["height_choice_confirmed"] = validate_height_choice(read_json(height))[0] is None
        except (ValueError, TypeError, OSError):
            pass
    checks["blend_file"] = bool(model and model.is_file())
    source_fp = path_of(config_file, cfg, "firstperson_source_blend_file")
    checks["firstperson_source_blend_file"] = bool(source_fp and source_fp.is_file())
    checks["ag2_profile"] = bool(path_of(config_file, cfg, "ag2_profile") and path_of(config_file, cfg, "ag2_profile").is_file())
    checks["bbox_rules"] = bool(path_of(config_file, cfg, "bbox_rules") and path_of(config_file, cfg, "bbox_rules").is_file())
    for item in ("proportion_profile", "original_proportions", "animation_suite", "accessories", "joint_deformation", "mesh_integrity", "rig_stretch"):
        path = path_of(config_file, cfg, item)
        checks[item] = bool(path and path.is_file())
    checks["cs2_root"] = bool(root and (root / "game" / "csgo" / "gameinfo.gi").is_file())
    checks["addon_created_in_workshop_tools"] = False
    if checks["cs2_root"]:
        try:
            addon_dirs(root, cfg["addon_name"])
            checks["addon_created_in_workshop_tools"] = True
        except (OSError, ValueError, KeyError):
            pass
    checks["workshop_tools_launcher"] = bool(root and (root / "game/bin/win64/csgocfg.exe").is_file())
    checks["resource_compiler"] = bool(root and (root / "game/bin/win64/resourcecompiler.exe").is_file())
    checks["client_binary"] = bool(root and (root / "game/bin/win64/cs2.exe").is_file())
    dual = path_of(config_file, cfg, "dual_viewmodel")
    checks["dual_viewmodel"] = bool(dual and dual.is_file())
    extraction = path_of(config_file, cfg, "firstperson_extraction")
    checks["firstperson_extraction"] = bool(extraction and extraction.is_file())
    seam_config = path_of(config_file, cfg, "seam_repair")
    checks["seam_repair"] = bool(seam_config and seam_config.is_file())
    game_config = path_of(config_file, cfg, "game_test_config")
    checks["game_test_config"] = bool(game_config and game_config.is_file())
    return checks



def ensure_height_choice_before_audit(config_file, cfg, *, allow_interactive=True):
    """Mandatory user choice BEFORE Blender measures height or anything gets modified.

    Interactive terminal: ask and persist an explicit choice to *.local.json.
    Headless/CI: fail closed with instructions instead of silently assuming agent size.
    """
    if cfg.get("target") != "player_runtime":
        return {"status": "NOT_REQUIRED_PROP_PREVIEW"}
    profile_file = path_of(config_file, cfg, "height_profile")
    if not profile_file or not profile_file.is_file():
        raise ValueError("NEEDS_HEIGHT_CHOICE: 请先复制 height_profile.humanoid/nonhumanoid.example.json 为 *.local.json")
    profile = read_json(profile_file)
    error, target, mode = validate_height_choice(profile)
    if error and error.startswith('NEEDS_HEIGHT_CHOICE') and allow_interactive and sys.stdin.isatty():
        print('开始尺寸检测前，必须由你选择：默认探员等高 / 自定义目标高度 / 全身等比例缩放 / 保持原高。', flush=True)
        configure_profile(profile_file, interactive=True, save=True)
        profile = read_json(profile_file)
        error, target, mode = validate_height_choice(profile)
    if error:
        raise ValueError('NEEDS_HEIGHT_CHOICE: ' + error +
            '。请先在交互终端运行 python scripts/height_choice.py --profile "' + str(profile_file) +
            '" --save；自动化模式需明确 --mode ... --confirm --save。')
    return {"status": "USER_CONFIRMED", "model_type": profile['model_type'],
            "mode": mode, "target_body_height": target,
            "note": "只做尺寸审计和统一缩放建议；不自动修改人物、四肢或装饰物。"}


def verify_height_report_matches_decision(report, decision):
    """Reject a previous height audit if the user has since changed the plan."""
    if decision.get('status') == 'NOT_REQUIRED_PROP_PREVIEW':
        return
    measured = report.get('checks', {}).get('source_height', {})
    if measured.get('selection_confirmed') is not True:
        raise ValueError('源模型尺寸审计没有已确认的高度选择；不能复用旧报告')
    if measured.get('height_choice_mode') != decision.get('mode'):
        raise ValueError('高度策略已变更，请重新运行 Blender 主体高度审计')
    try:
        expected = float(decision['target_body_height'])
        audited = float(measured['target_body_height'])
    except (KeyError, ValueError, TypeError):
        raise ValueError('尺寸报告缺少目标高度的原始证据')
    if abs(audited / expected - 1.0) > 1e-6:
        raise ValueError('目标高度已变更；旧模型审计结果不能用于部署')


def run_process(command, *, cwd=None, log_path=None, expected=(0,)):
    result = subprocess.run([str(v) for v in command], cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, errors="replace", check=False)
    if log_path:
        p = Path(log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(result.stdout or "", encoding="utf-8")
    if result.returncode not in expected:
        raise RuntimeError(f"命令运行失败 exit={result.returncode}; 日志：{log_path}")
    return result.returncode


def execute_blender(config_file, cfg, script_name, input_blend, args, logfile, expected=(0, 2)):
    blender = path_of(config_file, cfg, "blender_executable")
    if not blender or not blender.is_file():
        raise ValueError("Blender 不存在；检查配置 blender_executable")
    command = [blender, "-b", input_blend, "--python", SKILL / "scripts" / script_name, "--", *args]
    return run_process(command, log_path=logfile, expected=expected)


def do_audit(config_file, cfg, blend, folder, suffix=""):
    profile = path_of(config_file, cfg, "ag2_profile")
    bbox = path_of(config_file, cfg, "bbox_rules")
    if not profile or not bbox or not profile.is_file() or not bbox.is_file():
        raise ValueError("ag2_profile / bbox_rules 文件不存在")
    report = folder / f"blender_audit{suffix}.json"
    optional = []
    for name, flag in (("proportion_profile", "--proportions"),
                       ("original_proportions", "--baseline"),
                       ("animation_suite", "--animation-suite")):
        path = path_of(config_file, cfg, name)
        if path and path.is_file():
            optional.extend([flag, path])
        elif cfg["target"] == "player_runtime":
            raise ValueError(f"玩家模型必须配置并提供 {name}；不得按默认探员拉伸")
    if not cfg.get("_skip_height_check"):
        height_file = path_of(config_file, cfg, "height_profile")
        if height_file and height_file.is_file():
            optional.extend(["--height-profile", height_file])
        elif cfg["target"] == "player_runtime":
            raise ValueError("玩家世界模型缺少 height_profile；不得将装饰物计入身高")
    for name, flag in (("accessories", "--accessories"), ("joint_deformation", "--joint-deformation"),
                       ("mesh_integrity", "--mesh-integrity"), ("rig_stretch", "--rig-stretch")):
        path = path_of(config_file, cfg, name)
        if path and path.is_file():
            optional.extend([flag, path])
        elif cfg["target"] == "player_runtime":
            raise ValueError(f"玩家模型必须提供 {name} 来核对装饰物及各关节动作形变")
    execute_blender(config_file, cfg, "blender_audit.py", blend,
                    ["--config", profile, "--bbox", bbox, "--out", report, *optional],
                    folder / f"blender_audit{suffix}.log")
    if not report.is_file():
        raise RuntimeError("Blender 未输出审计报告，无法继续")
    return report, read_json(report)


def do_extract_firstperson(config_file, cfg, input_blend, folder, apply):
    conf = path_of(config_file, cfg, "firstperson_extraction")
    if not conf or not conf.is_file():
        raise ValueError("--extract-viewmodel 需要 firstperson_extraction 配置，且须手工标记原模型双臂掩码")
    output = folder / "firstperson_cut_preview.blend"
    report = folder / "firstperson_extraction.json"
    execute_blender(config_file, cfg, "blender_extract_firstperson.py", input_blend,
                    ["--config", conf, "--out", output, "--report", report,
                     *(["--apply"] if apply else [])], folder / "firstperson_extract.log", expected=(0,))
    result = read_json(report)
    if result.get("status") == "FAIL" or (apply and not output.is_file()):
        raise RuntimeError("原人物第一人称手臂提取失败；不会修改原模型")
    return result


def do_viewmodel_contract(config_file, cfg, view_file, folder):
    conf = path_of(config_file, cfg, "dual_viewmodel")
    if not conf or not conf.is_file():
        raise ValueError("缺少 dual_viewmodel 配置")
    report = folder / "firstperson_final_audit.json"
    execute_blender(config_file, cfg, "blender_viewmodel_final_audit.py", view_file,
                    ["--config", conf, "--out", report], folder / "firstperson_final_audit.log",
                    expected=(0, 2))
    if not report.is_file():
        raise RuntimeError("第一人称独立骨架审计没有输出")
    return read_json(report)


def ensure_paired_viewmodel(config_file, cfg, report=None):
    from dual_viewmodel_gate import inspect_pair
    problems = inspect_pair(config_file, cfg, report)
    if problems:
        raise ValueError("双视角部署门禁失败: " + "; ".join(problems))


def do_accessory_setup(config_file, cfg, input_blend, folder, apply):
    accessory = path_of(config_file, cfg, "accessories")
    if not accessory or not accessory.is_file():
        raise ValueError("--rig-accessories 必须设置有效的 accessories 配置文件")
    output = folder / "accessories_prepared.blend"
    report = folder / "accessory_setup_report.json"
    execute_blender(config_file, cfg, "blender_accessory_setup.py", input_blend,
                    ["--config", accessory, "--out", output, "--report", report,
                     *(["--apply"] if apply else [])],folder / "accessory_setup.log",expected=(0,))
    result = read_json(report)
    return (output if apply else input_blend), result


def do_seam_repair(config_file, cfg, input_blend, folder, apply):
    seam_cfg = path_of(config_file, cfg, "seam_repair")
    if not seam_cfg or not seam_cfg.is_file():
        raise ValueError("--repair-seams 需要 seam_repair 配置与人工核准的精确顶点对")
    output = folder / "seam_repaired.blend"
    report = folder / "seam_repair_report.json"
    execute_blender(config_file, cfg, "blender_seam_repair.py", input_blend,
                    ["--config", seam_cfg, "--out", output, "--report", report,
                     *(["--apply"] if apply else [])],
                    folder / "seam_repair.log", expected=(0,))
    info = read_json(report)
    if info.get("status") == "FAIL" or apply and not output.is_file():
        raise RuntimeError("接缝修复失败或没有生成新 .blend")
    return (output if apply else input_blend), info


def do_fix(config_file, cfg, input_blend, folder, apply):
    target = folder / "auto_fixed.blend"
    report = folder / "auto_fix_report.json"
    export_cfg = cfg.get("auto_export_fbx", {})
    export_path = folder / "corrected_model.fbx" if apply and export_cfg.get("enabled", False) else None
    execute_blender(config_file, cfg, "blender_auto_fix.py", input_blend,
                    ["--config", path_of(config_file, cfg, "ag2_profile"),
                     "--out", target, "--report", report, *(["--apply"] if apply else []),
                     *(["--export-fbx", export_path] if export_path else [])],
                    folder / "auto_fix.log", expected=(0,))
    info = read_json(report)
    if info.get("status") == "FAIL":
        raise RuntimeError("自动纠错失败")
    return (target if apply else input_blend), info


def do_deploy(config_file, cfg, folder, execute, overrides=None):
    roots, planned = prepare_file_plan(config_file, cfg)
    for relative, source_path in (overrides or {}).items():
        matches = [row for row in planned if row["area"] == "content" and row["relative_path"] == relative]
        if len(matches) != 1:
            raise ValueError("自动导出 FBX 必须在 deploy_files 中有对应的 content 目标: " + relative)
        matches[0]["source"] = Path(source_path)
        matches[0]["bytes"] = Path(source_path).stat().st_size
    record = {"status": "DRY_RUN" if not execute else "DEPLOYED_TO_LOCAL_ADDON",
              "files": [{"from": str(row["source"]), "to": str(row["destination"]), "bytes": row["bytes"]} for row in planned],
              "note": "这里仅复制已明确声明的素材到用户的 Addon；不等于模型编译成功或玩家运行时可用。"}
    if not planned:
        raise ValueError("deploy_files 为空；没有可部署的文件")
    if execute:
        record["files"] = deploy_transaction(planned, folder / "backups")
    write_json(folder / "deploy_result.json", record)
    return roots, record


def do_compile(config_file, cfg, folder, execute):
    root = path_of(config_file, cfg, "cs2_root")
    roots = addon_dirs(root, cfg["addon_name"])
    compiler = root / "game/bin/win64/resourcecompiler.exe"
    if not compiler.is_file():
        raise ValueError("缺少 resourcecompiler.exe；请安装 CS2 Workshop Tools")
    sources = cfg.get("compile_sources", [])
    if not sources:
        raise ValueError("compile_sources 为空。先用 ModelDoc 创建并保存 .vmdl，再填写待编译路径")
    commands = []
    for rel in sources:
        path = validated_destination(roots, "content", rel)
        if path.suffix.lower() not in {".vmdl", ".vmat", ".vtex", ".vnmskel", ".vnmgraph", ".vnmclip"}:
            raise ValueError(f"该资源需要在 ModelDoc/Hammer 手动处理: {rel}")
        if execute and not path.is_file():
            raise ValueError(f"编译源文件不存在: {path}")
        commands.append([str(compiler), "-i", str(path)])
    outcome = {"status": "DRY_RUN" if not execute else "COMPILE_COMMANDS_EXECUTED",
               "commands": commands, "compiled_outputs_present": {}}
    if execute:
        for index, command in enumerate(commands):
            run_process(command, cwd=compiler.parent, log_path=folder / f"compile_{index}.log")
        for rel in cfg.get("required_compiled_files", []):
            dest = validated_destination(roots, "game", rel)
            outcome["compiled_outputs_present"][rel] = dest.is_file()
        if not outcome["compiled_outputs_present"] or not all(outcome["compiled_outputs_present"].values()):
            outcome["status"] = "FAIL_UNVERIFIED_COMPILED_OUTPUT"
    write_json(folder / "compile_result.json", outcome)
    if outcome["status"] == "FAIL_UNVERIFIED_COMPILED_OUTPUT":
        raise RuntimeError("编译命令已执行，但必需的编译产物未全部出现")
    return outcome


def get_launch_command(config_file, cfg):
    root = path_of(config_file, cfg, "cs2_root")
    if not root or not (root / "game/csgo/gameinfo.gi").is_file():
        raise ValueError("缺少有效 cs2_root")
    mode = cfg.get("launch_mode", "tools")
    if mode == "tools":
        exe = root / "game/bin/win64/csgocfg.exe"
        # Launcher GUI requires user to select the addon and click Launch Tools.
        cmd = [str(exe)]
    elif mode == "dedicated_server":
        exe = path_of(config_file, cfg, "server_executable") or (root / "game/bin/win64/cs2.exe")
        map_name = validate_map(cfg.get("server_map", "de_dust2"))
        port = int(cfg.get("server_port", 27015))
        if not 1024 <= port <= 65535:
            raise ValueError("server_port 必须为 1024~65535")
        cmd = [str(exe), "-dedicated", "-console", "-port", str(port), "+map", map_name]
    else:
        raise ValueError("仅支持 launch_mode=tools 或 dedicated_server；不提供非官方大厅换模")
    if not exe.is_file():
        raise ValueError(f"启动程序不存在: {exe}")
    return cmd


def do_launch(config_file, cfg, folder, execute):
    cmd = get_launch_command(config_file, cfg)
    if cfg.get("launch_mode") == "dedicated_server":
        # A running server is not proof of player-model mounting, but require build outputs before launch.
        roots = addon_dirs(path_of(config_file, cfg, "cs2_root"), cfg["addon_name"])
        required = cfg.get("required_compiled_files", [])
        if not required:
            raise ValueError("启动自定义模型专用服前必须配置 required_compiled_files")
        missing = [rel for rel in required if not validated_destination(roots, "game", rel).is_file()]
        if execute and missing:
            raise ValueError("缺少编译产物，停止启动: " + ", ".join(missing))
    out = {"status": "DRY_RUN", "command": cmd, "note": "启动外部进程不代表资源加载成功；必须查看日志和游戏画面。"}
    if execute:
        # Never shell=True. Avoid inherited blocking pipes and never suppress errors.
        with (folder / "launch_stdout.log").open("ab") as output:
            p = subprocess.Popen(cmd, stdout=output, stderr=subprocess.STDOUT,
                                 cwd=str(Path(cmd[0]).parent), shell=False,
                                 creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        time.sleep(0.4)
        code = p.poll()
        out.update({"status": "PROCESS_STARTED_UNVERIFIED" if code is None else "PROCESS_EXITED_EARLY",
                    "pid": p.pid, "early_exit_code": code})
    write_json(folder / "launch_result.json", out)
    if out["status"] == "PROCESS_EXITED_EARLY":
        raise RuntimeError("启动程序提前退出，查看 launch_stdout.log")
    return out


def parser():
    ap = argparse.ArgumentParser(description="CS2 本地模型自动检查/修复/部署/启动（仅当前机器）")
    ap.add_argument("action", choices=["doctor", "run", "deploy", "compile", "launch"])
    ap.add_argument("--config", required=True, help="项目特定配置 JSON")
    ap.add_argument("--execute", action="store_true", help="允许写入新的修复文件、部署到 Addon、编译和启动进程")
    ap.add_argument("--fix", action="store_true", help="run 时执行安全权重归一化并复检")
    ap.add_argument("--repair-seams", action="store_true", help="按人工核准顶点对尝试安全焊接到新 .blend，不做盲目补洞")
    ap.add_argument("--extract-viewmodel", action="store_true", help="从完整原始人物按人工 FP_KEEP 顶点掩码生成手臂、衣袖预览副本；仍需独立重绑、动画与审核")
    ap.add_argument("--viewmodel-audit", help="单独 deploy/compile/launch 必须提供的第一人称骨架审计 JSON")
    ap.add_argument("--rig-accessories", action="store_true", help="依明确标定坐标为装饰物新增辅助骨骼并另存模型；需人工检查动态骨骼权重")
    ap.add_argument("--deploy", action="store_true", help="run 时复制显式列出的 Addon 文件")
    ap.add_argument("--compile", action="store_true", help="run 时编译可批处理的 Source 2 资源")
    ap.add_argument("--launch", action="store_true", help="run 时启动 Workshop Tools GUI 或私人专用服")
    ap.add_argument("--game-test", action="store_true", help="run 时在本机私人服务器中启动客户端、操作游戏并采样截图/日志（需单独授权和 GUI 依赖）")
    ap.add_argument("--allow-pending-preview", action="store_true", help="仅道具预览可显式放宽缺少参考 AABB；不能用于玩家模型")
    ap.add_argument("--audit", help="单独 deploy/compile/launch 的已有 Blender 审计 JSON（非默认从网络/机器猜测）")
    ap.add_argument("--no-height-prompt", action="store_true", help="无交互模式：缺少用户缩放选择时直接阻止检测，而不是读取键盘输入")
    ap.add_argument("--out-dir", help="可选报告目录；默认自动生成独立时间戳目录")
    return ap


def main():
    args = parser().parse_args()
    cfg_file, cfg = get_config(args.config)
    report_dir = (Path(args.out_dir).expanduser().resolve() if args.out_dir else SKILL / "reports" / f"run_{timestamp()}_{os.getpid()}")
    report_dir.mkdir(parents=True, exist_ok=False)
    meta = {"status": "PENDING", "action": args.action, "executed": bool(args.execute),
            "target": cfg["target"], "reports_dir": str(report_dir), "steps": {},
            "important": "AUTO-DEPLOYED/PROCESS_STARTED != Runtime PASS. Hitbox、Physics、AG2 与玩家实体须实际测试并提供证据。"}
    try:
        health = doctor(cfg_file, cfg)
        meta["steps"]["doctor"] = health
        if args.action == "doctor":
            meta["status"] = "DOCTOR_COMPLETE"
        else:
            # P0 decision gate happens BEFORE first Blender audit, accessory setup,
            # geometry edits, or any deploy/compile/launch commands.
            height_decision = ensure_height_choice_before_audit(
                cfg_file, cfg, allow_interactive=not args.no_height_prompt)
            meta["steps"]["height_choice_before_size_audit"] = height_decision
            if args.action == "run":
                required = ["blender_executable", "blend_file", "ag2_profile", "bbox_rules"]
                if cfg["target"] == "player_runtime":
                    required.extend(["proportion_profile", "original_proportions", "animation_suite", "accessories", "joint_deformation", "height_profile"])
                for item in required:
                    if not health[item]:
                        raise ValueError(f"预检失败: {item}")
                blend_file = path_of(cfg_file, cfg, "blend_file")
                if args.rig_accessories:
                    if args.execute and (args.deploy or args.compile or args.launch or args.game_test) and not args.fix:
                        raise ValueError("一键新建装饰物骨骼后若要部署，必须同时 --fix --deploy 并重新导出/编译新 FBX")
                    blend_file, accessory_setup = do_accessory_setup(cfg_file, cfg, blend_file, report_dir, args.execute)
                    meta["steps"]["accessory_setup"] = {"status":accessory_setup["status"], "file":accessory_setup.get("output_blend"),
                                                          "manual_weights_pending":accessory_setup.get("manual_weights_pending",[])}
                first, report = do_audit(cfg_file, cfg, blend_file, report_dir, "_before")
                meta["steps"]["audit_before"] = {"status": report.get("status"), "file": str(first),
                    "source_height": report.get("checks", {}).get("source_height", {}).get("status", "PENDING")}
                if args.extract_viewmodel:
                    if cfg["target"] != "player_runtime":
                        raise ValueError("--extract-viewmodel 只适用于 player_runtime")
                    if args.fix or args.repair_seams or args.rig_accessories or args.deploy or args.compile or args.launch or args.game_test:
                        raise ValueError("裁剪手模必须单独成轮：先修完整角色再提取；随后人工完成独立骨架重定向和审核才可部署")
                    source_fp = path_of(cfg_file, cfg, "firstperson_source_blend_file")
                    if not source_fp or not source_fp.is_file():
                        raise ValueError("必须填写 firstperson_source_blend_file：复制完整原始模型的独立带 FP_KEEP 掩码副本，不能随意从已拉伸的世界模型裁剪")
                    result = do_extract_firstperson(cfg_file, cfg, source_fp, report_dir, args.execute)
                    meta["steps"]["firstperson_extraction"] = result
                    meta["status"] = "VIEWMODEL_EXTRACTION_PENDING_RIGGING" if args.execute else "VIEWMODEL_EXTRACTION_DRY_RUN"
                view_contract = None
                if cfg["target"] == "player_runtime":
                    if cfg.get("viewmodel_blend_file") and not args.extract_viewmodel:
                        names = {"blend_file": "viewmodel_blend_file",
                                 "ag2_profile": "viewmodel_ag2_profile",
                                 "bbox_rules": "viewmodel_bbox_rules",
                                 "proportion_profile": "viewmodel_proportion_profile",
                                 "original_proportions": "viewmodel_original_proportions"}
                        vcfg = dict(cfg)
                        vcfg["_skip_height_check"] = True  # FPS 裁剪手臂不按完整身高比较
                        for real_name, view_name in names.items():
                            if not cfg.get(view_name):
                                raise ValueError(f"单独检测第一人称手模缺少 {view_name}")
                            vcfg[real_name] = cfg[view_name]
                        for local_name, view_name in (("accessories","viewmodel_accessories"),
                                                      ("joint_deformation","viewmodel_joint_deformation"),
                                                      ("mesh_integrity", "viewmodel_mesh_integrity"),
                                                      ("rig_stretch", "viewmodel_rig_stretch")):
                            if not cfg.get(view_name):
                                raise ValueError(f"第一人称手模缺少 {view_name} 检查配置")
                            vcfg[local_name] = cfg[view_name]
                        view_file = path_of(cfg_file, vcfg, "blend_file")
                        if not view_file or not view_file.is_file():
                            raise ValueError("第一人称手模 .blend 文件不存在")
                        _, view_report = do_audit(cfg_file, vcfg, view_file, report_dir, "_viewmodel")
                        if cfg.get("dual_viewmodel"):
                            view_contract = do_viewmodel_contract(cfg_file, cfg, view_file, report_dir)
                            meta["steps"]["firstperson_contract"] = {"status": view_contract.get("status"),
                                "file": str(report_dir / "firstperson_final_audit.json")}

                        meta["steps"]["viewmodel_audit"] = {"status": view_report.get("status"),
                          "source_proportions": view_report.get("checks", {}).get("source_proportions", {}).get("status"),
                          "file": str(report_dir / "blender_audit_viewmodel.json")}
                        if (view_report.get("status") == "FAIL"
                            or view_report.get("checks", {}).get("source_proportions", {}).get("status") != "PASS"
                            or view_report.get("checks", {}).get("accessories", {}).get("status") != "PASS_PRELIMINARY"
                            or view_report.get("checks", {}).get("joint_deformation", {}).get("status") != "PASS_PRELIMINARY"
                            or view_report.get("checks", {}).get("mesh_integrity", {}).get("status") != "PASS_PRELIMINARY"
                            or view_report.get("checks", {}).get("rig_stretch", {}).get("status") != "PASS_PRELIMINARY"):
                            raise ValueError("第一人称手模源比例/绑定检测未通过，停止自动部署")
                    else:
                        meta["steps"]["viewmodel_audit"] = {"status": "PENDING_NO_VIEWMODEL_SOURCE",
                            "note": "没有用户提供的第一人称源手模；游戏内截图和后续人工验收仍为必须。"}
                # v6 conservative seam repair happens AFTER before-audit; never weld
                # unreviewed geometry, and NEVER deploy a repaired .blend before re-export.
                if args.repair_seams:
                    if args.execute and (args.deploy or args.compile or args.launch or args.game_test) and not args.fix:
                        raise ValueError("修复网格后需要 --fix 重新导出最终 FBX 并运行部署验证")
                    blend_file, seam_report = do_seam_repair(cfg_file, cfg, blend_file, report_dir, args.execute)
                    meta["steps"]["seam_repair"] = {"status": seam_report["status"], "output_blend": seam_report.get("output_blend"),
                                                     "pairs_reviewed": len(seam_report.get("repairs",[]))}
                export_overrides = {}
                if args.fix and args.execute and (args.deploy or args.compile or args.launch or args.game_test):
                    export_cfg = cfg.get("auto_export_fbx", {})
                    if not export_cfg.get("enabled") or not export_cfg.get("modeldoc_fbx_reference_verified"):
                        raise ValueError("自动修复后拟部署/编译/启动时，必须启用 auto_export_fbx 并确认 ModelDoc 引用导出目标；否则修复不会进入游戏")
                    if (args.compile or args.launch or args.game_test) and not args.deploy:
                        raise ValueError("自动修复后编译/启动/游戏验证必须同时 --deploy 新导出的 FBX")
                    if args.game_test and not args.compile:
                        raise ValueError("自动修复后立即游戏验证必须同时 --compile，避免检查的是旧编译模型")
                if args.fix:
                    blend_file, fix_result = do_fix(cfg_file, cfg, blend_file, report_dir, args.execute)
                    meta["steps"]["fix"] = {"status": fix_result["status"], "candidates": len(fix_result["actions"]),
                                            "output_blend": fix_result.get("output_blend"), "exported_fbx": fix_result.get("exported_fbx")}
                    if args.execute and args.deploy:
                        exp = cfg["auto_export_fbx"]
                        relative = str(safe_relative(exp["relative_path"]))
                        exported = fix_result.get("exported_fbx")
                        if not exported or not Path(exported).is_file():
                            raise ValueError("自动纠错后 FBX 未成功导出；停止部署，避免发布旧模型")
                        export_overrides[relative] = exported
                # No need to re-run the expensive animated geometry audit if source did not change.
                if (args.fix or args.repair_seams) and args.execute:
                    after, report = do_audit(cfg_file, cfg, blend_file, report_dir, "_after")
                    meta["steps"]["audit_after"] = {"status": report.get("status"), "file": str(after)}
                else:
                    after = first
                    meta["steps"]["audit_after"] = {"status": report.get("status"), "file": str(first), "reused_unchanged_input": True}
                from issue_triage import build_triage
                write_json(report_dir / "issues_prioritized.json", build_triage(report))
                meta["steps"]["issue_triage"] = str(report_dir / "issues_prioritized.json")
            else:
                if not args.audit:
                    raise ValueError("独立 deploy/compile/launch 必须提供 --audit 指向真实本地 Blender 审计报告")
                report = read_json(Path(args.audit).expanduser())
                meta["steps"]["audit_supplied"] = args.audit
            # Protect against stale reports when the user changes target height
            # after the last Blender measurement.
            if cfg["target"] == "player_runtime" and (args.action in {"deploy", "compile", "launch"} or
                (args.action == "run" and (args.deploy or args.compile or args.launch or args.game_test))):
                verify_height_report_matches_decision(report, height_decision)
            if cfg["target"] == "player_runtime" and (args.action in {"deploy", "compile", "launch"} or
                (args.action == "run" and (args.deploy or args.compile or args.launch or args.game_test))):
                if args.action != "run":
                    if not args.viewmodel_audit:
                        raise ValueError("独立 deploy/compile/launch 还必须提供 --viewmodel-audit")
                    view_contract = read_json(Path(args.viewmodel_audit).expanduser())
                ensure_paired_viewmodel(cfg_file, cfg, view_contract)
            if args.action == "deploy" or (args.action == "run" and args.deploy):
                gate = gate_source_report(report, cfg["target"], args.allow_pending_preview)
                if gate:
                    raise ValueError("部署前检查未通过: " + "; ".join(gate))
                _, record = do_deploy(cfg_file, cfg, report_dir, args.execute,
                                      export_overrides if args.action == "run" else None)
                meta["steps"]["deploy"] = record["status"]
            if args.action == "compile" or (args.action == "run" and args.compile):
                gate = gate_source_report(report, cfg["target"], args.allow_pending_preview)
                if gate:
                    raise ValueError("编译前检查未通过: " + "; ".join(gate))
                result = do_compile(cfg_file, cfg, report_dir, args.execute)
                meta["steps"]["compile"] = result["status"]
            if args.action == "launch" or (args.action == "run" and args.launch):
                gate = gate_source_report(report, cfg["target"], args.allow_pending_preview)
                if gate:
                    raise ValueError("启动前检查未通过: " + "; ".join(gate))
                # Do not start the server if the user requested compilation that failed.
                result = do_launch(cfg_file, cfg, report_dir, args.execute)
                meta["steps"]["launch"] = result["status"]
            if args.action == "run" and args.game_test:
                if cfg.get("target") != "player_runtime":
                    raise ValueError("--game-test 只适用于 player_runtime 模型")
                if args.launch and cfg.get("launch_mode") != "dedicated_server":
                    raise ValueError("--game-test 与 --launch 联用时必须选择 dedicated_server 模式")
                game_config = path_of(cfg_file, cfg, "game_test_config")
                if not game_config or not game_config.is_file():
                    raise ValueError("缺少 game_test_config：请复制 game_test.example.json 并填写私人环境")
                # Important: compile outputs and launching a server do NOT prove client content is mounted.
                from game_qa import run_from_files
                result = run_from_files(str(game_config), str(path_of(cfg_file, cfg, "cs2_root")),
                                        str(report_dir / "game_qa"), execute=args.execute)
                meta["steps"]["game_test"] = {"status": result["status"],
                                                  "report": str(report_dir / "game_qa" / "game_qa_report.json")}
                if result["status"] == "BLOCKED":
                    raise RuntimeError("游戏自动验收阶段已停止，查看 game_qa/game_qa_report.json")
            if not args.extract_viewmodel:
                meta["status"] = "STEPS_EXECUTED_RUNTIME_PENDING" if args.execute else "DRY_RUN_COMPLETE"
    except Exception as exc:
        meta["status"] = "BLOCKED"
        meta["error"] = str(exc)
    finally:
        write_json(report_dir / "workflow_result.json", meta)
    print(json.dumps({"status": meta["status"], "report": str(report_dir / "workflow_result.json"),
                      "error": meta.get("error")}, ensure_ascii=False, indent=2))
    if meta["status"] == "BLOCKED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
