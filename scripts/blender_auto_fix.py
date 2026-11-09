"""Conservative, reversible Blender weight normalization. Never reparent bones or guess missing weights.

Usage: blender -b input.blend --python blender_auto_fix.py -- --config profile.json
       --out fixed.blend --report fix_report.json [--apply]
Without --apply: produces only a dry-run report. With --apply: saves to a NEW .blend.
"""
import argparse
import json
import sys
import traceback
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_audit import choose_rig, choose_meshes, load_json


def cli():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--export-fbx", help="可选：导出修复后的 Mesh+Armature FBX 到新文件，ModelDoc 必须重新编译")
    return parser.parse_args(argv)


def make_plan(rig, meshes, conf):
    tol = float(conf["mesh_checks"].get("normalization_tolerance", 0.01))
    eps = float(conf["mesh_checks"].get("min_significant_weight", 0.0001))
    deform = {b.name for b in rig.data.bones if b.use_deform}
    plan, skipped = [], []
    for obj in meshes:
        if obj.library or obj.data.library or obj.override_library:
            skipped.append({"object": obj.name, "reason": "linked/library/override 对象不可安全修改"})
            continue
        for vertex in obj.data.vertices:
            valid = []
            for group in vertex.groups:
                if group.weight <= 0:
                    continue
                try:
                    group_name = obj.vertex_groups[group.group].name
                except IndexError:
                    skipped.append({"object": obj.name, "vertex": vertex.index, "reason": "顶点组索引无效"})
                    valid = []
                    break
                if group_name in deform:
                    valid.append((group_name, group.weight))
            total = sum(w for _, w in valid)
            if total <= eps:
                skipped.append({"object": obj.name, "vertex": vertex.index, "reason": "无有效变形权重，不能猜测骨骼"})
            elif abs(total - 1.0) > tol:
                plan.append({"object": obj.name, "vertex": vertex.index,
                             "previous_sum": total, "new_weights": {n: w / total for n, w in valid}})
    return plan, skipped


def main():
    args = cli()
    report = {"tool": "blender_auto_fix", "applied": False, "status": "PENDING", "actions": [], "skipped": [], "output_blend": None, "exported_fbx": None,
              "never_auto_fix": ["missing bones", "wrong parent or rest transforms", "zero-weight vertices", "hitbox/physics", "AG2 graph", "bbox overflow", "unknown groups", "topology", "excessive influences", "limb proportions", "pose stretch", "viewmodel skeleton", "death/ragdoll animation"]}
    try:
        conf = load_json(args.config)
        rig = choose_rig(conf)
        meshes = choose_meshes(conf, rig)
        plan, skipped = make_plan(rig, meshes, conf)
        report["actions"] = [{"object": r["object"], "vertex": r["vertex"], "previous_sum": r["previous_sum"]} for r in plan]
        report["skipped"] = skipped[:100]
        report["skipped_count"] = len(skipped)
        if args.apply:
            destination = Path(args.out).expanduser().resolve()
            source = Path(bpy.data.filepath).resolve()
            if destination.suffix.lower() != ".blend" or source == destination or destination.exists():
                raise ValueError("修复输出必须是全新的 .blend 文件，不允许覆盖输入或已有文件")
            if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            for item in plan:
                obj = bpy.data.objects[item["object"]]
                for group_name, new_weight in item["new_weights"].items():
                    obj.vertex_groups[group_name].add([item["vertex"]], new_weight, "REPLACE")
            destination.parent.mkdir(parents=True, exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=str(destination), check_existing=False)
            if args.export_fbx:
                fbx = Path(args.export_fbx).expanduser().resolve()
                if fbx.suffix.lower() != ".fbx" or fbx.exists():
                    raise ValueError("FBX 导出路径必须为新的 .fbx 文件")
                fbx.parent.mkdir(parents=True, exist_ok=True)
                bpy.ops.object.select_all(action="DESELECT")
                for selected in [rig, *meshes]:
                    selected.select_set(True)
                bpy.context.view_layer.objects.active = rig
                # Blender exporter availability is checked by real execution; never fake a successful file.
                bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={"ARMATURE", "MESH"},
                                         add_leaf_bones=False, bake_anim=False, use_mesh_modifiers=True,
                                         path_mode="AUTO")
                if not fbx.is_file() or fbx.stat().st_size == 0:
                    raise RuntimeError("Blender FBX 导出器未生成有效文件")
                report["exported_fbx"] = str(fbx)
            report["applied"] = True
            report["output_blend"] = str(destination)
            report["status"] = "APPLIED_NEW_COPY"
        else:
            report["status"] = "DRY_RUN"
    except Exception as exc:
        report["status"] = "FAIL"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    out = Path(args.report).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"CS2 auto-fix: {report['status']}; candidates={len(report['actions'])}")
    if report["status"] == "FAIL":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
