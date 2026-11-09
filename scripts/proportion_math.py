"""Pure math for *source-character-relative* limb proportions.

Only a single global scale is allowed; never compare lengths to an arbitrary
CS2 agent template. Torso anchor pairs determine global scale independently of
arms and legs so scaling ALL limbs together cannot evade this check.
"""
from __future__ import annotations

import math
import statistics


def evaluate_proportions(reference: dict, measured: dict, *, tolerance=0.03, min_anchors=1):
    if not 0 < tolerance <= 0.15:
        raise ValueError("tolerance must be in (0, 0.15]")
    source = reference.get("segments", {})
    target = measured.get("segments", {})
    anchors = reference.get("anchor_ids", [])
    if not source or not target or not anchors:
        return {"status": "PENDING", "reason": "missing source geometry / target geometry / calibrated torso anchors"}
    ratios = []
    for item_id in anchors:
        a, b = source.get(item_id), target.get(item_id)
        if a is not None and b is not None and a > 1e-8 and b > 1e-8:
            ratios.append(b / a)
    if len(ratios) < min_anchors:
        return {"status": "PENDING", "reason": "not enough valid original torso anchors", "available_anchors": len(ratios)}
    uniform_scale = statistics.median(ratios)
    missing = sorted(set(source) - set(target))
    rows = []
    for item_id, original in source.items():
        actual = target.get(item_id)
        if actual is None or not math.isfinite(actual) or actual <= 0 or original <= 0:
            continue
        expected = original * uniform_scale
        delta = abs(actual / expected - 1)
        rows.append({"segment": item_id, "original_length": original, "current_length": actual,
                     "expected_at_global_scale": expected, "relative_deviation": delta,
                     "status": "FAIL" if delta > tolerance else "PASS"})
    bad = [r for r in rows if r["status"] == "FAIL"]
    return {"status": "FAIL" if bad else ("PENDING" if missing else "PASS"),
            "uniform_scale_from_torso": uniform_scale, "tolerance": tolerance,
            "violations": bad, "missing_segments": missing, "segments": rows,
            "interpretation": "Scale is derived ONLY from original torso anchors; CS2 agent bone lengths are not a target."}


def pose_length_deviation(rest_length: float, posed_length: float):
    if not (math.isfinite(rest_length) and math.isfinite(posed_length)) or rest_length <= 1e-8:
        return None
    return abs(posed_length / rest_length - 1)


def anisotropy(scale):
    magnitudes = [abs(float(v)) for v in scale]
    if not magnitudes or min(magnitudes) < 1e-8:
        return float("inf")
    return max(magnitudes) / min(magnitudes) - 1
