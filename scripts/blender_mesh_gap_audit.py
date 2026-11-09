"""Audit actual mesh openings + user-reviewed dynamic seam pairs in Blender.

No destructive changes. Reports topology, visible candidate seam splits and
explicit reviewed seam failures. The optional candidate discovery is for
triage only; candidate pairs never count as a confirmed tear by themselves.
"""
from __future__ import annotations
import math
import bpy
import bmesh
from mesh_gap_math import seam_drift, distance


def audit(config, rig, meshes, actions):
    out={'status':'PENDING_REVIEW','topology':{},'reviewed_seams':{},
         'seam_candidates':[], 'errors':[], 'warnings':[],
         'actions_tested':[], 'evaluated_pose_meshes':0,
         'note':'Source-geometry audit only. UV/material alpha artifacts, occluded surfaces, self-intersection and compiled CS2 meshes need visual and runtime review.'}
    if not isinstance(config,dict):
        out['errors'].append('mesh_integrity config must be an object');out['status']='FAIL';return out
    objects={m.name:m for m in meshes}
    approved=set(config.get('approved_open_meshes',[]))
    for name in approved:
        if name not in objects:out['errors'].append(f'approved_open_meshes nonexistent mesh: {name}')
    dg=bpy.context.evaluated_depsgraph_get()
    inverse=rig.matrix_world.inverted_safe()
    old_frame=bpy.context.scene.frame_current
    old_pose=rig.data.pose_position
    anim=rig.animation_data_create()
    old_action=anim.action
    rest={}
    boundary={}

    def points(obj):
        ob=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        em=ob.to_mesh()
        if em is None:return None
        try:
            transform=inverse @ ob.matrix_world
            return [tuple(transform@v.co) for v in em.vertices]
        finally:
            ob.to_mesh_clear()

    try:
        rig.data.pose_position='REST'
        bpy.context.view_layer.update()
        for obj in meshes:
            m=obj.data
            bm=bmesh.new()
            try:
                bm.from_mesh(m)
                bm.verts.index_update()
                rim=[e for e in bm.edges if e.is_boundary]
                non_manifold=[e for e in bm.edges if not e.is_manifold and not e.is_boundary]
                loose=[e for e in bm.edges if e.is_wire]
                degenerate=sum(1 for f in bm.faces if f.calc_area()<=1e-12)
                boundary[obj.name]={v.index for e in rim for v in e.verts}
                out['topology'][obj.name]={
                    'vertices':len(m.vertices),'faces':len(m.polygons),
                    'boundary_edges':len(rim),'boundary_vertex_examples':sorted(boundary[obj.name])[:50],
                    'non_manifold_non_boundary_edges':len(non_manifold),
                    'loose_edges':len(loose),'degenerate_faces':degenerate,
                    'open_surface_approved':obj.name in approved}
                if non_manifold or loose or degenerate:
                    out['errors'].append(f'{obj.name}: non-manifold/wire/zero-area geometry; inspect topology')
                if rim and obj.name not in approved:
                    out['warnings'].append(f'{obj.name}: {len(rim)} open boundary edges not yet reviewed as intentional')
            finally:
                bm.free()
            rest[obj.name]=points(obj)
            if rest[obj.name] is None or len(rest[obj.name])!=len(obj.data.vertices):
                out['errors'].append(f'{obj.name}: evaluated REST topology differs; cannot index seam vertices safely')
        # All automatic candidates are review-only. Never silently invent a weld/fill target.
        discover=float(config.get('candidate_rest_distance',0.0005))
        max_candidates=max(0,min(1000,int(config.get('max_candidates',100))))
        if 0<discover<1 and max_candidates:
            entries=[]
            neighbors={name:{} for name in objects}
            for name,obj in objects.items():
                for edge in obj.data.edges:
                    a,b=tuple(edge.vertices)
                    neighbors[name].setdefault(a,set()).add(b)
                    neighbors[name].setdefault(b,set()).add(a)
            for name,indices in boundary.items():
                coords=rest.get(name)
                if coords and len(coords)==len(objects[name].data.vertices):
                    for i in sorted(indices):entries.append((name,i,coords[i]))
            buckets={}
            for mesh_name,i,co in entries:
                cell=tuple(math.floor(v/discover) for v in co)
                for x in (-1,0,1):
                    for y in (-1,0,1):
                        for z in (-1,0,1):
                            for other_mesh,other_idx,other_co in buckets.get((cell[0]+x,cell[1]+y,cell[2]+z),[]):
                                if mesh_name==other_mesh and (i==other_idx or other_idx in neighbors[mesh_name].get(i,set())):
                                    continue
                                if distance(co,other_co)<=discover:
                                    out['seam_candidates'].append({'a':[other_mesh,other_idx], 'b':[mesh_name,i],
                                        'rest_gap':distance(co,other_co),'review':'CANDIDATE_ONLY'})
                                    if len(out['seam_candidates'])>=max_candidates:break
                            if len(out['seam_candidates'])>=max_candidates:break
                        if len(out['seam_candidates'])>=max_candidates:break
                    if len(out['seam_candidates'])>=max_candidates:break
                buckets.setdefault(cell,[]).append((mesh_name,i,co))
                if len(out['seam_candidates'])>=max_candidates:break
        specs=[]
        ids=set()
        for spec in config.get('reviewed_seam_pairs',[]):
            try:
                seam_id=str(spec['id'])
                if seam_id in ids:raise ValueError('duplicate id')
                ids.add(seam_id)
                a,b=spec['a'],spec['b']
                for endpoint in (a,b):
                    if not isinstance(endpoint,list) or len(endpoint)!=2:raise ValueError('endpoint must be [mesh, vertex_index]')
                    name,idx=endpoint
                    if name not in objects or not isinstance(idx,int) or idx<0 or not rest.get(name) or idx>=len(rest[name]):
                        raise ValueError('invalid endpoint or evaluated topology')
                max_gap=float(spec['max_pose_gap'])
                max_growth=float(spec.get('max_gap_growth',max_gap/2))
                if max_gap<=0 or max_growth<0:raise ValueError('gap thresholds must be calibrated')
                specs.append((seam_id,a,b,max_gap,max_growth))
                out['reviewed_seams'][seam_id]={'status':'PENDING_ACTIONS','rest_gap':distance(rest[a[0]][a[1]],rest[b[0]][b[1]]), 'max_pose_gap':max_gap,'max_gap_growth':max_growth,'violations':[]}
            except (ValueError,KeyError,TypeError) as exc:
                out['errors'].append({'seam':spec.get('id') if isinstance(spec,dict) else '?','reason':str(exc)})
        names=list(actions or ([old_action.name] if old_action else []))
        step=int(config.get('sample_step_frames',3))
        if step<1:out['errors'].append('sample_step_frames must be >= 1');step=3
        max_frames=int(config.get('max_frames_per_action',60))
        if max_frames<2:out['errors'].append('max_frames_per_action must be >= 2');max_frames=60
        rig.data.pose_position='POSE'
        bpy.context.view_layer.update()
        for name in names:
            act=bpy.data.actions.get(name)
            if not act:
                out['warnings'].append(f'Action missing: {name}');continue
            try:
                anim.action=act
            except Exception as exc:
                out['warnings'].append(f'Action assignment failed: {name}: {exc}');continue
            first,last=map(float,act.frame_range)
            frames=sorted(set(list(range(math.floor(first), math.ceil(last)+1,step))+[math.ceil(last)]))
            if len(frames)>max_frames:
                frames=sorted(set(frames[round(i*(len(frames)-1)/(max_frames-1))] for i in range(max_frames)))
                out['warnings'].append(f'Action {name}: frame cap applied')
            for frame in frames:
                bpy.context.scene.frame_set(frame)
                bpy.context.view_layer.update()
                involved={endpoint[0] for _,a,b,_,_ in specs for endpoint in (a,b)}
                posed={mesh_name:points(objects[mesh_name]) for mesh_name in involved}
                out['evaluated_pose_meshes']+=len(involved)
                for seam_id,a,b,max_gap,max_growth in specs:
                    if posed.get(a[0]) is None or posed.get(b[0]) is None or len(posed[a[0]])!=len(rest[a[0]]) or len(posed[b[0]])!=len(rest[b[0]]):
                        out['warnings'].append(f'{seam_id}: topology changes in action {name} frame {frame}')
                        continue
                    result=seam_drift(rest[a[0]][a[1]],rest[b[0]][b[1]],posed[a[0]][a[1]],posed[b[0]][b[1]],max_gap=max_gap,max_increase=max_growth)
                    result.update({'action':name,'frame':frame})
                    if result['failed']:
                        out['reviewed_seams'][seam_id]['violations'].append(result)
            out['actions_tested'].append(name)
        for seam_id in out['reviewed_seams']:
            v=out['reviewed_seams'][seam_id]['violations']
            if v:
                out['reviewed_seams'][seam_id]['status']='FAIL'
                out['reviewed_seams'][seam_id]['count']=len(v)
                out['reviewed_seams'][seam_id]['examples']=v[:15]
                del out['reviewed_seams'][seam_id]['violations']
            elif names and len(out['actions_tested'])==len(names):
                out['reviewed_seams'][seam_id]['status']='PASS_PRELIMINARY'
                del out['reviewed_seams'][seam_id]['violations']
    finally:
        rig.data.pose_position=old_pose
        anim.action=old_action
        bpy.context.scene.frame_set(old_frame)
        bpy.context.view_layer.update()
    if out['errors'] or any(s['status']=='FAIL' for s in out['reviewed_seams'].values()):
        out['status']='FAIL'
    elif (out['warnings'] or not names or (config.get('require_reviewed_seams',False) and not specs)
          or (specs and len(names)!=len(out['actions_tested']))):
        out['status']='PENDING_REVIEW'
    else:
        out['status']='PASS_PRELIMINARY'
    return out
