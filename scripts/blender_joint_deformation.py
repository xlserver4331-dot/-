"""Source animation joint deformation analyzer (Blender bpy).

Source topology & armature-local poses must match across frames. Static audit
only: does NOT prove absence of interpenetration or physics ragdoll errors.
Execution complexity: samples each mesh ONCE per (Action, frame), not per joint.
"""
from __future__ import annotations
import math
import bpy
from deformation_metrics import compare_region


def audit(config, rig, associated_meshes, action_names, excluded=None):
    joints = config.get('joints', [])
    result = {'status':'PENDING', 'joints':{},'warnings':[], 'errors':[],
              'actions_tested':[], 'evaluated_pose_meshes':0,
              'note':'Source pose geometry only. Legitimate bend creases can need threshold calibration; no self-intersection, clothing penetration, ragdoll or runtime checks.'}
    if not isinstance(joints,list) or not joints:
        result['warnings'].append('没有配置任何关节检测范围')
        return result
    excluded=set(excluded or [])
    all_meshes={m.name:m for m in associated_meshes}
    body_meshes={n:m for n,m in all_meshes.items() if n not in excluded}
    anim=rig.animation_data_create()
    old_action, old_pose, old_frame=anim.action,rig.data.pose_position,bpy.context.scene.frame_current
    selected=list(action_names or ([old_action.name] if old_action else []))
    if not selected:result['warnings'].append('没有源 Action，需编写 Blender 关节弯曲测试 Action 或提供运行时引擎证据')
    for a in selected:
        if bpy.data.actions.get(a) is None:
            result['errors'].append({'action':a,'reason':'Action missing'})

    def evaluated_mesh(obj):
        dg=bpy.context.evaluated_depsgraph_get()
        eval_obj=obj.evaluated_get(dg)
        mesh=eval_obj.to_mesh()
        if mesh is None:return None
        try:
            relative=rig.matrix_world.inverted_safe() @ eval_obj.matrix_world
            verts=[tuple(relative @ vert.co) for vert in mesh.vertices]
            edges={tuple(sorted(edge.vertices)) for edge in mesh.edges}
            return (verts,edges)
        finally:eval_obj.to_mesh_clear()

    try:
        rig.data.pose_position='REST'
        bpy.context.view_layer.update()
        rest={name:evaluated_mesh(obj) for name,obj in all_meshes.items()}
        rig.data.pose_position='POSE'
        bpy.context.view_layer.update()
        specifications={}
        for joint in joints:
            name=joint.get('id')
            if not isinstance(name,str) or not name or name in result['joints']:
                result['errors'].append({'joint':name,'reason':'missing/duplicate joint id'});continue
            parent=rig.data.bones.get(joint.get('parent_bone'))
            child=rig.data.bones.get(joint.get('child_bone'))
            if parent is None or child is None or child.parent!=parent:
                result['errors'].append({'joint':name,'reason':'missing joint bones or wrong parent'});continue
            radius=float(joint.get('radius',0))
            if not 0 < radius < 1e6:
                result['warnings'].append({'joint':name,'reason':'joint radius not calibrated in armature-object space'});
                result['joints'][name]={'status':'PENDING_RADIUS'}
                continue
            explicit=joint.get('mesh_objects')
            mesh_names=explicit if explicit else list(body_meshes)
            if not isinstance(mesh_names,list):
                result['errors'].append({'joint':name,'reason':'mesh_objects must be array'});continue
            tracked=[]
            for mesh_name in mesh_names:
                obj=(all_meshes if explicit else body_meshes).get(mesh_name)
                if obj is None or rest.get(mesh_name) is None:
                    result['errors'].append({'joint':name,'mesh':mesh_name,'reason':'mesh missing or unattached'});continue
                points, topology=rest[mesh_name]
                data=obj.data
                if len(points)!=len(data.vertices) or topology!={tuple(sorted(edge.vertices)) for edge in data.edges}:
                    result['warnings'].append({'joint':name,'mesh':mesh_name,'reason':'source/evaluated topology differs'});continue
                groups={group.index:group.name for group in obj.vertex_groups}
                minimum=float(joint.get('minimum_weight',0.02))
                eligible=set()
                center=child.head_local
                for vert in data.vertices:
                    a_weight,b_weight=0.0,0.0
                    for binding in vert.groups:
                        bname=groups.get(binding.group)
                        if bname==parent.name:a_weight=binding.weight
                        if bname==child.name:b_weight=binding.weight
                    if max(a_weight,b_weight)>=minimum and math.dist(points[vert.index],center)<=radius:
                        eligible.add(vert.index)
                edges=[tuple(edge.vertices) for edge in data.edges if set(edge.vertices).issubset(eligible)]
                triangles=[]
                for poly in data.polygons:
                    vv=list(poly.vertices)
                    if not set(vv).issubset(eligible):continue
                    for i in range(1,len(vv)-1):triangles.append((vv[0],vv[i],vv[i+1]))
                max_edges=int(joint.get('max_region_edges',config.get('max_region_edges',6000)))
                if not 1 <= max_edges <= 100000:
                    result['errors'].append({'joint':name,'reason':'invalid max_region_edges'});continue
                if len(edges)>max_edges:
                    result['warnings'].append({'joint':name,'reason':'region edge limit reached','total':len(edges)})
                    edges=edges[:max_edges]
                if not edges:
                    result['warnings'].append({'joint':name,'mesh':mesh_name,'reason':'empty skinning/geometry region'});continue
                tracked.append({'name':mesh_name,'object':obj,'rest':points,'topology':topology,
                                'edges':edges,'triangles':triangles})
            if not tracked:
                result['joints'][name]={'status':'PENDING_EMPTY_REGION'}
            else:
                result['joints'][name]={'status':'PENDING_RUNTIME' if not selected else 'PASS_PRELIMINARY',
                                       'sampled_meshes':[v['name'] for v in tracked],
                                       'errors_total':0,'examples':[]}
                specifications[name]={'definition':joint,'meshes':tracked,'violations':[]}

        # Single time sweep shared by all joints; expensive mesh evaluation is cached
        # for the current frame only and discarded before advancing to next frame.
        for action_name in selected:
            action=bpy.data.actions.get(action_name)
            if action is None:continue
            anim.action=action
            first,last=action.frame_range
            steps={}
            for key,spec in specifications.items():
                j=spec['definition']
                step=max(1,int(j.get('sample_step_frames',config.get('sample_step_frames',3))))
                frames=sorted(set(list(range(math.floor(first),math.ceil(last)+1,step))+[math.ceil(last)]))
                cap=max(2,int(config.get('max_frames_per_action',40)))
                if len(frames)>cap:
                    frames=sorted(set(frames[round(i*(len(frames)-1)/(cap-1))] for i in range(cap)))
                    result['warnings'].append({'joint':key,'action':action_name,'reason':'frame sampling capped'})
                steps[key]=set(frames)
            for frame in sorted(set.union(*steps.values()) if steps else set()):
                bpy.context.scene.frame_set(frame)
                bpy.context.view_layer.update()
                active={k:v for k,v in specifications.items() if frame in steps[k]}
                required={row['name']:row['object'] for spec in active.values() for row in spec['meshes']}
                deformed={name:evaluated_mesh(obj) for name,obj in required.items()}
                result['evaluated_pose_meshes']+=len(required)
                for joint_name,spec in active.items():
                    for row in spec['meshes']:
                        current=deformed.get(row['name'])
                        if current is None or current[1]!=row['topology']:
                            result['warnings'].append({'joint':joint_name,'mesh':row['name'],'action':action_name,
                                                       'frame':frame,'reason':'pose topology altered'});continue
                        j=spec['definition']
                        metrics=compare_region(row['rest'],current[0],row['edges'],row['triangles'],
                            max_edge_change=float(j.get('max_edge_change',0.45)),
                            max_area_change=float(j.get('max_area_change',0.75)))
                        if metrics['status']=='FAIL':
                            spec['violations'].append({'mesh':row['name'],'action':action_name,'frame':frame,**metrics})
            result['actions_tested'].append(action_name)
        for name,spec in specifications.items():
            found=spec['violations']
            if found:
                result['joints'][name].update({'status':'FAIL','errors_total':len(found),'examples':found[:30]})
    finally:
        anim.action=old_action
        rig.data.pose_position=old_pose
        bpy.context.scene.frame_set(old_frame)
        bpy.context.view_layer.update()

    if result['errors'] or any(item['status']=='FAIL' for item in result['joints'].values()):
        result['status']='FAIL'
    elif result['warnings'] or not selected or any(item['status']!='PASS_PRELIMINARY' for item in result['joints'].values()):
        result['status']='PENDING_REVIEW'
    else:result['status']='PASS_PRELIMINARY'
    return result
