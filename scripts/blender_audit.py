"""Read-only Blender rig, mesh, weight and bounds audit.

Run:
  blender -b model.blend --python scripts/blender_audit.py -- \
    --config config/ag2_profile.example.json \
    --bbox config/bbox_rules.example.json --out reports/blender_audit.json

This file is intentionally not importable in ordinary CPython: it requires bpy.
"""
import argparse
import json
import math
import sys
import traceback
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bbox_math import make_box, union_boxes, compare_box


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="CS2 Blender read-only model audit")
    parser.add_argument("--config", required=True)
    parser.add_argument("--bbox", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--proportions", help="calibrated original-to-CS2 proportions profile")
    parser.add_argument("--baseline", help="captured ORIGINAL character lengths")
    parser.add_argument("--animation-suite", help="world/view model animation coverage inventory")
    parser.add_argument("--accessories", help="explicit decorative mesh and support-bone chains")
    parser.add_argument("--joint-deformation", help="joint deformation regions, limits, and action sampling")
    parser.add_argument("--mesh-integrity", help="mesh boundary/opening and dynamic seam pair checks")
    parser.add_argument("--rig-stretch", help="bone stretch controls and pose-length diagnostics")
    parser.add_argument("--height-profile", help="v8 主体高度检查；装饰物不计入高度")
    return parser.parse_args(argv)


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def findings_bucket():
    return {"errors": [], "warnings": [], "info": []}


def add(report, severity, code, message, **details):
    report["findings"][severity].append({"code": code, "message": message, **details})


def choose_rig(profile):
    target = profile.get("target_armature")
    if target:
        rig = bpy.data.objects.get(target)
        if rig is None or rig.type != "ARMATURE":
            raise ValueError(f"找不到指定 Armature: {target}")
        return rig
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(rigs) != 1:
        raise ValueError(f"场景包含 {len(rigs)} 个 Armature；请设置 target_armature")
    return rigs[0]


def choose_meshes(profile, rig):
    exact = profile.get("object_names") or []
    if exact:
        meshes = []
        for name in exact:
            obj = bpy.data.objects.get(name)
            if obj is None or obj.type != "MESH":
                raise ValueError(f"object_names 包含不存在的网格: {name}")
            meshes.append(obj)
        return meshes

    meshes = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.get("cs2_collision_only", False):
            continue
        modifiers = [mod for mod in obj.modifiers if mod.type == "ARMATURE"]
        if obj.parent == rig or any(mod.object == rig for mod in modifiers):
            meshes.append(obj)
    return meshes


def check_skeleton(rig, profile, report):
    bones = rig.data.bones
    expected = profile["required_parent_map"]
    missing, wrong_parent = [], []
    for name, parent in expected.items():
        bone = bones.get(name)
        if bone is None:
            missing.append(name)
            add(report, "errors", "MISSING_BONE", f"缺少关键骨骼 {name}", bone=name)
            continue
        actual = bone.parent.name if bone.parent else None
        if actual != parent:
            wrong_parent.append({"bone": name, "expected": parent, "actual": actual})
            add(report, "errors", "BONE_PARENT", f"{name}: parent={actual}; 期望={parent}")
    zero_len = [b.name for b in bones if b.length < 0.000001]
    if zero_len:
        add(report, "warnings", "BONE_LENGTH", "骨骼长度接近零", samples=zero_len[:20])
    roots = [b.name for b in bones if b.parent is None]
    if roots != ["root_motion"]:
        add(report, "warnings", "ROOT_BONES", "root_motion 不是唯一根骨骼；确认是否为自定义辅助骨骼", roots=roots)
    if not profile.get("reference_rest_transforms_validated"):
        add(report, "warnings", "REST_NOT_CALIBRATED", "未用当前 CS2 参考模型校准 Rest Matrix/坐标轴")
    return {
        "rig": rig.name, "bones": len(bones), "roots": roots,
        "missing": missing, "wrong_parent": wrong_parent,
        "rest_transforms_validated": bool(profile.get("reference_rest_transforms_validated")),
    }


def check_mesh(obj, rig, profile, report):
    settings = profile["mesh_checks"]
    mesh = obj.data
    modifiers = [m for m in obj.modifiers if m.type == "ARMATURE" and m.object == rig]
    if settings.get("require_armature_modifier", True) and not modifiers:
        add(report, "errors", "NO_ARMATURE_MODIFIER", "网格未绑定目标 Armature 修改器", mesh=obj.name)
    if settings.get("require_uv", True) and not mesh.uv_layers:
        add(report, "warnings", "NO_UV", "网格无 UV", mesh=obj.name)
    if settings.get("require_material", True) and not mesh.materials:
        add(report, "warnings", "NO_MATERIAL", "网格无材质", mesh=obj.name)
    if obj.matrix_world.determinant() < 0:
        add(report, "warnings", "NEGATIVE_DETERMINANT", "对象变换为镜像/反射", mesh=obj.name)
    if any(abs(s - 1.0) > 0.0001 for s in obj.scale):
        severity = "errors" if settings.get("require_applied_scale", False) else "warnings"
        add(report, severity, "UNAPPLIED_SCALE", "对象缩放未应用；核对参考单位", mesh=obj.name, scale=list(obj.scale))

    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        non_manifold = sum(1 for edge in bm.edges if not edge.is_manifold)
        degenerate_faces = sum(1 for face in bm.faces if face.calc_area() < 1e-12)
    finally:
        bm.free()
    if non_manifold:
        add(report, "warnings", "NON_MANIFOLD", "检测到非流形边；衣服边界可有意开放", mesh=obj.name, count=non_manifold)
    if degenerate_faces:
        add(report, "errors", "DEGENERATE_FACE", "检测到零面积/近零面积面", mesh=obj.name, count=degenerate_faces)

    deform_bones = {bone.name for bone in rig.data.bones if bone.use_deform}
    all_bones = {bone.name for bone in rig.data.bones}
    max_inf = int(settings.get("max_influences_recommended", 4))
    threshold = float(settings.get("min_significant_weight", 0.0001))
    tolerance = float(settings.get("normalization_tolerance", 0.01))
    limit = int(settings.get("warning_sample_limit", 30))
    unweighted, non_normalized, too_many, unknown = [], [], [], set()
    non_deform = set()

    for v in mesh.vertices:
        valid = []
        for entry in v.groups:
            if entry.weight <= 0:
                continue
            try:
                name = obj.vertex_groups[entry.group].name
            except IndexError:
                unknown.add(f"index:{entry.group}")
                continue
            if name not in all_bones:
                unknown.add(name)
            elif name not in deform_bones:
                non_deform.add(name)
            elif entry.weight > threshold:
                valid.append(float(entry.weight))

        total = sum(valid)
        if total <= threshold:
            unweighted.append(v.index)
        elif abs(total - 1.0) > tolerance:
            non_normalized.append(v.index)
        if len(valid) > max_inf:
            too_many.append(v.index)

    if unweighted:
        add(report, "errors", "UNWEIGHTED_VERTICES", "存在没有有效变形骨骼权重的顶点", mesh=obj.name, count=len(unweighted), sample=unweighted[:limit])
    if unknown:
        add(report, "errors", "UNKNOWN_VERTEX_GROUP", "权重组未匹配到骨骼（注意大小写）", mesh=obj.name, groups=sorted(unknown))
    if non_deform:
        add(report, "warnings", "NON_DEFORM_GROUP", "非变形骨骼被分配顶点权重", mesh=obj.name, groups=sorted(non_deform))
    if non_normalized:
        add(report, "warnings", "WEIGHT_SUM", "顶点有效权重总和偏离 1", mesh=obj.name, count=len(non_normalized), sample=non_normalized[:limit])
    if too_many:
        add(report, "warnings", "BONE_INFLUENCES", "超过建议单顶点影响数", mesh=obj.name, limit=max_inf, count=len(too_many), sample=too_many[:limit])

    return {
        "vertex_count": len(mesh.vertices), "polygon_count": len(mesh.polygons),
        "uv_layers": len(mesh.uv_layers), "materials": len(mesh.materials),
        "non_manifold_edges": non_manifold, "degenerate_faces": degenerate_faces,
        "unweighted_count": len(unweighted), "non_normalized_count": len(non_normalized),
        "too_many_influences_count": len(too_many), "unknown_vertex_groups": sorted(unknown),
    }


def evaluated_box(meshes, rig):
    """Evaluated deformed vertices in armature OBJECT space (all mesh objects)."""
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    inv_rig = rig.matrix_world.inverted_safe()
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    count = 0

    for obj in meshes:
        evaluated = obj.evaluated_get(depsgraph)
        eval_mesh = evaluated.to_mesh()
        if eval_mesh is None:
            continue
        try:
            transform = inv_rig @ evaluated.matrix_world
            for vert in eval_mesh.vertices:
                pos = transform @ vert.co
                count += 1
                for i in range(3):
                    lo[i] = min(lo[i], float(pos[i]))
                    hi[i] = max(hi[i], float(pos[i]))
        finally:
            evaluated.to_mesh_clear()
    if count == 0:
        return None
    result = make_box(lo, hi)
    result["evaluated_vertex_count"] = count
    return result


def scan_actions(meshes, rig, profile, bbox_conf, report):
    original_frame = bpy.context.scene.frame_current
    original_pose = rig.data.pose_position
    anim = rig.animation_data_create()
    original_action = anim.action
    bounds = {"coordinate_space": "armature_local", "static_rest": None, "actions": {}, "dynamic_union": None}
    try:
        rig.data.pose_position = "REST"
        bpy.context.view_layer.update()
        bounds["static_rest"] = evaluated_box(meshes, rig)
        rig.data.pose_position = "POSE"
        bpy.context.view_layer.update()
        selected = profile.get("actions") or ([original_action.name] if original_action else [])
        all_boxes = []
        for name in selected:
            action = bpy.data.actions.get(name)
            if not action:
                add(report, "errors", "ACTION_NOT_FOUND", "找不到指定 Action", action=name)
                continue
            try:
                anim.action = action
                start, end = action.frame_range
                if not (math.isfinite(start) and math.isfinite(end) and start <= end):
                    raise ValueError(f"invalid frame range {start}, {end}")
                step = max(1, int(profile.get("sample_step_frames", 3)))
                frames = sorted(set(list(range(int(math.floor(start)), int(math.ceil(end)) + 1, step)) + [int(math.ceil(end))]))
                boxes = []
                for frame in frames:
                    bpy.context.scene.frame_set(frame)
                    bbox = evaluated_box(meshes, rig)
                    if bbox:
                        boxes.append(bbox)
                combined = union_boxes(boxes)
                if combined:
                    combined["sampled_frame_count"] = len(frames)
                    combined["frame_range"] = [float(start), float(end)]
                    bounds["actions"][name] = combined
                    all_boxes.append(combined)
                else:
                    add(report, "errors", "EMPTY_ACTION_BOUNDS", "动画未产生任何网格边界", action=name)
            except Exception as exc:
                add(report, "errors", "ACTION_EVAL_ERROR", f"动作 {name} 采样失败：{exc}")
        bounds["dynamic_union"] = union_boxes(all_boxes)
        if not all_boxes:
            add(report, "warnings", "NO_DYNAMIC_SAMPLING", "没有采样任何动画 Action；动态边界待验证")
    finally:
        anim.action = original_action
        rig.data.pose_position = original_pose
        bpy.context.scene.frame_set(original_frame)
        bpy.context.view_layer.update()
    ref = bbox_conf.get("reference")
    margin = bbox_conf.get("axis_absolute_margin", [0, 0, 0])
    if bounds["static_rest"]:
        bounds["static_comparison"] = compare_box(bounds["static_rest"], ref, margin)
    else:
        add(report, "errors", "EMPTY_BOUNDS", "没有可用的静态网格顶点")
    if bounds["dynamic_union"]:
        bounds["dynamic_comparison"] = compare_box(bounds["dynamic_union"], ref, margin)
    else:
        bounds["dynamic_comparison"] = {"status": "PENDING", "reason": "缺少动画采样"}
    for name in ("static_comparison", "dynamic_comparison"):
        if bounds[name]["status"] == "FAIL":
            add(report, "errors", "BBOX_OVERFLOW", f"{name} 超出参考包围盒", overflow=bounds[name])
    return bounds


def main():
    args = parse_args()
    report = {
        "schema_version": 1,
        "tool": "cs2-model-rigging-deployment/blender_audit",
        "source_blend": bpy.data.filepath,
        "checks": {},
        "findings": findings_bucket(),
        "engine_checks_not_performed": ["ModelDoc compile", "AG2 live player", "compiled collision", "Hitbox", "server mounting"],
    }
    try:
        profile = load_json(args.config)
        bbox_conf = load_json(args.bbox)
        rig = choose_rig(profile)
        meshes = choose_meshes(profile, rig)
        if not meshes:
            raise ValueError("没有发现与目标 Armature 相关联的渲染网格；指定 object_names")
        report["checks"]["skeleton"] = check_skeleton(rig, profile, report)
        report["checks"]["mesh_and_weights"] = {obj.name: check_mesh(obj, rig, profile, report) for obj in meshes}
        report["checks"]["bounding_boxes"] = scan_actions(meshes, rig, profile, bbox_conf, report)
        # v8 body HEIGHT uses explicitly classified BODY geometry only. Do not
        # silently skip mixed decorations; entire render bounds still include them.
        if args.height_profile:
            from blender_body_height_audit import audit as height_audit
            try:
                height_result = height_audit(load_json(args.height_profile))
            except Exception as exc:
                height_result = {"status": "FAIL", "reason": str(exc)}
            report["checks"]["source_height"] = height_result
            if height_result["status"] == "FAIL":
                add(report, "errors", "BODY_HEIGHT_INVALID", "主体高度或装饰物排除规则不符合要求", details=height_result)
            elif height_result["status"] in ("WARN", "PENDING"):
                add(report, "warnings", "BODY_HEIGHT_REVIEW", "人体高度需接近当前默认探员；非人形主骨架应匹配本体高度", details=height_result)
        else:
            report["checks"]["source_height"] = {"status": "PENDING", "reason": "未提供主体与装饰物高度分类"}
        # v4: compare source-body anchors against target lengths, never against Valve agent proportions.
        if args.proportions and args.baseline:
            from blender_proportion_audit import audit as proportion_audit
            result = proportion_audit(load_json(args.proportions), load_json(args.baseline), profile.get("actions"))
            report["checks"]["source_proportions"] = result
            if result["status"] == "FAIL":
                add(report, "errors", "ORIGINAL_PROPORTIONS_CHANGED", "模型相对原始四肢比例超出容差，禁止拉伸适配", details=result)
            elif result["status"] == "PENDING":
                add(report, "warnings", "PROPORTIONS_PENDING", "缺乏完整原始比例/姿态伸缩证据")
        else:
            report["checks"]["source_proportions"] = {"status": "PENDING", "reason": "原始模型基准未提供"}
        if args.animation_suite:
            from animation_suite import audit_suite
            suite = audit_suite(load_json(args.animation_suite),
                               set(bpy.data.actions.keys()),
                               set(report["checks"]["bounding_boxes"]["actions"].keys()))
            report["checks"]["animation_suite"] = suite
            if suite["status"] == "FAIL":
                add(report, "errors", "ANIMATION_SOURCE_CLIP_MISSING", "声明了必须导出但不存在的动画片段", details=suite["errors"])
        else:
            report["checks"]["animation_suite"] = {"status": "PENDING", "reason": "未配置动画覆盖清单"}
        # v5 accessory bones MUST be present and weighted; Source 2 dynamics remain pending.
        if args.accessories:
            from blender_accessory_audit import audit as accessory_audit
            acc_config = load_json(args.accessories)
            all_actions = profile.get("actions") or ([rig.animation_data.action.name] if rig.animation_data and rig.animation_data.action else [])
            accessory_result = accessory_audit(acc_config, rig, meshes, all_actions)
            report["checks"]["accessories"] = accessory_result
            if accessory_result["status"] == "FAIL":
                add(report, "errors", "ACCESSORY_BONES_OR_WEIGHTS", "装饰物未按声明绑定独立骨骼或蒙皮", details=accessory_result["errors"])
            elif accessory_result["status"] != "PASS_PRELIMINARY":
                add(report, "warnings", "ACCESSORY_REVIEW_PENDING", "装饰物源模型仍有待复核项", details=accessory_result["warnings"])
        else:
            report["checks"]["accessories"] = {"status":"PENDING", "reason":"未提供装饰物清单/显式无装饰物确认"}
        if args.joint_deformation:
            from blender_joint_deformation import audit as joint_audit
            joint_config = load_json(args.joint_deformation)
            excluded = [name for accessory in (load_json(args.accessories).get("accessories",[]) if args.accessories else [])
                        for name in accessory.get("mesh_objects",[])]
            all_actions = profile.get("actions") or ([rig.animation_data.action.name] if rig.animation_data and rig.animation_data.action else [])
            joint_result = joint_audit(joint_config, rig, meshes, all_actions, excluded=excluded)
            report["checks"]["joint_deformation"] = joint_result
            if joint_result["status"] == "FAIL":
                add(report, "errors", "JOINT_DEFORMATION", "关节动态采样发现拉伸、挤压、坍缩或无效源数据", details=joint_result["errors"], joints=joint_result["joints"])
            elif joint_result["status"] != "PASS_PRELIMINARY":
                add(report, "warnings", "JOINT_REVIEW_PENDING", "关节区域或动画帧采样未完整校准", details=joint_result["warnings"])
        else:
            report["checks"]["joint_deformation"] = {"status":"PENDING", "reason":"未提供关节运动变形检测配置"}
        # v6: source geometry gap / reviewed animated seam checks. No topology edits.
        action_names = profile.get("actions") or ([rig.animation_data.action.name] if rig.animation_data and rig.animation_data.action else [])
        if args.mesh_integrity:
            from blender_mesh_gap_audit import audit as gap_audit
            gap_result = gap_audit(load_json(args.mesh_integrity), rig, meshes, action_names)
            report["checks"]["mesh_integrity"] = gap_result
            if gap_result["status"] == "FAIL":
                add(report, "errors", "MESH_CRACK_OR_TOPOLOGY", "检测到网格破口/拓扑问题或受控接缝动态裂开", details=gap_result)
            elif gap_result["status"] != "PASS_PRELIMINARY":
                add(report, "warnings", "MESH_SEAM_PENDING", "存在未确认开口或动作接缝验收不足", details=gap_result.get("warnings", []))
        else:
            report["checks"]["mesh_integrity"] = {"status": "PENDING", "reason": "尚未配置静态破口与动态接缝检查"}
        if args.rig_stretch:
            from blender_rig_stretch_audit import audit as stretch_audit
            stretch_result = stretch_audit(load_json(args.rig_stretch), rig, meshes, action_names)
            report["checks"]["rig_stretch"] = stretch_result
            if stretch_result["status"] == "FAIL":
                add(report, "errors", "RIG_STRETCH", "姿态骨长/缩放/重复骨架驱动异常", details=stretch_result)
            elif stretch_result["status"] != "PASS_PRELIMINARY":
                add(report, "warnings", "RIG_STRETCH_PENDING", "骨骼拉伸排查仍待校准", details=stretch_result.get("warnings", []))
        else:
            report["checks"]["rig_stretch"] = {"status": "PENDING", "reason": "尚未配置逐动作骨长与双重蒙皮检查"}
        if not bbox_conf.get("reference"):
            add(report, "warnings", "BBOX_REFERENCE_MISSING", "参考包围盒未配置；仅输出尺寸")
        if profile.get("reference_rest_transforms_validated") is False:
            report["checks"]["reference_rest_pose"] = "PENDING"
        else:
            report["checks"]["reference_rest_pose"] = "USER_ATTESTED"
        report["status"] = "FAIL" if report["findings"]["errors"] else "WARN" if report["findings"]["warnings"] else "PASS_PRELIMINARY"
    except Exception as exc:
        report["status"] = "FAIL"
        add(report, "errors", "AUDIT_FATAL", str(exc), traceback=traceback.format_exc())

    destination = Path(args.out).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"CS2 Blender audit: {report['status']} -> {destination}")
    if report["status"] == "FAIL":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
