"""Pure Python AABB operations. Coordinates must be in the SAME space and units."""
import math


def _vec3(data, name):
    if not isinstance(data, (list, tuple)) or len(data) != 3:
        raise ValueError(f"{name} must be a list of 3 finite numbers")
    result = [float(v) for v in data]
    if not all(math.isfinite(v) for v in result):
        raise ValueError(f"{name} must contain finite numbers")
    return result


def make_box(low, high):
    low = _vec3(low, "min")
    high = _vec3(high, "max")
    if any(a > b for a, b in zip(low, high)):
        raise ValueError("min cannot exceed max")
    return {
        "min": low,
        "max": high,
        "size": [b - a for a, b in zip(low, high)],
        "center": [(a + b) / 2 for a, b in zip(low, high)],
    }


def union_boxes(boxes):
    boxes = list(boxes)
    if not boxes:
        return None
    return make_box(
        [min(box["min"][i] for box in boxes) for i in range(3)],
        [max(box["max"][i] for box in boxes) for i in range(3)],
    )


def compare_box(box, reference, margins):
    """Compare box against reference in the same coordinate space.

    Returns PENDING when no reference; otherwise PASS/FAIL with per-axis overflow.
    """
    if reference is None:
        return {"status": "PENDING", "reason": "未提供校准过的参考包围盒"}
    ref = make_box(reference["min"], reference["max"])
    margins = _vec3(margins, "axis_absolute_margin")
    if any(v < 0 for v in margins):
        raise ValueError("margins must be nonnegative")
    lo_over = [max(0.0, ref["min"][i] - margins[i] - box["min"][i]) for i in range(3)]
    hi_over = [max(0.0, box["max"][i] - ref["max"][i] - margins[i]) for i in range(3)]
    return {
        "status": "FAIL" if any(lo_over + hi_over) else "PASS",
        "overflow_below": lo_over,
        "overflow_above": hi_over,
        "reference": ref,
    }
