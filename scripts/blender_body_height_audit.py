"""Read-only Blender inspection of decoration-excluded body height.

Height uses REST source geometry transformed to world coordinates; the full
render bounds, including accessories, are kept separately for render QA.
An embedded accessory in a merged mesh requires a FACE INT/BOOLEAN attribute
(e.g. cs2_height_body=1 for body polygons, 0 for accessory polygons).
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from height_policy_core import evaluate_height_policy


def _measure(coords, axis):
    if not coords:
        return None
    lo = [min(v[i] for v in coords) for i in range(3)]
    hi = [max(v[i] for v in coords) for i in range(3)]
    return {'min': lo, 'max': hi, 'size': [hi[i]-lo[i] for i in range(3)],
            'height': hi[axis]-lo[axis], 'vertex_samples': len(coords)}


def _world_vertex(obj, index):
    return tuple(float(v) for v in (obj.matrix_world @ obj.data.vertices[index].co))


def _obj(name):
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != 'MESH':
        raise ValueError('找不到已声明的网格: ' + name)
    return obj


def _all_vertices(obj):
    used = {idx for polygon in obj.data.polygons for idx in polygon.vertices}
    if not used:
        raise ValueError(f'{obj.name}: 网格没有有效表面，不能用孤立顶点计算主体高度')
    return [_world_vertex(obj, idx) for idx in sorted(used)]


def _face_coords(obj, attribute):
    a = obj.data.attributes.get(attribute)
    if a is None or a.domain != 'FACE' or a.data_type not in {'BOOLEAN', 'INT'}:
        raise ValueError(f'{obj.name}: 需要 FACE 域布尔/整数属性 {attribute}')
    body, acc = set(), set()
    for polygon in obj.data.polygons:
        selection = body if bool(a.data[polygon.index].value) else acc
        selection.update(polygon.vertices)
    if not body or not acc:
        raise ValueError(f'{obj.name}: 混合网格属性必须同时标记主体面和装饰面')
    return [_world_vertex(obj, i) for i in sorted(body)], [_world_vertex(obj, i) for i in sorted(acc)]


def audit(config):
    name = config.get('armature')
    rig = bpy.data.objects.get(name)
    if rig is None or rig.type != 'ARMATURE':
        raise ValueError(f'找不到主体骨架: {name}')
    axis = {'X': 0, 'Y': 1, 'Z': 2}.get(config.get('up_axis', 'Z'))
    if axis is None:
        raise ValueError('up_axis 只能为 X/Y/Z，且须使用与参照探员一致的单位')
    body_names = config.get('body_mesh_objects', [])
    acc_names = config.get('accessory_mesh_objects', [])
    mixed = config.get('mixed_meshes', [])
    ignored = config.get('ignored_mesh_objects', [])
    mixed_names = [entry['object'] for entry in mixed]
    categories = body_names + acc_names + mixed_names + ignored
    if len(set(categories)) != len(categories):
        raise ValueError('网格不能重复归入多个高度类别，混合网格应只列在 mixed_meshes')
    if not body_names and not mixed:
        raise ValueError('必须显式标记主体网格或混合网格的主体面')
    if config.get('exclude_accessories_from_height') is not True:
        raise ValueError('exclude_accessories_from_height 必须为 true')

    body, accessories, all_render = [], [], []
    for name in body_names:
        pts = _all_vertices(_obj(name))
        body.extend(pts); all_render.extend(pts)
    for name in acc_names:
        pts = _all_vertices(_obj(name))
        accessories.extend(pts); all_render.extend(pts)
    for entry in mixed:
        obj = _obj(entry['object'])
        b, a = _face_coords(obj, entry['body_face_attribute'])
        body.extend(b); accessories.extend(a); all_render.extend(_all_vertices(obj))
    for name in ignored:
        _obj(name)  # intentionally excluded only with explicit declaration

    rigged = {obj.name for obj in bpy.context.scene.objects
              if obj.type == 'MESH' and not obj.get('cs2_collision_only', False) and
              (obj.parent == rig or any(mod.type == 'ARMATURE' and mod.object == rig for mod in obj.modifiers))}
    unclassified = sorted(rigged - set(categories))
    if unclassified:
        raise ValueError('发现未分类绑定网格，可能把装饰物错误算入身高: ' + ', '.join(unclassified))
    if not body:
        raise ValueError('主体面集合为空')

    body_bounds = _measure(body, axis)
    accessory_bounds = _measure(accessories, axis)
    full_bounds = _measure(all_render, axis)
    bone_bounds = None
    if config.get('model_type') == 'nonhumanoid':
        bones = config.get('primary_height_bones') or []
        if len(bones) < 2 or len(set(bones)) != len(bones):
            raise ValueError('非人形必须指定至少两个不同的主体高度骨骼；不得包含装饰骨')
        positions = []
        for name in bones:
            bone = rig.data.bones.get(name)
            if bone is None:
                raise ValueError('找不到非人形主骨架骨骼: ' + name)
            positions.extend([tuple(rig.matrix_world @ bone.head_local),
                              tuple(rig.matrix_world @ bone.tail_local)])
        bone_bounds = _measure(positions, axis)

    result = evaluate_height_policy(config, body_bounds['height'],
                                    rig_height=bone_bounds['height'] if bone_bounds else None)
    result.update({'body_bounds_excluding_accessories': body_bounds,
                   'accessory_bounds_excluded_from_height': accessory_bounds,
                   'full_visual_bounds_including_accessories': full_bounds,
                   'primary_skeleton_bounds': bone_bounds,
                   'height_axis': config.get('up_axis', 'Z'),
                   'coordinate_space': 'Blender world space; ensure equal units for baseline',
                   'classified': {'body_meshes': body_names, 'accessory_meshes': acc_names,
                                  'mixed_meshes': mixed_names, 'ignored_meshes': ignored},
                   'safety': '只读检测：不移动、缩放或自动拉伸骨骼；不覆盖原模型。渲染/Hitbox 仍含装饰物。'})
    return result


def main():
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser(description='装饰物不计身高；人形参考CS2探员、非人形骨架匹配主体高度')
    p.add_argument('--config', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--capture-reference', action='store_true', help='捕获当前探员去装饰主体高度，仅作本机参考')
    p.add_argument('--capture-original', action='store_true', help='从未经缩放的原始模型捕获主体高度基准')
    args = p.parse_args(argv)
    try:
        profile = json.loads(Path(args.config).read_text(encoding='utf-8'))
        if args.capture_reference and args.capture_original:
            raise ValueError('不能同时捕获默认探员与原始主体高度')
        result = audit(profile)
        if args.capture_reference or args.capture_original:
            height = result['body_bounds_excluding_accessories']['height']
            is_agent = args.capture_reference
            result = {'status': 'REFERENCE_CAPTURED' if is_agent else 'ORIGINAL_BODY_CAPTURED',
                      'agent_reference_body_height' if is_agent else 'original_body_height': height,
                      'body_bounds_excluding_accessories': result['body_bounds_excluding_accessories'],
                      'source_blend': bpy.data.filepath, 'up_axis': profile.get('up_axis', 'Z'),
                      'note': ('将高度填入本机探员参考配置，并校准同单位/上轴。' if is_agent
                               else '从未经修改的原人物主体捕获：仅用于统一缩放或保留原高度基准，禁止误计装饰物。')}
    except Exception as exc:
        result = {'status': 'FAIL', 'reason': str(exc), 'source_blend': bpy.data.filepath}
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('CS2 body height audit:', result['status'], out)
    if result['status'] == 'FAIL':
        raise SystemExit(2)

if __name__ == '__main__':
    main()
