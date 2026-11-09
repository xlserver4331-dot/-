"""Merge Blender audit + manually verified engine checklist. NEVER auto-PASS pending gates."""
import argparse
import json
from pathlib import Path

REQUIRED = {
    "prop_preview": ["modeldoc_compiled", "mesh_materials_visible", "static_bounds_reviewed", "physics_collision_reviewed", "hammer_local_preview"],
    "player_runtime": ["modeldoc_compiled", "mesh_materials_visible", "static_bounds_reviewed", "dynamic_bounds_reviewed", "physics_collision_reviewed", "hitboxes_reviewed", "ag2_binding_live", "weapon_alignment_live", "local_server_mounted", "movement_animation_live", "original_limb_proportions_live", "viewmodel_arms_live", "viewmodel_animation_live", "hit_reaction_live", "death_transition_live", "ragdoll_physics_live", "respawn_live", "animation_suite_live", "accessory_motion_live", "joint_deformation_live", "mesh_cracks_live", "rig_stretch_live"],
}
VALID = {"PASS", "FAIL", "PENDING", "WARN"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", required=True)
    ap.add_argument("--engine", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    blender, engine = read(args.blender), read(args.engine)
    target = engine.get("target", "player_runtime")
    if target not in REQUIRED:
        ap.error(f"未知 target: {target}")
    tests = engine.get("tests", {})
    rows = []
    for key in REQUIRED[target]:
        item = tests.get(key, {})
        status = item.get("status", "PENDING")
        if status not in VALID:
            status = "FAIL"
        # Human assertions without evidence must not pass.
        evidence = item.get("evidence", "")
        if status == "PASS" and not str(evidence).strip():
            status = "PENDING"
        rows.append({"test": key, "status": status, "evidence": evidence, "notes": item.get("notes", "")})
    issues = [r for r in rows if r["status"] != "PASS"]
    authorized = engine.get("authorized_to_use_model", False)
    blender_status = blender.get("status", "FAIL")
    bbox = blender.get("checks", {}).get("bounding_boxes", {})
    bbox_results = {k: bbox.get(k, {}).get("status", "PENDING") for k in ("static_comparison", "dynamic_comparison")}
    proportions = blender.get("checks", {}).get("source_proportions", {}).get("status", "PENDING")
    animation_suite = blender.get("checks", {}).get("animation_suite", {}).get("status", "PENDING")
    accessories = blender.get("checks", {}).get("accessories", {}).get("status", "PENDING")
    joint_deformation = blender.get("checks", {}).get("joint_deformation", {}).get("status", "PENDING")
    mesh_integrity = blender.get("checks", {}).get("mesh_integrity", {}).get("status", "PENDING")
    rig_stretch = blender.get("checks", {}).get("rig_stretch", {}).get("status", "PENDING")
    # Hard rule: no original-mesh limb stretch, missing reference bounds or runtime evidence blocks approval.
    bbox_gates = [bbox_results["static_comparison"]]
    if target == "player_runtime":
        bbox_gates.append(bbox_results["dynamic_comparison"])
    source_fail = target == "player_runtime" and (proportions == "FAIL" or animation_suite == "FAIL" or accessories == "FAIL" or joint_deformation == "FAIL" or mesh_integrity == "FAIL" or rig_stretch == "FAIL")
    source_pending = target == "player_runtime" and (proportions != "PASS" or animation_suite != "PENDING_RUNTIME" or accessories != "PASS_PRELIMINARY" or joint_deformation != "PASS_PRELIMINARY" or mesh_integrity != "PASS_PRELIMINARY" or rig_stretch != "PASS_PRELIMINARY")
    if blender_status == "FAIL" or source_fail or any(r["status"] == "FAIL" for r in rows) or "FAIL" in bbox_gates:
        overall = "FAIL"
    elif not authorized or blender_status != "PASS_PRELIMINARY" or issues or "PENDING" in bbox_gates or source_pending:
        overall = "PENDING_OR_WARN"
    else:
        overall = "PASS_WITH_EVIDENCE"
    result = {
        "schema_version": 1,
        "target": target,
        "overall_status": overall,
        "blender_status": blender_status,
        "authorized_to_use_model": bool(authorized),
        "bbox_gates": bbox_results,
        "source_proportions_gate": proportions,
        "animation_suite_source_status": animation_suite,
        "accessories_source_status": accessories,
        "joint_deformation_source_status": joint_deformation,
        "mesh_integrity_source_status": mesh_integrity,
        "rig_stretch_source_status": rig_stretch,
        "engine_tests": rows,
        "open_items": issues,
        "disclaimer": "PASS_WITH_EVIDENCE 仅依据填写的证据声明；工具无法核实人工输入是否属实。"
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Final gate: {overall} -> {out}")
    if overall != "PASS_WITH_EVIDENCE":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
