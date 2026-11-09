"""Pure-Python deterministic mesh-region deformation metrics.

Compares IDENTICAL vertex-index topology in a bind/rest mesh and a posed mesh.
It is a geometric warning system, not a self-intersection, soft-body or visual QA solver.
"""
from __future__ import annotations
import math


def dist(a, b):
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def area(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    x = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    return 0.5 * math.sqrt(sum(z*z for z in x))


def compare_region(rest, posed, edges, triangles, *, max_edge_change=0.40,
                   max_area_change=0.65, minimum_length=1e-7, minimum_area=1e-11,
                   sample_limit=15):
    if len(rest) != len(posed):
        return {"status":"PENDING_TOPOLOGY_CHANGED", "rest_vertices":len(rest),"posed_vertices":len(posed)}
    if not 0 < max_edge_change < 1 or not 0 < max_area_change < 1:
        raise ValueError("Thresholds must lie in (0,1)")
    hits, worst_edge, worst_area = [], 0.0, 0.0
    edge_total = 0
    for i,j in edges:
        before = dist(rest[i], rest[j])
        if before < minimum_length:
            continue
        now = dist(posed[i], posed[j])
        # symmetric normalized distortion: 2.0x stretch and 0.5x compression both = 1
        ratio = now / before
        deviation = abs(math.log(max(ratio, 1e-12)))
        worst_edge = max(worst_edge, deviation)
        edge_total += 1
        if ratio > 1 + max_edge_change or ratio < 1 - max_edge_change:
            hits.append({"type":"edge", "vertices":[i,j],"ratio":round(ratio,5)})
    face_total = 0
    for i,j,k in triangles:
        before = area(rest[i],rest[j],rest[k])
        if before < minimum_area:
            continue
        now = area(posed[i],posed[j],posed[k])
        ratio = now / before
        worst_area = max(worst_area, abs(math.log(max(ratio, 1e-12))))
        face_total += 1
        if ratio > 1 + max_area_change or ratio < 1 - max_area_change:
            hits.append({"type":"triangle", "vertices":[i,j,k], "ratio":round(ratio,5)})
    return {"status": "FAIL" if hits else ("PASS_PRELIMINARY" if edge_total or face_total else "PENDING_EMPTY_REGION"),
            "edges_evaluated":edge_total, "triangles_evaluated":face_total,
            "violations":len(hits), "samples":hits[:sample_limit],
            "max_abs_log_edge_ratio":round(worst_edge,6),
            "max_abs_log_area_ratio":round(worst_area,6)}
