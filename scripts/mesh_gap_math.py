"""Pure functions for crack / seam diagnostics; no bpy needed.

A seam pair must come from an explicit, user-reviewed anchor. Normal open
boundaries may be intentional and are not automatically treated as defects.
"""
from __future__ import annotations
import math


def distance(a, b):
    return math.sqrt(sum((float(x)-float(y))**2 for x,y in zip(a,b)))


def seam_drift(rest_a, rest_b, pose_a, pose_b, *, max_gap, max_increase):
    """Observe *absolute* seam gap AND growth from the rest state.

    Works on vertices transformed into the SAME reference frame.
    """
    if max_gap <= 0 or max_increase < 0:
        raise ValueError('max_gap > 0 and max_increase >= 0 are required')
    rest = distance(rest_a,rest_b)
    now = distance(pose_a,pose_b)
    growth = now-rest
    return {'rest_gap':rest, 'pose_gap':now,'gap_increase':growth,
            'failed':bool(now > max_gap and growth > max_increase)}


def scale_spread(values):
    """Anisotropy measure independent of a uniform model scale."""
    scales=[abs(float(v)) for v in values]
    if len(scales)!=3 or min(scales)<=1e-8:
        return float('inf')
    return max(scales)/min(scales)-1.0


def relative_length(rest, posed):
    if rest<=1e-9:
        return float('inf')
    return abs(posed/rest-1.0)


def stable_pair(a,b):
    return tuple(sorted((str(a),str(b))))
