"""EXPLICIT human-approved duplicate seam welding; never guess or fill holes.

Requires: user-approved exact mesh/vertex pairs, source .blend hash, no shape
keys, near-identical co/UV/material/weights, no adjacent/same-face vertices.
Dry-run by default. Apply saves a NEW .blend to the requested output only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
import bpy
import bmesh
from mesh_gap_math import distance


def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def weights(obj, vert):
    return {obj.vertex_groups[g.group].name:float(g.weight) for g in vert.groups if g.weight>1e-10}


def uv_sets(mesh, vertex_index):
    # Each UV corner is intentional. UV seams are not safe to auto-weld.
    if not mesh.uv_layers:return None
    values=[]
    for layer in mesh.uv_layers:
        coords=[tuple(layer.data[i].uv) for i,loop in enumerate(mesh.loops) if loop.vertex_index==vertex_index]
        values.append(coords)
    return values


def validate_pair(obj, keep, merge, distance_limit, weight_tolerance, uv_tolerance):
    mesh=obj.data
    if keep==merge or not (0<=keep<len(mesh.vertices) and 0<=merge<len(mesh.vertices)):
        raise ValueError('vertex index invalid')
    if mesh.shape_keys is not None:raise ValueError('shape keys present; welding changes topology / shape keys')
    if mesh.users>1 or mesh.library or obj.library:raise ValueError('linked/multi-user mesh data requires an isolated duplicate')
    changing={'REMESH','DECIMATE','SUBSURF','MIRROR','BOOLEAN','NODES','WELD','TRIANGULATE','SOLIDIFY'}
    for mod in obj.modifiers:
        if mod.type in changing:raise ValueError(f'topology-changing modifier present: {mod.name} / {mod.type}')
    va,vb=mesh.vertices[keep],mesh.vertices[merge]
    if distance(va.co,vb.co)>distance_limit:
        raise ValueError('rest vertex positions too far apart')
    if any(keep in p.vertices and merge in p.vertices for p in mesh.polygons):
        raise ValueError('both vertices occur in same face (would collapse triangle/quad)')
    if any(keep in e.vertices and merge in e.vertices for e in mesh.edges):
        raise ValueError('vertices directly linked by edge (would collapse edge)')
    wa,wb=weights(obj,va),weights(obj,vb)
    if any(abs(wa.get(k,0)-wb.get(k,0))>weight_tolerance for k in set(wa)|set(wb)):
        raise ValueError('vertex skin weights differ, fix weights BEFORE seam weld')
    ua,ub=uv_sets(mesh,keep),uv_sets(mesh,merge)
    if ua is None or ub is None:raise ValueError('missing UV: manual review required')
    if len(ua)!=len(ub):raise ValueError('UV layer count differs')
    for la,lb in zip(ua,ub):
        if not la or not lb:
            raise ValueError('UV on seam vertices is incomplete')
        points=la+lb
        ref=points[0]
        if any(distance(ref,p)>uv_tolerance for p in points):
            raise ValueError('UV discontinuity: likely intentional UV seam or texture boundary')
    mat_a={p.material_index for p in mesh.polygons if keep in p.vertices}
    mat_b={p.material_index for p in mesh.polygons if merge in p.vertices}
    if mat_a!=mat_b:raise ValueError('material boundaries differ')
    return {'mesh':obj.name,'keep_vertex':keep,'merge_vertex':merge,
            'rest_gap':distance(va.co,vb.co),'weights_match':True,'uv_match':True}


def run(config, out, report_path, apply):
    status={'status':'PENDING_APPROVAL','apply':apply,'repairs':[],'errors':[],'output_blend':None}
    try:
        source=Path(bpy.data.filepath)
        if not source.is_file():raise ValueError('input .blend must be saved on disk')
        expected=config.get('source_blend_sha256')
        if not isinstance(expected,str) or len(expected)!=64:
            raise ValueError('calibrate source_blend_sha256 to exact input file before running')
        current=hashlib.sha256(source.read_bytes()).hexdigest()
        if current.lower()!=expected.lower():raise ValueError('source .blend hash does not match reviewed file')
        if not config.get('user_approved_exact_pairs',False):raise ValueError('user_approved_exact_pairs must be true')
        entries=config.get('repairs',[])
        if not entries:raise ValueError('repair list empty')
        out=Path(out).resolve()
        if out==source.resolve():raise ValueError('output must be a NEW .blend; original cannot be overwritten')
        if out.exists():raise ValueError('output .blend already exists; refuse overwrite')
        seen=set()
        validated=[]
        for spec in entries:
            name=spec['mesh']
            obj=bpy.data.objects.get(name)
            if obj is None or obj.type!='MESH':raise ValueError(f'missing mesh object {name}')
            keep,merge=spec['keep_vertex'],spec['merge_vertex']
            if not isinstance(keep,int) or not isinstance(merge,int):raise ValueError('indices must be integers')
            if (name,keep) in seen or (name,merge) in seen:raise ValueError('one vertex appears in several repair pairs')
            seen.update({(name,keep),(name,merge)})
            row=validate_pair(obj,keep,merge,
                              float(spec.get('max_rest_distance',0)),
                              float(spec.get('max_weight_difference',0)),
                              float(spec.get('max_uv_difference',0)))
            validated.append((obj,keep,merge))
            status['repairs'].append(row)
        if apply:
            # Weld multiple pairs per object in one BMesh pass; source indices
            # are only valid prior to the first topology-changing operation.
            by_mesh={}
            for obj,keep,merge in validated:by_mesh.setdefault(obj,[]).append((keep,merge))
            for obj,pairs in by_mesh.items():
                bm=bmesh.new()
                try:
                    bm.from_mesh(obj.data)
                    bm.verts.ensure_lookup_table()
                    targetmap={bm.verts[merge]:bm.verts[keep] for keep,merge in pairs}
                    bmesh.ops.weld_verts(bm,targetmap=targetmap)
                    bm.to_mesh(obj.data)
                    obj.data.update()
                finally:
                    bm.free()
            out.parent.mkdir(parents=True,exist_ok=True)
            bpy.ops.wm.save_as_mainfile(filepath=str(out),check_existing=False)
            status['output_blend']=str(out)
            status['status']='APPLIED_REQUIRES_REAUDIT'
        else:status['status']='DRY_RUN_REVIEWED'
    except Exception as exc:
        status['errors'].append(str(exc))
        status['status']='FAIL'
    Path(report_path).parent.mkdir(parents=True,exist_ok=True)
    Path(report_path).write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    return status


def main():
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--report',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args(argv)
    result=run(load(args.config),args.out,args.report,args.apply)
    print(result['status'],args.report)
    if result['status']=='FAIL':raise SystemExit(2)

if __name__=='__main__':main()
