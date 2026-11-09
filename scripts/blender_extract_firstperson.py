"""Build FIRST-PERSON ARMS *GEOMETRY* from the complete original character.

No inverse kinematics, retargeting, rescaling or model overwrite. Manual vertex-group
masks define the cut. The output is a non-destructive COPY that STILL NEEDS a
separate CS2 viewmodel rig, animation and ModelDoc validation before deployment.

blender -b original.blend --python blender_extract_firstperson.py -- \
 --config config/viewmodel_extraction.local.json --out new_firstperson.blend \
 --report fp_extraction.json [--apply]
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import traceback
from pathlib import Path

import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
from viewmodel_core import selected_face_indices, face_boundary_edges, extraction_preflight


def hash_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def mask_vertices(obj, part):
    groups = []
    for name in part.get('mask_vertex_groups', []):
        group = obj.vertex_groups.get(name)
        if group is None:
            raise ValueError(f'{obj.name}: 缺少人工绘制的顶点组 {name}')
        groups.append(group.index)
    if part.get('whole_object_explicitly_approved'):
        if groups:
            raise ValueError('不能同时指定 entire mesh 和裁剪掩码')
        return set(range(len(obj.data.vertices)))
    threshold = float(part.get('min_vertex_weight', 0.95))
    if not 0.5 <= threshold <= 1:
        raise ValueError('min_vertex_weight must be between 0.5 and 1')
    chosen = set()
    for v in obj.data.vertices:
        if any(g.group in groups and g.weight >= threshold for g in v.groups):
            chosen.add(v.index)
    return chosen


def inspect_part(part):
    obj = bpy.data.objects[part['source_object']]
    faces = [list(poly.vertices) for poly in obj.data.polygons]
    marked = mask_vertices(obj, part)
    selected = selected_face_indices(faces, marked,
                    minimum_fraction=float(part.get('min_face_fraction', 1.0)))
    if len(selected) < int(part.get('min_selected_faces', 12)):
        raise ValueError(f'{obj.name}: 选中面太少 ({len(selected)})，请检查 FP_KEEP 掩码')
    if len(selected) == len(faces) and not part.get('whole_object_explicitly_approved'):
        raise ValueError(f'{obj.name}: 选中整个源网格，可能错误包含躯干；不允许无意导出全身')
    edges = face_boundary_edges(faces, selected)
    if not edges and not part.get('whole_object_explicitly_approved'):
        raise ValueError(f'{obj.name}: 没有截断边，检查所选区域是否正确')
    return obj, selected, edges


def make_copy(obj, name, chosen, collection, source_armature, source_hash, mask_group_names):
    new = obj.copy()
    new.data = obj.data.copy()
    collection.objects.link(new)
    new.name = name
    new.data.name = name + '_mesh'
    # Original polygon order == BMesh before topology changes; avoid evaluated
    # modifiers that could reorder vertices, destroy UVs, or change weights.
    bm = bmesh.new()
    try:
        bm.from_mesh(new.data)
        bm.faces.ensure_lookup_table()
        chosen_set = set(chosen)
        unwanted = [f for i, f in enumerate(list(bm.faces)) if i not in chosen_set]
        if unwanted:
            bmesh.ops.delete(bm, geom=unwanted, context='FACES')
        loose = [v for v in list(bm.verts) if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context='VERTS')
        bm.to_mesh(new.data)
    finally:
        bm.free()
    new.data.update()
    # Selection masks must not enter final skin export as undefined deform groups.
    for group_name in mask_group_names:
        group = new.vertex_groups.get(group_name)
        if group is not None:
            new.vertex_groups.remove(group)
    new['cs2_fp_provenance'] = 'extracted_from_original_fullbody'
    new['cs2_fp_source_object'] = obj.name
    new['cs2_fp_source_armature'] = source_armature
    new['cs2_fp_source_blend_sha256'] = source_hash
    new['cs2_fp_pending_viewmodel_rig'] = True
    new['cs2_fp_original_rest_preserved'] = True
    return new


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', required=True)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)
    report = {'status': 'FAIL', 'applied': False, 'output_blend': None,
              'next_required': ['manual_cut_review', 'independent_viewmodel_rig',
              'weapon_animation_bake', 'firstperson_joint_gap_proportions_audit',
              'modeldoc_viewmodel_compile', 'private_game_visual_confirmation'], 'parts': []}
    try:
        profile = json.loads(Path(args.config).read_text(encoding='utf-8'))
        src = Path(bpy.data.filepath).resolve()
        target = Path(args.out).expanduser().resolve()
        if not src.is_file():
            raise ValueError('Blender 输入 .blend 文件不存在或尚未保存')
        if target == src or target.exists() or target.suffix.lower() != '.blend':
            raise ValueError('必须输出新的、不存在的 .blend，不允许覆盖源模型')
        rig = bpy.data.objects.get(profile.get('source_armature', ''))
        if rig is None or rig.type != 'ARMATURE':
            raise ValueError('source_armature 与完整原始角色的骨架对象不匹配')
        objects = {o.name: o for o in bpy.data.objects}
        errors = extraction_preflight(profile, objects)
        if errors:
            raise ValueError('; '.join(errors))
        plan = []
        for part in profile['parts']:
            obj, faces, boundary = inspect_part(part)
            deform = [m for m in obj.modifiers if m.type == 'ARMATURE']
            if len(deform) != 1 or deform[0].object != rig:
                raise ValueError(f'{obj.name}: 必须且仅能有一个指向原始骨架的 Armature Modifier')
            if obj.data.shape_keys:
                raise ValueError(f'{obj.name}: 含 Shape Keys，不能安全自动截取；请先单独评审')
            if obj.library or obj.data.library or obj.override_library:
                raise ValueError(f'{obj.name}: 链接/覆盖库对象禁止自动改动')
            item = {'source_object': obj.name, 'output_object': part['output_object'],
                    'source_faces': len(obj.data.polygons), 'selected_faces': len(faces),
                    'open_boundary_edges': len(boundary), 'cut_reviewed': bool(part.get('approved_shoulder_cut')),
                    'selected_face_indices_sample': faces[:12]}
            report['parts'].append(item)
            plan.append((obj, part, faces))
        report['source_file'] = str(src)
        report['source_sha256_before'] = hash_file(src)
        if args.apply:
            collection = bpy.data.collections.new('CS2_FP_EXTRACTION_PREVIEW')
            bpy.context.scene.collection.children.link(collection)
            for obj, part, faces in plan:
                new = make_copy(obj, part['output_object'], faces, collection, rig.name, report['source_sha256_before'], part.get('mask_vertex_groups', []))
                if not new.data.polygons:
                    raise ValueError('裁剪后网格为空')
            target.parent.mkdir(parents=True, exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=str(target), check_existing=False)
            if not target.is_file():
                raise RuntimeError('没有生成新的 .blend')
            report['applied'] = True
            report['output_blend'] = str(target)
            report['status'] = 'EXTRACTED_REQUIRES_RIGGING'
        else:
            report['status'] = 'DRY_RUN'
        report['source_sha256_after'] = hash_file(src)
        if report['source_sha256_before'] != report['source_sha256_after']:
            raise RuntimeError('源文件在操作过程中被外部修改，必须重新审查')
    except Exception as e:
        report['status'] = 'FAIL'
        report['error'] = str(e)
        report['traceback'] = traceback.format_exc()
    path = Path(args.report).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('FP extraction: ' + report['status'])
    if report['status'] == 'FAIL':
        raise SystemExit(2)

if __name__ == '__main__':
    main()
