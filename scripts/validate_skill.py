"""Offline package structural validation; standard library only."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "SKILL.md", "README.md", "config/ag2_profile.example.json",
    "config/height_profile.humanoid.example.json", "config/height_profile.nonhumanoid.example.json",
    "config/height_profile.mixed_mesh.example.json", "config/height_reference_agent.example.json",
    "scripts/height_policy_core.py", "scripts/height_choice.py", "scripts/blender_body_height_audit.py",
    "references/v8-height-and-complete-workflow.md", "tests/test_v8_height.py", "tests/test_v8_height_choice.py",
    "config/viewmodel_extraction.example.json", "config/dual_viewmodel.example.json", "config/firstperson_bone_map.example.json", "config/workflow.player_dual.example.json",
    "scripts/viewmodel_core.py", "scripts/blender_extract_firstperson.py", "scripts/blender_viewmodel_final_audit.py",
    "scripts/dual_viewmodel_gate.py", "scripts/pin_viewmodel_export.py", "references/v7-dual-viewmodel-extraction.md", "tests/test_v7_firstperson.py",
    "config/mesh_integrity.example.json", "config/rig_stretch.example.json", "config/seam_repair.example.json",
    "scripts/mesh_gap_math.py", "scripts/blender_mesh_gap_audit.py", "scripts/blender_rig_stretch_audit.py", "scripts/blender_seam_repair.py",
    "references/v6-stretch-crack-recovery.md", "tests/test_v6_stretch_crack.py",
    "config/accessories.example.json", "config/joint_deformation.example.json",
    "scripts/accessory_core.py", "scripts/deformation_metrics.py", "scripts/blender_accessory_setup.py",
    "scripts/blender_accessory_audit.py", "scripts/blender_joint_deformation.py", "scripts/issue_triage.py",
    "references/v5-accessories-joint-deformation.md", "tests/test_v5_accessory_joint.py",
    "config/proportions.example.json", "config/animation_suite.example.json",
    "scripts/proportion_math.py", "scripts/blender_proportion_audit.py", "scripts/animation_suite.py",
    "references/v4-proportions-animation-death.md", "tests/test_v4_animation_proportions.py",
    "config/bbox_rules.example.json", "config/retarget_map.example.json",
    "scripts/blender_audit.py", "scripts/blender_retarget_setup.py", "scripts/bbox_math.py",
    "scripts/modeldoc_reference_audit.py", "scripts/finalize_report.py",
    "scripts/blender_auto_fix.py", "scripts/auto_workflow.py", "scripts/auto_workflow_core.py",
    "config/auto_workflow.example.json", "references/automation-and-launch.md", "run_skill.ps1",
    "scripts/game_qa.py", "scripts/game_qa_core.py", "scripts/game_evidence_audit.py",
    "scripts/game_evidence_merge.py", "config/game_test.example.json",
    "config/visual_baseline.example.json", "references/game-self-test.md", "requirements-game.txt",
    "templates/engine_validation.template.json",
    "references/rigging-and-driving.md", "references/bounding-boxes.md",
    "references/modeldoc-deployment.md", "references/sources.md",
]


def main():
    for item in REQUIRED:
        if not (ROOT / item).is_file():
            raise RuntimeError(f"缺少必需文件: {item}")
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if not (skill.startswith("---\n") and "name: cs2-model-rigging-deployment" in skill.split("---", 2)[1]):
        raise RuntimeError("SKILL.md YAML frontmatter 名称不匹配")
    for path in (ROOT / "config").glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    json.loads((ROOT / "templates/engine_validation.template.json").read_text(encoding="utf-8"))
    print("PASS: 目录结构、Skill frontmatter、全部 JSON 配置文件")


if __name__ == "__main__":
    main()
