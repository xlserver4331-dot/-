"""First-person extraction decisions and provenance gates; pure Python, no Blender dependency."""
from __future__ import annotations


def selected_face_indices(face_vertices, active_vertices, *, minimum_fraction=1.0):
    """Select only explicitly marked faces. No automatic anatomical guessing."""
    if not 0 < minimum_fraction <= 1:
        raise ValueError('minimum_fraction must be in (0,1]')
    active = set(active_vertices)
    return [i for i, vertices in enumerate(face_vertices)
            if vertices and sum(v in active for v in vertices) / len(vertices) >= minimum_fraction]


def face_boundary_edges(face_vertices, included):
    """Return cut/open boundary edges of selected face region, as sorted vertex index pairs."""
    counts = {}
    for i in included:
        face = face_vertices[i]
        for a, b in zip(face, face[1:] + face[:1]):
            edge = tuple(sorted((a, b)))
            counts[edge] = counts.get(edge, 0) + 1
    return sorted(edge for edge, count in counts.items() if count == 1)


def extraction_preflight(profile, objects):
    """Reject missing source, masks, unsafe defaults. objects: name -> metadata."""
    errors = []
    if profile.get('target') != 'firstperson_from_fullbody':
        errors.append('target 必须为 firstperson_from_fullbody')
    if not profile.get('source_armature'):
        errors.append('source_armature 不可为空')
    if profile.get('auto_rescale_limbs') or profile.get('auto_fill_holes'):
        errors.append('禁止自动拉长四肢或盲目 Fill Holes')
    parts = profile.get('parts', [])
    if not parts:
        errors.append('缺少 parts 配置')
    used = set()
    for part in parts:
        name, out = part.get('source_object'), part.get('output_object')
        if not name or name not in objects:
            errors.append('源网格不存在: ' + str(name))
        if not out or out in used or out in objects:
            errors.append('输出网格名称冲突: ' + str(out))
        used.add(out)
        if not part.get('mask_vertex_groups') and not part.get('whole_object_explicitly_approved'):
            errors.append(f'{name}: 必须有人工标定的顶点组或显式批准整物体复制')
        fraction = float(part.get('min_face_fraction', 1.0))
        if fraction < 0.75 or fraction > 1.0:
            errors.append(f'{name}: min_face_fraction 必须在 0.75–1 范围，避免带入躯干')
        if not part.get('approved_shoulder_cut', False):
            errors.append(f'{name}: 必须人工批准肩部截断位置')
    return errors


def viewmodel_release_gate(config, *, extraction=None, audit=None, packaging=None):
    """Separate original-geometry extraction from final runtime viewmodel acceptance."""
    if not config.get('required', False):
        return []
    problems = []
    if not extraction or extraction.get('status') not in ('EXTRACTED_REQUIRES_RIGGING', 'PASS_EXTRACTED'):
        problems.append('需要全身源模型提取记录及源文件 SHA256')
    if not audit or audit.get('status') != 'PASS_PRELIMINARY':
        problems.append('独立第一人称骨架/网格/变形审计未通过')
    elif audit.get('rig_independent_from_world') is not True:
        problems.append('第一人称未使用经验证的独立 viewmodel rig')
    if not packaging or not packaging.get('modeldoc_viewmodel_fbx_reference_verified'):
        problems.append('ModelDoc viewmodel FBX 引用尚未核对')
    if not packaging or not packaging.get('compiled_viewmodel_present'):
        problems.append('缺少独立编译后的第一人称资源')
    return problems
