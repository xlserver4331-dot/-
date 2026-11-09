"""Snapshot FP source+export SHA256 in editable local dual-viewmodel configuration.

Only explicit --execute mutates the *local config*; creates a backup first.
Does not set human-approval fields or pretend that FBX/ModelDoc imports work.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from auto_workflow_core import read_json, resolve_config_path, sha256, write_json


def compute(dual_path, workflow_path):
    cfg = read_json(dual_path)
    wf = read_json(workflow_path)
    blend = resolve_config_path(dual_path, cfg.get('firstperson_blend', ''))
    rel = cfg.get('firstperson_fbx_relative_path', '')
    matched = [x for x in wf.get('deploy_files', []) if x.get('area')=='content' and x.get('relative_path')==rel]
    if len(matched)!=1:
        raise ValueError('deploy_files 必须有唯一 firstperson_fbx_relative_path')
    fbx = resolve_config_path(workflow_path, matched[0]['source'])
    if not blend or not blend.is_file() or not fbx or not fbx.is_file():
        raise ValueError('需要有效的最终 FP .blend 和实际导出的 FBX；不能靠录入假 Hash')
    return {'firstperson_blend_sha256': sha256(blend), 'firstperson_fbx_sha256': sha256(fbx),
            'source_blend':str(blend),'source_fbx':str(fbx)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dual',required=True)
    p.add_argument('--workflow',required=True)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    dual=Path(a.dual).expanduser().resolve(); workflow=Path(a.workflow).expanduser().resolve()
    report=compute(dual,workflow)
    if a.execute:
        backup=dual.with_suffix('.json.bak')
        if backup.exists():
            raise ValueError('备份已存在，避免覆盖: '+str(backup))
        backup.write_bytes(dual.read_bytes())
        cfg=read_json(dual)
        cfg.update({k:report[k] for k in ('firstperson_blend_sha256','firstperson_fbx_sha256')})
        write_json(dual,cfg)
        report['status']='PINNED_LOCAL_CONFIG_WITH_BACKUP'
        report['backup']=str(backup)
    else:
        report['status']='DRY_RUN'
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
