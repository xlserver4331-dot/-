"""Explicit, reversible accessory support-bone creation. NEVER guesses original geometry proportions.

Requires user-calibrated armature-local head/tail positions and approved placement.
Default preview only. --apply saves a NEW .blend, never overwrites source.
"""
import argparse
import json
import sys
from pathlib import Path
import bpy
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parent))
from accessory_core import validated_config


def main():
    av=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    p=argparse.ArgumentParser()
    p.add_argument('--config',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--report',required=True)
    p.add_argument('--apply',action='store_true')
    args=p.parse_args(av)
    result={'status':'DRY_RUN','created_bones':[], 'existing_bones':[],
            'assigned_rigid_weights':[], 'assigned_chain_weights':[], 'manual_weights_pending':[], 'output_blend':None,
            'note':'No cloth physics or AG2 runtime driver is automatically generated.'}
    try:
        config=validated_config(json.loads(Path(args.config).read_text(encoding='utf8')))
        rig_name=config.get('target_armature')
        rig=bpy.data.objects.get(rig_name) if rig_name else None
        if rig is None or rig.type!='ARMATURE':raise ValueError('target_armature must identify an Armature')
        # Preflight everything BEFORE touching edit bones.
        for a in config['accessories']:
            if not a.get('rest_positions_approved',False):
                raise ValueError(a['id']+': rest_positions_approved must be true (original design dimensions)')
            if a['anchor_bone'] not in rig.data.bones:
                raise ValueError(a['id']+': missing anchor bone')
            for name in a['mesh_objects']:
                ob=bpy.data.objects.get(name)
                if ob is None or ob.type!='MESH':raise ValueError(a['id']+': missing accessory mesh '+name)
                for mod in ob.modifiers:
                    if mod.type=='ARMATURE' and mod.object and mod.object!=rig:
                        raise ValueError('mesh has different Armature modifier '+name)
            for b in a['bones']:
                old=rig.data.bones.get(b['name'])
                if old:
                    expected=a['anchor_bone'] if b is a['bones'][0] else a['bones'][a['bones'].index(b)-1]['name']
                    if not old.parent or old.parent.name!=expected:
                        raise ValueError('existing bone parent mismatch: '+b['name'])
                    if (old.head_local-Vector(b['head'])).length > 1e-4 or (old.tail_local-Vector(b['tail'])).length > 1e-4:
                        raise ValueError('existing bone coordinates differ; do not move original rig bones: '+b['name'])
        if args.apply:
            bpy.ops.object.mode_set(mode='OBJECT') if bpy.context.object and bpy.context.object.mode!='OBJECT' else None
            bpy.ops.object.select_all(action='DESELECT')
            rig.select_set(True)
            bpy.context.view_layer.objects.active=rig
            bpy.ops.object.mode_set(mode='EDIT')
            try:
                for a in config['accessories']:
                    previous=a['anchor_bone']
                    for b in a['bones']:
                        current=rig.data.edit_bones.get(b['name'])
                        if current:
                            result['existing_bones'].append(b['name'])
                        else:
                            current=rig.data.edit_bones.new(b['name'])
                            current.head=b['head']
                            current.tail=b['tail']
                            current.use_connect=False
                            current.use_deform=True
                            current.parent=rig.data.edit_bones[previous]
                            result['created_bones'].append(b['name'])
                        previous=b['name']
            finally:
                bpy.ops.object.mode_set(mode='OBJECT')
            for a in config['accessories']:
                for mesh_name in a['mesh_objects']:
                    ob=bpy.data.objects[mesh_name]
                    if not any(m.type=='ARMATURE' and m.object==rig for m in ob.modifiers):
                        arm=ob.modifiers.new('CS2_Accessory_Armature','ARMATURE')
                        arm.object=rig
                    if a.get('weight_mode','manual')=='rigid_auto':
                        for old in list(ob.vertex_groups): ob.vertex_groups.remove(old)
                        group=ob.vertex_groups.new(name=a['bones'][0]['name'])
                        group.add(list(range(len(ob.data.vertices))),1.0,'REPLACE')
                        result['assigned_rigid_weights'].append(mesh_name)
                    elif a.get('weight_mode')=='chain_linear_auto':
                        # Initial weights ONLY on explicitly selected accessory meshes.
                        # Nearest chain segment -> linear blend between adjacent bones.
                        # This is a FIRST PASS, not anatomically safe final skinning.
                        for old in list(ob.vertex_groups):ob.vertex_groups.remove(old)
                        groups=[ob.vertex_groups.new(name=b['name']) for b in a['bones']]
                        relative=rig.matrix_world.inverted_safe() @ ob.matrix_world
                        points=[(Vector(b['head']),Vector(b['tail'])) for b in a['bones']]
                        for vert in ob.data.vertices:
                            p=relative @ vert.co
                            best=None
                            for i,(head,tail) in enumerate(points):
                                axis=tail-head
                                t=max(0.0,min(1.0,(p-head).dot(axis)/axis.length_squared))
                                dist_sq=(p-(head+t*axis)).length_squared
                                if best is None or dist_sq < best[0]:best=(dist_sq,i,t)
                            _,i,t=best
                            if i==len(groups)-1:
                                groups[i].add([vert.index],1.0,'REPLACE')
                            else:
                                if (1-t)>1e-7:groups[i].add([vert.index],1-t,'REPLACE')
                                if t>1e-7:groups[i+1].add([vert.index],t,'REPLACE')
                        result['assigned_chain_weights'].append(mesh_name)
                    else:
                        result['manual_weights_pending'].append(mesh_name)
            output=Path(args.out).expanduser().resolve()
            if Path(bpy.data.filepath).resolve()==output:
                raise ValueError('output path must differ from original blend')
            output.parent.mkdir(parents=True,exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=str(output),copy=True)
            result['output_blend']=str(output)
            result['status']='PREPARED_NEEDS_WEIGHT_REVIEW' if result['manual_weights_pending'] else 'PREPARED_REAUDIT_REQUIRED'
        else:
            result['planned_bones']=[b['name'] for a in config['accessories'] for b in a['bones']]
    except Exception as exc:
        result['status']='FAIL'
        result['error']=str(exc)
    out=Path(args.report)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print('Accessory setup:',result['status'],'->',out)
    if result['status']=='FAIL':raise SystemExit(2)

if __name__=='__main__':main()
