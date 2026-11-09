"""Pure-Python safety primitives for the CS2 local-only workflow.

No shell execution, implicit permission escalation, server plugin installs, or base-game writes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath

NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,47}$")
MAP = re.compile(r"^[A-Za-z0-9_/-]{1,96}$")
SOURCE_EXT = {".vmdl", ".fbx", ".dmx", ".vmat", ".vtex", ".tga", ".png", ".jpg", ".jpeg", ".vnmskel", ".vnmgraph", ".vnmclip", ".vmap"}
GAME_EXT = {".vmdl_c", ".vmat_c", ".vtex_c", ".vnmskel_c", ".vnmgraph_c", ".vnmclip_c", ".vpk"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_config_path(config_file: Path, value: str):
    if not value:
        return None
    path = Path(value).expanduser()
    return (path if path.is_absolute() else config_file.parent / path).resolve()


def validate_name(addon):
    if not isinstance(addon, str) or not NAME.fullmatch(addon):
        raise ValueError("addon_name 必须为 2~48 位安全字母/数字/下划线/连字符，以字母开头")
    return addon


def validate_map(map_name):
    if not isinstance(map_name, str) or not MAP.fullmatch(map_name) or ".." in map_name.split("/"):
        raise ValueError("无效 map 名称")
    return map_name


def safe_relative(relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative or "\x00" in relative:
        raise ValueError(f"非法相对路径: {relative!r}")
    p = PurePosixPath(relative)
    if p.is_absolute() or any(part in (".", "..", "") for part in p.parts):
        raise ValueError(f"路径逃逸或无效路径: {relative!r}")
    return p


def addon_dirs(cs2_root, addon_name):
    root = Path(cs2_root).expanduser().resolve(strict=True)
    validate_name(addon_name)
    if not (root / "game" / "csgo" / "gameinfo.gi").is_file():
        raise ValueError("cs2_root 不是包含 game/csgo/gameinfo.gi 的 CS2 安装根目录")
    content_root = root / "content" / "csgo_addons" / addon_name
    game_root = root / "game" / "csgo_addons" / addon_name
    # User creates addon through Workshop Tools first; no blind creation or gameinfo mutation.
    if not content_root.is_dir() or not game_root.is_dir():
        raise ValueError("Addon 不存在。先在官方 Workshop Tools 中 Create New Addon")
    # Reject any symlink at or above the managed addon; never follow into base game files.
    for area_root in (content_root, game_root):
        candidate = area_root
        while candidate != root:
            if candidate.is_symlink():
                raise ValueError(f"Addon 路径包含符号链接，不允许写入: {candidate}")
            candidate = candidate.parent
        if not area_root.resolve().is_relative_to((root / ("content" if area_root == content_root else "game") / "csgo_addons").resolve()):
            raise ValueError("Addon 不在预期 csgo_addons 范围内")
    return {"content": content_root.resolve(), "game": game_root.resolve()}


def validated_destination(roots, area, relative):
    if area not in roots:
        raise ValueError(f"禁止写入的区域: {area}")
    rel = safe_relative(relative)
    ext_allowed = SOURCE_EXT if area == "content" else GAME_EXT
    if not any(str(rel).lower().endswith(suffix) for suffix in ext_allowed):
        raise ValueError(f"不允许写入该文件类型到 {area}: {relative}")
    base = roots[area]
    dst = base.joinpath(*rel.parts)
    # Resolve is symlink-aware even for not-yet-existing files.
    if not dst.resolve().is_relative_to(base):
        raise ValueError(f"目标通过符号链接逃逸 Addon: {dst}")
    if dst.is_symlink():
        raise ValueError(f"拒绝覆盖符号链接: {dst}")
    return dst


def prepare_file_plan(config_file, cfg):
    roots = addon_dirs(resolve_config_path(config_file, cfg["cs2_root"]), cfg["addon_name"])
    planned, seen = [], set()
    for entry in cfg.get("deploy_files", []):
        src = resolve_config_path(config_file, entry["source"])
        if not src.is_file() or src.is_symlink():
            raise ValueError(f"源文件不存在或是符号链接: {src}")
        area, rel = entry["area"], entry["relative_path"]
        dst = validated_destination(roots, area, rel)
        if dst in seen:
            raise ValueError(f"部署目标重复: {dst}")
        seen.add(dst)
        planned.append({"source": src, "destination": dst, "area": area, "relative_path": rel, "bytes": src.stat().st_size})
    return roots, planned


def sha256(path):
    dig = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            dig.update(chunk)
    return dig.hexdigest()


def deploy_transaction(plan, backup_dir):
    """Copy approved manifest atomically per-file, restore already-changed files on failure."""
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    history, results = [], []
    try:
        for index, item in enumerate(plan):
            src, dst = Path(item["source"]), Path(item["destination"])
            # Verify parent after creation, catching symlinks introduced since preflight.
            dst.parent.mkdir(parents=True, exist_ok=True)
            root = dst
            for _ in Path(item["relative_path"]).parts:
                root = root.parent
            if not dst.resolve().is_relative_to(root.resolve()) or dst.is_symlink():
                raise ValueError(f"写入时目标路径不安全: {dst}")
            if dst.is_file() and sha256(src) == sha256(dst):
                results.append({"source": str(src), "destination": str(dst), "sha256": sha256(dst), "backed_up": False, "status": "UNCHANGED"})
                continue
            old = dst.exists()
            prev = backup_dir / (f"{index:04d}.backup")
            if old:
                shutil.copy2(dst, prev)
            history.append((dst, prev if old else None))
            with tempfile.NamedTemporaryFile(dir=dst.parent, prefix=".cs2-stage-", delete=False) as f:
                tmp = Path(f.name)
            try:
                shutil.copy2(src, tmp)
                os.replace(tmp, dst)
            finally:
                tmp.unlink(missing_ok=True)
            results.append({"source": str(src), "destination": str(dst), "sha256": sha256(dst), "backed_up": old})
    except Exception:
        for dst, old in reversed(history):
            if old is None:
                dst.unlink(missing_ok=True)
            else:
                shutil.copy2(old, dst)
        raise
    return results


def gate_source_report(report, target, allow_pending_preview=False):
    """Pre-deploy source gate, NOT a runtime acceptance test."""
    problems = []
    if report.get("status") == "FAIL" or report.get("findings", {}).get("errors"):
        problems.append("Blender 源模型审计 FAIL")
    bbox = report.get("checks", {}).get("bounding_boxes", {})
    keys = ["static_comparison"] if target == "prop_preview" else ["static_comparison", "dynamic_comparison"]
    for key in keys:
        status = bbox.get(key, {}).get("status", "PENDING")
        if status == "FAIL":
            problems.append(f"{key} 超出可信参考边界")
        elif status == "PENDING" and (target != "prop_preview" or not allow_pending_preview):
            problems.append(f"{key} 尚无可信参考测量；不能自动通过")
    for name in ("mesh_integrity", "rig_stretch"):
        status = report.get("checks", {}).get(name, {}).get("status", "PENDING")
        if status == "FAIL":
            problems.append(f"{name} 检测 FAIL，禁止部署")
    if target == "player_runtime":
        prop = report.get("checks", {}).get("source_proportions", {}).get("status", "PENDING")
        if prop != "PASS":
            problems.append(f"原始四肢比例与动态抗拉伸验证未通过: {prop}")
        accessory_status = report.get("checks", {}).get("accessories", {}).get("status", "PENDING")
        if accessory_status != "PASS_PRELIMINARY":
            problems.append(f"装饰物骨骼/权重/绑定未通过: {accessory_status}")
        joint_status = report.get("checks", {}).get("joint_deformation", {}).get("status", "PENDING")
        if joint_status != "PASS_PRELIMINARY":
            problems.append(f"关节动态形变测试未通过: {joint_status}")
        for name, label in (("mesh_integrity", "网格开放边和动态接缝"),
                            ("rig_stretch", "骨骼伸缩/重复变形")):
            status = report.get("checks", {}).get(name, {}).get("status", "PENDING")
            if status != "PASS_PRELIMINARY":
                problems.append(f"{label}检查未通过: {status}")
        suite = report.get("checks", {}).get("animation_suite", {}).get("status", "PENDING")
        if suite not in ("PENDING_RUNTIME",):
            problems.append(f"尚未建立可信的动画覆盖清单或存在缺失片段: {suite}")
    if target == "player_runtime" and report.get("checks", {}).get("reference_rest_pose") != "USER_ATTESTED":
        problems.append("当前版本 CS2 Rest Pose 未校准")
    return problems
