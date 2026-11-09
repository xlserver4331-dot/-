"""Inspect local Blender rig for limb stretches and likely double deformation.

Does not edit any bone. Rest proportion comparison against ORIGINAL source is
already performed by blender_proportion_audit; this adds causal diagnostics.
"""
from __future__ import annotations
import bpy
from mesh_gap_math import relative_length, scale_spread


STRETCHING_TYPES={'STRETCH_TO','COPY_SCALE','MAINTAIN_VOLUME'}


def audit(config, rig, meshes, actions):
    result={'status':'PENDING','errors':[],'warnings':[],'stretch_samples':[],
            'modifier_conflicts':[], 'controls':[], 'actions_tested':[],
            'note':'Bone-head-to-tail pose-length check is NOT a substitute for original-mesh-proportion comparison, animated mesh cracks or compiled AG2 validation.'}
    names=config.get('monitored_bones',[])
    if not names:
        result['warnings'].append('monitored_bones is empty; calibrate from the ORIGINAL character')
        return result
    for name in names:
        b=rig.data.bones.get(name)
        if not b or b.length<=1e-8:
            result['errors'].append(f'Missing or zero length monitored bone: {name}')
    max_stretch=float(config.get('max_pose_bone_length_change',0.015))
    max_scale=float(config.get('max_nonuniform_object_scale',0.005))
    if max_stretch<0 or max_scale<0:
        result['errors'].append('Negative threshold is not allowed')
    for obj in [rig,*meshes]:
        if scale_spread(obj.scale)>max_scale:
            result['errors'].append(f'Nonuniform object scale: {obj.name} {tuple(obj.scale)}')
    for obj in meshes:
        modifiers=[m for m in obj.modifiers if m.type=='ARMATURE']
        target=[m for m in modifiers if m.object == rig and m.show_viewport]
        if len(target)!=1 or len(modifiers)>1:
            entry={'mesh':obj.name,'armature_modifiers':[(m.name,m.object.name if m.object else None) for m in modifiers]}
            result['modifier_conflicts'].append(entry)
            result['errors'].append(f'{obj.name}: expected exactly one active target armature and no foreign armature modifiers')
        if obj.parent == rig and obj.parent_type=='BONE' and target:
            result['warnings'].append(f'{obj.name}: bone-parent + armature modifier may unintentionally double transform')
        for m in obj.modifiers:
            if m.type in {'LATTICE','MESH_DEFORM','SURFACE_DEFORM','HOOK'}:
                result['warnings'].append(f'{obj.name}: additional deformation modifier {m.name}/{m.type}; isolate to diagnose cracks')
    for pb in rig.pose.bones:
        if pb.name not in names:continue
        for c in pb.constraints:
            if c.mute or c.influence<=0:continue
            if c.type in STRETCHING_TYPES or (c.type=='IK' and getattr(c,'use_stretch',False)) or c.type=='SPLINE_IK':
                result['controls'].append({'bone':pb.name,'constraint':c.name,'type':c.type})
            if c.type=='COPY_TRANSFORMS':
                result['warnings'].append(f'{pb.name}: Copy Transforms may import source bone scale; verify rest alignment and spaces')
        if getattr(pb,'ik_stretch',0.0)>1e-6:
            result['controls'].append({'bone':pb.name,'ik_stretch':float(pb.ik_stretch)})
    if result['controls']:
        result['errors'].append('Potential stretch-capable controls on monitored deform bones; inspect and disable in working copy')
    anim=rig.animation_data_create()
    old_action,old_frame,old_pose=anim.action,bpy.context.scene.frame_current,rig.data.pose_position
    selected=list(actions or ([old_action.name] if old_action else []))
    step=int(config.get('sample_step_frames',3))
    cap=int(config.get('max_frames_per_action',60))
    if step<=0 or cap<2:result['errors'].append('sample_step_frames >=1 and max_frames_per_action >=2 required')
    else:
        try:
            rig.data.pose_position='POSE'
            for action_name in selected:
                action=bpy.data.actions.get(action_name)
                if action is None:
                    result['warnings'].append(f'Missing Action: {action_name}');continue
                try:anim.action=action
                except Exception as exc:
                    result['warnings'].append(f'Cannot assign Action {action_name}: {exc}');continue
                start,end=map(int,action.frame_range)
                frames=sorted(set(list(range(start,end+1,step))+[end]))
                if len(frames)>cap:frames=sorted(set(frames[round(i*(len(frames)-1)/(cap-1))] for i in range(cap)))
                for frame in frames:
                    bpy.context.scene.frame_set(frame)
                    bpy.context.view_layer.update()
                    for name in names:
                        rest=rig.data.bones.get(name)
                        pb=rig.pose.bones.get(name)
                        if not rest or not pb:continue
                        current=(pb.tail-pb.head).length
                        d=relative_length(rest.length,current)
                        if d>max_stretch:
                            result['stretch_samples'].append({'bone':name,'action':action_name,'frame':frame,
                                                             'rest_length':rest.length,'pose_length':current,
                                                             'relative_change':d})
                result['actions_tested'].append(action_name)
        finally:
            anim.action=old_action
            rig.data.pose_position=old_pose
            bpy.context.scene.frame_set(old_frame)
            bpy.context.view_layer.update()
    if result['stretch_samples']:
        result['errors'].append('Monitored bones change geometric length during animation')
    if result['errors']:
        result['status']='FAIL'
    elif result['warnings'] or not selected or len(selected)!=len(result['actions_tested']):
        result['status']='PENDING_REVIEW'
    else:
        result['status']='PASS_PRELIMINARY'
    result['stretch_samples_total']=len(result['stretch_samples'])
    result['stretch_samples']=result['stretch_samples'][:120]
    return result
