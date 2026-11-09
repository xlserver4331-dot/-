"""Optional Blender SOURCE -> CS2 TARGET animation driver constraints builder.

DRY RUN by default. Requires manually aligned reference/rest orientations.

blender -b project.blend --python scripts/blender_retarget_setup.py -- \
  --source MixamoRig --target CS2_Rig --mapping config/retarget_map.example.json

To actually modify current Blender scene add --apply. It does not save the .blend.
It does NOT bake, construct AG2 runtime graphs, or fix different bone axes.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy

PREFIX = "CS2_SKILL_RETARGET_"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="Existing source Armature object")
    ap.add_argument("--target", required=True, help="Existing target CS2 Armature object")
    ap.add_argument("--mapping", required=True, help="JSON mapping source_name -> target_name")
    ap.add_argument("--mode", choices=("ROTATION", "TRANSFORMS"), default="ROTATION")
    ap.add_argument("--space", choices=("WORLD", "LOCAL"), default="WORLD")
    ap.add_argument("--apply", action="store_true", help="Actually create Blender constraints (default: dry run)")
    return ap.parse_args(argv)


def main():
    args = parse_args()
    source, target = bpy.data.objects.get(args.source), bpy.data.objects.get(args.target)
    if source is None or source.type != "ARMATURE":
        raise ValueError("找不到 source Armature")
    if target is None or target.type != "ARMATURE":
        raise ValueError("找不到 target Armature")
    if source is target:
        raise ValueError("source 和 target 不能是同一个 Armature")
    config = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    mapping = config["mapping"]
    errors = []
    plans = []
    for src_name, dst_name in mapping.items():
        if src_name not in source.pose.bones:
            errors.append(f"source missing: {src_name}")
        if dst_name not in target.pose.bones:
            errors.append(f"target missing: {dst_name}")
        plans.append((src_name, dst_name))
    if errors:
        print("Mapping errors:\n" + "\n".join(errors))
        raise SystemExit(2)

    print(f"Checked {len(plans)} mapped bones; mode={args.mode}, space={args.space}")
    print("WARNING: Before --apply, manually align source and target rest pose, units and coordinate axes.")
    if not args.apply:
        print("DRY RUN: no Blender constraints were created")
        return

    constraint_type = "COPY_ROTATION" if args.mode == "ROTATION" else "COPY_TRANSFORMS"
    for src_name, dst_name in plans:
        bone = target.pose.bones[dst_name]
        constraint_name = PREFIX + args.mode
        # Idempotent only for constraints from this tool, not for unrelated author constraints.
        for existing in list(bone.constraints):
            if existing.name.startswith(PREFIX):
                bone.constraints.remove(existing)
        constraint = bone.constraints.new(type=constraint_type)
        constraint.name = constraint_name
        constraint.target = source
        constraint.subtarget = src_name
        constraint.target_space = args.space
        constraint.owner_space = args.space
        constraint.influence = 1.0
    bpy.context.view_layer.update()
    print("Created constraints in current scene; preview each pose, then Bake Action and remove constraints.")
    print("No .blend was saved. Blender constraints are authoring aids, NOT an AG2 runtime driver.")


if __name__ == "__main__":
    main()
