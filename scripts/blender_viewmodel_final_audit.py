"""Independent first-person arm rig / skin / provenance audit (Blender side only).

Requires a human-retargeted first-person model. Does not claim CS2 runtime success.
"""
from __future__ import annotations
import argparse
import json
import sys
import traceback
from pathlib import Path

import bpy
import bmesh


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def resolve(path, base):
    p = Path(path).expanduser()
    return p if p.is_absolute() else (Path(base).parent / p).resolve()


def evaluate(config, config_path):
    problems, pending, detail = [], [], []
    first_name = config.get('viewmodel_rig_object', '')
    world_name = config.get('worldmodel_rig_object', '')
    view = bpy.data.objects.get(first_name)
    if not view or view.type != 'ARMATURE':
        problems.append('缺少独立的 viewmodel Armature: ' + first_name)
    if first_name == world_name or not world_name:
        problems.append('第一/第三人称骨架不可为同一目标对象')
    original = config.get('source_extraction_report', '')
    previous = None
    if not original or not resolve(original, config_path).is_file():
        problems.append('缺少第一人称源全身模型的提取报告及哈希')
    else:
        previous = read(resolve(original, config_path))
        if previous.get('status') != 'EXTRACTED_REQUIRES_RIGGING' or not previous.get('source_sha256_before'):
            problems.append('提取报告缺少成功标记或源模型 SHA256')
    mapping_path = config.get('firstperson_bone_map', '')
    mapping = None
    if not mapping_path or not resolve(mapping_path, config_path).is_file():
        problems.append('缺少源骨架 -> viewmodel 骨架的人工确认映射')
    else:
        mapping = read(resolve(mapping_path, config_path))
        if mapping.get('reviewed') is not True or not mapping.get('mapping'):
            problems.append('骨骼映射尚未逐骨骼确认并保存')
        if view:
            for destination in (mapping.get('mapping') or {}).values():
                if destination not in view.data.bones:
                    problems.append('viewmodel 缺少映射目标骨骼: '+destination)
    objects = config.get('approved_firstperson_objects', [])
    if not objects:
        problems.append('approved_firstperson_objects 为空')
    for name in objects:
        obj = bpy.data.objects.get(name)
        if not obj or obj.type != 'MESH':
            problems.append('缺少独立第一人称裁剪网格: ' + name)
            continue
        mods = [mod for mod in obj.modifiers if mod.type == 'ARMATURE']
        if len(mods) != 1 or (view and mods[0].object != view):
            problems.append(f'{name}: Armature 修改器应恰好一个且指向独立 viewmodel rig')
        if obj.parent and obj.parent.type == 'ARMATURE' and obj.parent != view:
            problems.append(f'{name}: 仍被第三人称/旧骨架 Parent 驱动')
        if obj.get('cs2_fp_provenance') != 'extracted_from_original_fullbody':
            problems.append(f'{name}: 无法证实手模从完整原始人物裁剪')
        if previous and obj.get('cs2_fp_source_blend_sha256') != previous.get('source_sha256_before'):
            problems.append(f'{name}: 原模型哈希与提取记录不一致')
        scale = [abs(n) for n in obj.scale]
        if min(scale) <= 1e-8 or max(scale) / min(scale) > 1.005:
            problems.append(f'{name}: 存在非均匀缩放或零缩放')
        deform = {bone.name for bone in view.data.bones if bone.use_deform} if view else set()
        unknown = 0
        no_weights = 0
        for vertex in obj.data.vertices:
            total = 0.0
            for g in vertex.groups:
                name_group = obj.vertex_groups[g.group].name
                if name_group in deform:
                    total += g.weight
                elif g.weight > 0.0001 and name_group not in {'FP_KEEP_L','FP_KEEP_R'}:
                    unknown += 1
            if total < 0.0001:
                no_weights += 1
        if no_weights:
            problems.append(f'{name}: {no_weights} 个顶点未蒙皮到 viewmodel 目标骨骼')
        if unknown:
            pending.append(f'{name}: {unknown} 处非目标骨骼顶点组需人工审查')
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            open_edges = sum(1 for e in bm.edges if e.is_boundary)
            nonmanifold = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
        finally:
            bm.free()
        if nonmanifold:
            problems.append(f'{name}: {nonmanifold} 非流形/独立边')
        if open_edges and not config.get('approved_cut_geometry_in_camera'):
            pending.append(f'{name}: {open_edges} 开边；需确认只在相机不可见的肩部裁口，且手套/袖口无破口')
        detail.append({'name': name, 'vertices': len(obj.data.vertices), 'open_edges': open_edges,
                       'unbound_vertices': no_weights, 'unknown_weight_entries': unknown})
    if not config.get('original_proportions_verified'):
        pending.append('第一人称源模型四肢比例尚未与原始手臂基准复核')
    if not config.get('firstperson_actions_baked_verified'):
        pending.append('握枪、射击、换弹、刀具与检视动作尚未逐帧验证')
    if view:
        scale = [abs(x) for x in view.scale]
        if min(scale) <= 1e-8 or max(scale) / min(scale) > 1.005:
            problems.append('第一人称目标骨架存在非均匀缩放')
        for bone in view.pose.bones:
            if bone.ik_stretch > 1e-6:
                problems.append(f'{bone.name}: 不允许 IK Stretch')
            for c in bone.constraints:
                if c.type in {'STRETCH_TO', 'COPY_SCALE'}:
                    problems.append(f'{bone.name}: 不允许未审查的 {c.type}')
    return {'status': 'FAIL' if problems else ('PENDING_REVIEW' if pending else 'PASS_PRELIMINARY'),
            'rig_independent_from_world': bool(view and first_name != world_name),
            'problems': problems, 'pending': pending, 'meshes': detail,
            'runtime_status': 'PENDING_ENGINE',
            'reminder': 'Blender 通过不等于 AG2、ModelDoc 或游戏第一人称实际切换成功'}


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args(argv)
    try:
        report = evaluate(read(args.config), args.config)
    except Exception as exc:
        report = {'status': 'FAIL', 'error': str(exc), 'traceback': traceback.format_exc()}
    path = Path(args.out).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('First-person final audit: ' + report['status'])
    if report['status'] == 'FAIL':
        raise SystemExit(2)

if __name__ == '__main__':
    main()
