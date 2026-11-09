"""Accessory support-bone + binding audit, never claims runtime physics works."""
import bpy
import math
import re
from accessory_core import validated_config


def audit(config, rig, meshes, action_names=None):
    result={"status":"PENDING", "items":{},"errors":[],"warnings":[],
            "runtime_physics":"PENDING_RUNTIME", "note":"Source rig only. Secondary bone swing in CS2 needs compatible animations/constraints/physics verified in ModelDoc and game."}
    try:validated_config(config)
    except ValueError as err:
        result["errors"].append(str(err));result["status"]="FAIL";return result
    by_name={m.name:m for m in meshes}
    listed={name for a in config["accessories"] for name in a["mesh_objects"]}
    tagged={obj.name for obj in bpy.context.scene.objects if obj.type=="MESH" and obj.get("cs2_accessory",False)}
    for unlisted in sorted(tagged-listed):
        result["errors"].append({"accessory":unlisted,"reason":"mesh tagged cs2_accessory but not declared in accessory manifest"})
    hints=config.get("inventory_name_hints",["hair", "scarf", "cape", "keychain", "pendant", "strap", "tassel", "ribbon", "earring", "bracelet", "skirt", "backpack", "发辫", "挂件", "披风", "围巾", "裙摆"])
    if not isinstance(hints,list) or any(not isinstance(x,str) or not x for x in hints):
        result["errors"].append("inventory_name_hints must be array of names")
    else:
        guesses={obj.name for obj in bpy.context.scene.objects if obj.type=="MESH"
                 and any(word.casefold() in obj.name.casefold() for word in hints)}
        for unknown in sorted(guesses-listed-tagged):
            result["warnings"].append({"candidate":unknown,"reason":"possible undeclared decorative mesh; classify or tag cs2_accessory"})
    if not config["accessories"]:
        result["status"]="FAIL" if result["errors"] else "PENDING_REVIEW" if result["warnings"] else "PASS_PRELIMINARY"
        result["runtime_physics"]="NOT_APPLICABLE" if result["status"]=="PASS_PRELIMINARY" else "PENDING"
        return result
    minimum=float(config.get("min_deform_weight",0.001))
    for a in config["accessories"]:
        name=a["id"];anchor=rig.data.bones.get(a["anchor_bone"])
        errors=[];warnings=[]
        if anchor is None:errors.append("anchor bone missing")
        if not a.get("rest_positions_approved",False):
            warnings.append("accessory rest positions not approved against the original character")
        prev=anchor
        chain_names=[]
        for specified in a["bones"]:
            bone=rig.data.bones.get(specified["name"])
            chain_names.append(specified["name"])
            if bone is None:
                errors.append("missing support bone: "+specified["name"])
            else:
                if prev and bone.parent!=prev:errors.append("wrong bone parent: "+bone.name)
                if not bone.use_deform:errors.append("support bone not deform: "+bone.name)
                from mathutils import Vector
                tolerance=float(config.get("rest_position_tolerance",0.002))
                if (bone.head_local-Vector(specified["head"])).length>tolerance or (bone.tail_local-Vector(specified["tail"])).length>tolerance:
                    errors.append("support bone rest coordinates differ from approved design: "+bone.name)
                prev=bone
        combined_counts={key:0 for key in chain_names}
        for mesh_name in a["mesh_objects"]:
            obj=by_name.get(mesh_name)
            if obj is None:
                errors.append("mesh missing from audited rig: "+mesh_name);continue
            mods=[m for m in obj.modifiers if m.type=="ARMATURE" and m.object==rig]
            if not mods:errors.append("missing Armature modifier: "+mesh_name)
            bound_counts={key:0 for key in chain_names}
            total=0
            for v in obj.data.vertices:
                vertex_names={obj.vertex_groups[g.group].name:g.weight for g in v.groups}
                valid=sum(weight>minimum for key,weight in vertex_names.items() if key in chain_names)
                if valid:total+=1
                for key in chain_names:
                    if vertex_names.get(key,0)>minimum:bound_counts[key]+=1
            if total==0:errors.append("accessory has no weights on support bones: "+mesh_name)
            if len(obj.data.vertices) and total/len(obj.data.vertices) < float(config.get("min_covered_vertex_fraction",0.70)):
                errors.append(f"accessory support-bone vertex coverage too low: {mesh_name} ({total}/{len(obj.data.vertices)})")
            for key,count in bound_counts.items():
                combined_counts[key]+=count
        for key,count in combined_counts.items():
            if count==0:
                errors.append(f"no painted deformation weight for declared accessory bone: {key}")
        motion = "NOT_REQUIRED" if a["mode"] == "rigid" else "PENDING_RUNTIME"
        action_names = list(action_names or [])
        if a["mode"] == "secondary_baked":
            if not action_names:
                warnings.append("source actions absent; secondary motion cannot be confirmed")
                motion = "PENDING_NO_ACTIONS"
            else:
                anim=rig.animation_data_create()
                prev_action,prev_frame,prev_pose=anim.action,bpy.context.scene.frame_current,rig.data.pose_position
                max_angle=0.0;max_stretch=0.0;sampled=0
                try:
                    rig.data.pose_position="POSE"
                    for action_name in action_names:
                        action=bpy.data.actions.get(action_name)
                        if not action:
                            warnings.append("source Action missing: "+action_name);continue
                        anim.action=action
                        start,end=action.frame_range
                        for frame in sorted(set([int(start),int(round((start+end)/2)),int(end)])):
                            bpy.context.scene.frame_set(frame)
                            bpy.context.view_layer.update()
                            sampled+=1
                            for bone_name in chain_names:
                                pb=rig.pose.bones.get(bone_name)
                                if pb is None or pb.parent is None:continue
                                local=pb.parent.matrix.inverted_safe() @ pb.matrix
                                rest=pb.parent.bone.matrix_local.inverted_safe() @ pb.bone.matrix_local
                                delta=(rest.to_quaternion().rotation_difference(local.to_quaternion())).angle
                                max_angle=max(max_angle,float(delta))
                                rest_length=rig.data.bones[bone_name].length
                                if rest_length>1e-7:
                                    max_stretch=max(max_stretch,abs((pb.tail-pb.head).length/rest_length-1.0))
                finally:
                    anim.action=prev_action
                    rig.data.pose_position=prev_pose
                    bpy.context.scene.frame_set(prev_frame)
                    bpy.context.view_layer.update()
                if max_stretch>float(config.get("max_accessory_bone_stretch",0.03)):
                    errors.append(f"animated accessory bone stretch > limit: {max_stretch:.4f}")
                    motion="FAIL_STRETCH"
                elif sampled==0 or max_angle<float(config.get("min_baked_swing_radians",0.008)):
                    warnings.append("no measurable secondary swing in source Actions; game motion unverified")
                    motion="PENDING_NO_MEASURABLE_SWING"
                else:
                    motion="SOURCE_BAKED_SWING_PRESENT_RUNTIME_PENDING"
        # Non-baked modes must still keep bone lengths if an Action drives them.
        if a["mode"] != "secondary_baked" and action_names:
            anim=rig.animation_data_create()
            saved=(anim.action, bpy.context.scene.frame_current,rig.data.pose_position)
            max_stretch=0.0
            try:
                rig.data.pose_position="POSE"
                for action_name in action_names:
                    action=bpy.data.actions.get(action_name)
                    if action is None:continue
                    anim.action=action
                    start,end=action.frame_range
                    for frame in sorted(set([int(start),int((start+end)/2),int(end)])):
                        bpy.context.scene.frame_set(frame)
                        bpy.context.view_layer.update()
                        for bone_name in chain_names:
                            pb=rig.pose.bones.get(bone_name)
                            rest_length=rig.data.bones[bone_name].length if pb else 0.0
                            if rest_length>1e-7:
                                max_stretch=max(max_stretch,abs((pb.tail-pb.head).length/rest_length-1.0))
            finally:
                anim.action=saved[0]
                rig.data.pose_position=saved[2]
                bpy.context.scene.frame_set(saved[1])
                bpy.context.view_layer.update()
            if max_stretch>float(config.get("max_accessory_bone_stretch",0.03)):
                errors.append(f"accessory bone stretches in Action: {max_stretch:.4f}")
        result["items"][name]={"mode":a["mode"],"anchor":a["anchor_bone"],"bones":chain_names,
                              "errors":errors,"warnings":warnings,"motion_source":motion,
                              "status":"FAIL" if errors else "PENDING_REVIEW" if warnings else "PASS_PRELIMINARY"}
        result["errors"].extend({"accessory":name,"reason":e} for e in errors)
        result["warnings"].extend({"accessory":name,"reason":w} for w in warnings)
    result["status"]="FAIL" if result["errors"] else "PENDING_REVIEW" if result["warnings"] else "PASS_PRELIMINARY"
    return result
