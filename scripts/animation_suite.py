"""Evaluate animation inventory separately from runtime animation/ragdoll evidence."""
from __future__ import annotations

ALLOWED_MODES = {"action_optional", "action_required", "runtime_only"}
ALLOWED_KINDS = {"animation", "transition", "physics", "external_event"}


def audit_suite(suite, available_actions, sampled_actions):
    if not isinstance(suite, dict) or not isinstance(suite.get("tracks"), dict):
        raise ValueError("animation suite must contain tracks")
    result = {"tracks": {}, "errors": [], "pending": [], "status": "PENDING"}
    for track, states in suite["tracks"].items():
        if track not in {"worldmodel", "viewmodel"} or not isinstance(states, list):
            raise ValueError("tracks must be worldmodel/viewmodel arrays")
        rows = []
        identifiers = set()
        for state in states:
            state_id = state.get("id")
            mode = state.get("mode", "action_optional")
            kind = state.get("kind", "animation")
            action = state.get("source_action", "")
            if not isinstance(state_id, str) or not state_id or state_id in identifiers or mode not in ALLOWED_MODES or kind not in ALLOWED_KINDS:
                raise ValueError("invalid/duplicate animation state id, mode or kind")
            identifiers.add(state_id)
            if mode == "runtime_only":
                status = "PENDING_RUNTIME"
            elif not action:
                status = "FAIL_REQUIRED_ACTION_UNSPECIFIED" if mode == "action_required" else "PENDING_RUNTIME"
            elif action not in available_actions:
                status = "FAIL_ACTION_MISSING" if mode == "action_required" else "PENDING_RUNTIME"
            elif track == "worldmodel" and action not in sampled_actions:
                status = "PENDING_UNSAMPLED_ACTION"
            else:
                status = "SOURCE_ACTION_PRESENT_RUNTIME_PENDING"
            row = {"id": state_id, "kind": kind, "mode": mode, "source_action": action,
                   "status": status, "runtime_required": bool(state.get("runtime_required", True))}
            rows.append(row)
            if status.startswith("FAIL"):
                result["errors"].append({"track": track, **row})
            if status.startswith("PENDING"):
                result["pending"].append({"track": track, **row})
        result["tracks"][track] = rows
    result["status"] = "FAIL" if result["errors"] else "PENDING_RUNTIME"
    result["note"] = "A source Action does not prove AG2 plays it. Death may use runtime ragdoll rather than a named death Action."
    return result
