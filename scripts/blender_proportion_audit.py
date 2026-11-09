"""Capture original character limb lengths; audit target CS2 rig without resizing limbs.

Only local Blender bpy. This script NEVER applies a scale, moves a bone or changes a mesh.
Measure armature-rest bone HEAD-to-HEAD joint distances. Use trustworthy original files,
and independently calibrated torso anchors to estimate a single permitted global scale.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proportion_math import evaluate_proportions, anisotropy, pose_length_deviation


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fingerprint(profile):
    blob = json.dumps(profile.get("measurements", []), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def select_armature(name):
    rig = bpy.data.objects.get(name)
    if rig is None or rig.type != "ARMATURE":
        raise ValueError(f"Missing calibrated Armature: {name}")
    return rig


def rest_measurements(rig, profile, field):
    values, errors = {}, []
    bones = rig.data.bones
    for record in profile["measurements"]:
        key = record["id"]
        pair = record[field]
        if len(pair) != 2 or pair[0] not in bones or pair[1] not in bones:
            errors.append({"segment": key, "missing_or_invalid_pair": pair})
            continue
        dist = float((bones[pair[1]].head_local - bones[pair[0]].head_local).length)
        if dist < 1e-8:
            errors.append({"segment": key, "zero_joint_distance": pair})
        else:
            values[key] = dist
    return values, errors


def capture(profile):
    rig = select_armature(profile["source_armature"])
    lengths, errors = rest_measurements(rig, profile, "source")
    source_file = Path(bpy.data.filepath)
    source_sha = hashlib.sha256(source_file.read_bytes()).hexdigest() if source_file.is_file() else None
    return {"status": "FAIL" if errors else "CAPTURED_SOURCE_REFERENCE", "schema_version": 1,
            "source_file": str(source_file), "source_sha256": source_sha,
            "source_armature": rig.name, "profile_fingerprint": fingerprint(profile),
            "anchor_ids": [r["id"] for r in profile["measurements"] if r.get("anchor")],
            "segments": lengths, "errors": errors,
            "note": "Baseline from ORIGINAL character, not Valve agent. Keep immutable; use same profile when auditing."}


def animation_stretch_check(rig, profile, action_names):
    anim = rig.animation_data_create()
    old_action, old_frame, old_pose = anim.action, bpy.context.scene.frame_current, rig.data.pose_position
    step = max(1, int(profile.get("sample_step_frames", 3)))
    tolerance = float(profile.get("max_pose_stretch", 0.015))
    violations, pending = [], []
    pairs = [r for r in profile["measurements"] if not r.get("anchor")]
    # Target parent-child joints only, otherwise flexion naturally changes head-to-head distance.
    direct = []
    for r in pairs:
        a, b = r["target"]
        parent, child = rig.data.bones.get(a), rig.data.bones.get(b)
        if parent and child and child.parent == parent:
            direct.append((r["id"], a, b, float((child.head_local - parent.head_local).length)))
        else:
            pending.append({"id": r["id"], "reason": "not a direct joint; cannot use fixed-distance pose test"})
    names = list(action_names or ([old_action.name] if old_action else []))
    try:
        rig.data.pose_position = "POSE"
        for action_name in names:
            action = bpy.data.actions.get(action_name)
            if not action:
                pending.append({"action": action_name, "reason": "Action missing"})
                continue
            try:
                anim.action = action
                start, end = (int(action.frame_range[0]), int(action.frame_range[1]))
                frames = sorted(set(list(range(start, end + 1, step)) + [end]))
                for frame in frames:
                    bpy.context.scene.frame_set(frame)
                    bpy.context.view_layer.update()
                    for key, a, b, rest_length in direct:
                        pa, pb = rig.pose.bones.get(a), rig.pose.bones.get(b)
                        if not pa or not pb:
                            continue
                        deviation = pose_length_deviation(rest_length, float((pb.head - pa.head).length))
                        if deviation is not None and deviation > tolerance:
                            violations.append({"action": action_name, "frame": frame, "segment": key,
                                               "stretch_relative": deviation, "tolerance": tolerance})
            except Exception as exc:
                pending.append({"action": action_name, "reason": str(exc)})
    finally:
        anim.action = old_action
        rig.data.pose_position = old_pose
        bpy.context.scene.frame_set(old_frame)
        bpy.context.view_layer.update()
    stretch_controls = []
    for bone in rig.pose.bones:
        for constraint in bone.constraints:
            if constraint.type in {"STRETCH_TO", "COPY_SCALE"}:
                stretch_controls.append({"bone": bone.name, "constraint": constraint.type})
        if getattr(bone, "ik_stretch", 0) > 1e-5:
            stretch_controls.append({"bone": bone.name, "ik_stretch": bone.ik_stretch})
    return {"status": "FAIL" if violations or stretch_controls else
            ("PENDING" if pending else ("PENDING_RUNTIME" if not names else "PASS")),
            "actions_tested": names, "violations": violations[:150], "total_violations": len(violations),
            "stretch_constraints": stretch_controls, "pending": pending}


def audit(profile, reference, actions=None):
    if reference.get("profile_fingerprint") != fingerprint(profile):
        return {"status": "FAIL", "reason": "source baseline does not match calibrated measurements config"}
    rig = select_armature(profile["target_armature"])
    current, errors = rest_measurements(rig, profile, "target")
    result = evaluate_proportions(reference, {"segments": current},
                                  tolerance=float(profile.get("max_relative_deviation", 0.03)))
    scale_limit = float(profile.get("max_nonuniform_scale", 0.005))
    linked_objects = [o for o in bpy.context.scene.objects
                      if o.type == "MESH" and (o.parent == rig or any(m.type == "ARMATURE" and m.object == rig for m in o.modifiers))]
    scale_violations = [{"object": o.name, "scale": list(o.scale), "anisotropy": anisotropy(o.scale)}
                        for o in [rig, *linked_objects] if anisotropy(o.scale) > scale_limit]
    pose = animation_stretch_check(rig, profile, actions)
    result.update({"source_reference": reference.get("source_file"),
                   "rest_measurement_errors": errors, "object_scale_violations": scale_violations,
                   "pose_stretch": pose,
                   "original_model_reference_used": True,
                   "notes": "Never stretch limbs to Valve agent proportions. Mesh morphs/visual clipping need separate visual review."})
    if errors or scale_violations or pose["status"] == "FAIL":
        result["status"] = "FAIL"
    elif result["status"] == "PASS" and pose["status"] not in ("PASS", "PENDING_RUNTIME"):
        result["status"] = "PENDING"
    return result


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(description="Preserve ORIGINAL body proportion; never stretch into a Valve agent")
    ap.add_argument("--mode", choices=["capture", "audit"], required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--baseline", help="JSON captured from original pristine .blend")
    ap.add_argument("--out", required=True)
    ap.add_argument("--actions", nargs="*", default=None)
    args = ap.parse_args(argv)
    profile = read(args.config)
    if args.mode == "audit" and not args.baseline:
        ap.error("audit requires --baseline captured from the original source model")
    report = capture(profile) if args.mode == "capture" else audit(profile, read(args.baseline), args.actions)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Proportion {args.mode}: {report['status']} -> {output}")
    if report["status"] == "FAIL":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
