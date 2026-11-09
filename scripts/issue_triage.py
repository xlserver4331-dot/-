"""Convert source audit into a prioritized, deduplicated corrective-action queue.
Never labels difficult rig changes as auto-fixable.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

AUTO_FIXABLE = {"WEIGHT_SUM"}
HARD = {"JOINT_DEFORMATION", "ACCESSORY_BONES_OR_WEIGHTS", "ORIGINAL_PROPORTIONS_CHANGED", "BBOX_OVERFLOW", "MISSING_BONE", "BONE_PARENT", "MESH_CRACK_OR_TOPOLOGY", "RIG_STRETCH"}


def build_triage(report):
    findings = report.get('findings',{})
    rows=[]
    dedup=set()
    for severity in ('errors','warnings','info'):
        for finding in findings.get(severity,[]):
            code=finding.get('code','UNKNOWN')
            reference=(finding.get('mesh',''),finding.get('bone',''),finding.get('action',''))
            key=(code,reference)
            if key in dedup:continue
            dedup.add(key)
            level='BLOCKER' if severity=='errors' or code in HARD else 'REVIEW' if severity=='warnings' else 'INFO'
            rows.append({'priority':level,'code':code,'message':finding.get('message',''),
                         'auto_fix_allowed':code in AUTO_FIXABLE,
                         'reference':list(reference), 'action':'review geometry/weight/bone data' if code not in AUTO_FIXABLE else 'safe normalization then re-audit'})
    for gate,name in (('accessories','装饰物独立骨骼'),('joint_deformation','关节动态形变'),
                      ('mesh_integrity','网格破口及动态接缝'),('rig_stretch','动作拉伸及重复变形')):
        status=report.get('checks',{}).get(gate,{}).get('status','PENDING')
        if status!='PASS_PRELIMINARY' and not any(x['code'].startswith('ACCESSORY_') if gate=='accessories' else x['code'].startswith('JOINT_') if gate=='joint_deformation' else x['code'].startswith('MESH_') if gate=='mesh_integrity' else x['code'].startswith('RIG_') for x in rows):
            rows.append({'priority':'BLOCKER' if status=='FAIL' else 'REVIEW', 'code':f'{gate.upper()}_GATE',
                         'message':f'{name}: {status}', 'auto_fix_allowed':False,'reference':[], 'action':'calibrate and review'})
    order={'BLOCKER':0,'REVIEW':1,'INFO':2}
    rows.sort(key=lambda row:(order[row['priority']],row['code']))
    return {'status':'FAIL' if any(x['priority']=='BLOCKER' for x in rows) else 'PENDING_REVIEW' if rows else 'PASS_PRELIMINARY',
            'items':rows,'summary':{k:sum(x['priority']==k for x in rows) for k in order},
            'note':'Priorities are recommendations, not permission to change source proportions or automate joint weight painting.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--audit',required=True);p.add_argument('--out',required=True)
    a=p.parse_args()
    r=build_triage(json.loads(Path(a.audit).read_text(encoding='utf8')))
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
    print(r['status'], '->',dest)
