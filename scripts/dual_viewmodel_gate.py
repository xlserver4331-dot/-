"""Strict paired-viewmodel gate for the player pipeline, independent of Blender."""
from pathlib import Path
from auto_workflow_core import sha256
from auto_workflow_core import read_json, resolve_config_path, safe_relative


def inspect_pair(config_file, workflow, audit=None):
    errors = []
    if workflow.get('target') != 'player_runtime':
        return errors
    cfg_path = resolve_config_path(config_file, workflow.get('dual_viewmodel', ''))
    if not cfg_path or not cfg_path.is_file():
        return ['player_runtime: 缺少 dual_viewmodel 配置；不允许只发布第三人称而把第一人称留默认手模']
    cfg = read_json(cfg_path)
    if not cfg.get('required'):
        return ['player_runtime: dual_viewmodel.required 必须为 true 才允许自动部署']
    for field in ('source_extraction_report', 'firstperson_blend', 'firstperson_bone_map'):
        p = resolve_config_path(cfg_path, cfg.get(field, ''))
        if not p or not p.is_file():
            errors.append('双视角缺少文件: ' + field)
    report_path = resolve_config_path(cfg_path, cfg.get('source_extraction_report', ''))
    if report_path and report_path.is_file():
        record = read_json(report_path)
        if record.get('status') != 'EXTRACTED_REQUIRES_RIGGING' or not record.get('source_sha256_before'):
            errors.append('缺少原始整模提取来源 SHA256 证据')
    blend_path = resolve_config_path(cfg_path, cfg.get('firstperson_blend', ''))
    pinned_blend = cfg.get('firstperson_blend_sha256', '')
    if not pinned_blend or not blend_path or (blend_path.is_file() and sha256(blend_path) != pinned_blend):
        errors.append('第一人称最终 .blend 哈希未固定或与文件不匹配')
    fp_rel = cfg.get('firstperson_fbx_relative_path', '')
    rows = [x for x in workflow.get('deploy_files', []) if x.get('area') == 'content' and x.get('relative_path') == fp_rel]
    pinned_fbx = cfg.get('firstperson_fbx_sha256', '')
    if rows:
        fbx = resolve_config_path(config_file, rows[0].get('source', ''))
        if not pinned_fbx or not fbx or not fbx.is_file() or sha256(fbx) != pinned_fbx:
            errors.append('第一人称待部署 FBX 哈希未固定或与文件不匹配，可能是旧手模')
    if not cfg.get('modeldoc_viewmodel_fbx_reference_verified'):
        errors.append('尚未验证 ModelDoc 的第一人称 FBX 引用')
    if audit is None or audit.get('status') != 'PASS_PRELIMINARY':
        errors.append('独立第一人称手模审计未通过')
    rel = str(safe_relative(cfg.get('firstperson_fbx_relative_path', '')))
    if not any(x.get('area') == 'content' and x.get('relative_path') == rel for x in workflow.get('deploy_files', [])):
        errors.append('deploy_files 缺少第一人称 FBX: ' + rel)
    mode = cfg.get('packaging_mode', 'shared_bodygroup')
    if mode == 'shared_bodygroup':
        if not cfg.get('bodygroup_verified') or not cfg.get('ag2_viewmodel_skeleton_verified'):
            errors.append('共享 ModelDoc 的 bodygroup / viewmodel AG2 skeleton 尚未核对')
        vmdl = str(safe_relative(cfg.get('shared_modeldoc_vmdl', '')))
        compiled = str(safe_relative(cfg.get('compiled_shared_model', '')))
    elif mode == 'separate_vmdl':
        vmdl = str(safe_relative(cfg.get('firstperson_modeldoc_vmdl', '')))
        compiled = str(safe_relative(cfg.get('firstperson_compiled_vmdl', '')))
    else:
        errors.append('packaging_mode 必须为 shared_bodygroup 或 separate_vmdl')
        return errors
    if not any(x.get('area') == 'content' and x.get('relative_path') == vmdl for x in workflow.get('deploy_files', [])):
        errors.append('部署清单缺少 ModelDoc: ' + vmdl)
    if vmdl not in workflow.get('compile_sources', []):
        errors.append('compile_sources 未包括相关 ModelDoc')
    if compiled not in workflow.get('required_compiled_files', []):
        errors.append('required_compiled_files 未验证包含 FP 手模的模型')
    return errors
