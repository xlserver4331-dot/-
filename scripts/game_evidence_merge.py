"""Transfer local game QA evidence to engine checklist, NEVER assert a runtime PASS."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def merge(game_report: dict, template: dict):
    if template.get("target") != "player_runtime":
        raise ValueError("游戏自动检查的证据只能回填 player_runtime 验收清单")
    result = json.loads(json.dumps(template))
    shots = {s.get("id"): s.get("screenshot") for s in game_report.get("test_results", []) if s.get("screenshot")}
    world = [s for s in game_report.get("test_results", []) if s.get("view", "thirdperson") == "thirdperson"]
    first = [s for s in game_report.get("test_results", []) if s.get("view") == "firstperson"]
    death = [s for s in game_report.get("test_results", []) if s.get("action") == "death"]
    def all_paths(rows):
        paths=[]
        for step in rows:
            for path in step.get("sequence_screenshots", [step.get("screenshot")]):
                if path and path not in paths:paths.append(path)
        return paths
    world_images = all_paths(world)
    first_images = all_paths(first)
    death_images = [s["screenshot"] for s in death if s.get("screenshot")]
    hints = {
        "mesh_materials_visible": ["idle"],
        "ag2_binding_live": ["idle", "walk", "run"],
        "weapon_alignment_live": ["aim", "fire", "reload", "swap"],
        "movement_animation_live": list(shots),
    }
    for key, actions in hints.items():
        selected = [shots[action] for action in actions if action in shots]
        item = result.setdefault("tests", {}).setdefault(key, {})
        if selected:
            item["evidence"] = "; ".join(selected)
        item["status"] = "PENDING"
        item["notes"] = (item.get("notes", "") + " | 自动键鼠截图只证明采集到画面，不能证明模型/动作正确；必须人工或引擎校验。").strip()
    for key, paths in {
        "viewmodel_arms_live": first_images,
        "viewmodel_animation_live": first_images,
        "original_limb_proportions_live": world_images,
        "death_transition_live": death_images,
        "ragdoll_physics_live": death_images,
        "animation_suite_live": world_images + first_images,
        "accessory_motion_live": world_images,
        "joint_deformation_live": world_images + first_images,
        "mesh_cracks_live": world_images + first_images,
        "rig_stretch_live": world_images + first_images,
    }.items():
        item = result["tests"].setdefault(key, {})
        item["status"] = "PENDING"
        if paths:
            item["evidence"] = "; ".join(paths)
        item["notes"] = (item.get("notes", "") + " | 仅为截图/触发记录，不证明动画、手模或布娃娃通过。需额外观察者/引擎证据。").strip()
    for key in ("hit_reaction_live", "respawn_live"):
        result["tests"].setdefault(key, {})["status"] = "PENDING"
    item = result["tests"].setdefault("local_server_mounted", {})
    item["status"] = "PENDING"
    item["evidence"] = game_report.get("readiness", {}).get("evidence", "")
    item["notes"] = "客户端就绪标记不是模型资源挂载证明。需核对服务端/客户端的资源加载日志。"
    for key in ("hitboxes_reviewed", "physics_collision_reviewed"):
        result["tests"].setdefault(key, {})["status"] = "PENDING"
    result["model_id"] = game_report.get("model_name", result.get("model_id", ""))
    result["automatic_game_qa"] = {"status": game_report.get("status"),
                                    "evidence_paths": all_paths(game_report.get("test_results", [])),
                                    "visual_report": game_report.get("visual_audit", {}).get("status", "PENDING"),
                                    "log_report": game_report.get("log_audit", {}).get("status", "PENDING")}
    return result


def main():
    ap = argparse.ArgumentParser(description="安全回填自动游戏截图证据；所有运行时检查保持 PENDING")
    ap.add_argument("--game-report", required=True)
    ap.add_argument("--template", default=str(ROOT / "templates/engine_validation.template.json"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    report = json.loads(Path(args.game_report).read_text(encoding="utf-8"))
    template = json.loads(Path(args.template).read_text(encoding="utf-8"))
    result = merge(report, template)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("证据回填（非 PASS） ->", path)


if __name__ == "__main__":
    main()
