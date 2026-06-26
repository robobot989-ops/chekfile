import math
import networkx as nx
from shapely.geometry import LineString, Point
from typing import List, Tuple
from .dxf_loader import Segment, CYAN

SNAP = 0.01


def _snap(p: Tuple[float, float]) -> Tuple[float, float]:
    return (round(p[0] / SNAP) * SNAP, round(p[1] / SNAP) * SNAP)


def _diameter(pts: List[Tuple[float, float]]) -> float:
    if len(pts) < 2:
        return 0
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    max_r = max(math.hypot(p[0] - cx, p[1] - cy) for p in pts)
    return max_r * 2


def _centroid(segments: List) -> Tuple[float, float]:
    pts = []
    for seg in segments:
        pts.extend(list(seg.geom.coords))
    if not pts:
        return (0.0, 0.0)
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return (cx, cy)


def find_missing_bridges(
    segments: List[Segment],
    min_bridge: float = 1.0,
    max_bridge: float = 6.0,
    exclude_colors: List[Tuple[int, int, int]] = None,
    max_hole_diameter: float = 10.0,
) -> List[dict]:
    """Detect contours without proper bridges.

    A bridge is a gap of 1-6mm in a cut contour that keeps the part
    from falling out.  The algorithm:

    1. Build a graph from segment endpoints (connected at shared nodes).
    2. Find connected components.
    3. Any fully closed component (0 dangling ends) that is NOT a small
       hole → error (missing bridge).
    4. Collect ALL dangling ends across ALL remaining components and
       pair them greedily by proximity.  If every paired gap falls
       inside [min_bridge, max_bridge] the contour is OK; otherwise
       the offending pair is reported as an error.
    """
    if exclude_colors is None:
        exclude_colors = [CYAN]

    # --- filter out engraving layers by colour ---
    cut = []
    for seg in segments:
        if seg.color:
            h = seg.color.lstrip("#")
            rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
            if rgb in exclude_colors:
                continue
        cut.append(seg)
    if not cut:
        return []

    # --- build endpoint graph ---
    G = nx.Graph()
    for seg in cut:
        coords = list(seg.geom.coords)
        if len(coords) < 2:
            continue
        start = _snap(coords[0])
        end = _snap(coords[-1])
        if start == end:
            continue  # zero-length edge, skip
        G.add_edge(start, end, segment=seg)

    # --- collect per-component info ---
    component_data = []      # list of dicts
    all_dangling = []        # (node, component_idx)
    next_comp_id = 0

    for comp_nodes in nx.connected_components(G):
        sub = G.subgraph(comp_nodes)

        contour_segs = []
        for _, _, d in sub.edges(data=True):
            s = d.get("segment")
            if s:
                contour_segs.append(s)

        all_pts = []
        for s in contour_segs:
            all_pts.extend(list(s.geom.coords))

        diam = _diameter(all_pts)
        deg1 = [n for n in sub.nodes if sub.degree(n) == 1]
        is_small_hole = diam <= max_hole_diameter

        idx = next_comp_id
        next_comp_id += 1

        component_data.append({
            "idx": idx,
            "contour_segments": contour_segs,
            "diameter": diam,
            "deg1": deg1,
            "is_small_hole": is_small_hole,
            "sub": sub,
        })

        for node in deg1:
            all_dangling.append((node, idx))

    # --- step 1: fully closed components → error (unless small hole) ---
    results = []
    for cd in component_data:
        if len(cd["deg1"]) == 0 and not cd["is_small_hole"]:
            loc = _centroid(cd["contour_segments"])
            results.append({
                "type": "missing_bridge",
                "contour_segments": cd["contour_segments"],
                "location": loc,
                "diameter": round(cd["diameter"], 2),
                "gap": 0.0,
                "nodes": cd["sub"].number_of_nodes(),
                "edges": cd["sub"].number_of_edges(),
                "has_bridge": False,
            })

    # --- no dangling ends → done ---
    if not all_dangling:
        return results

    if len(all_dangling) % 2 != 0:
        # odd number — can't pair; report every component that has ends
        seen = set()
        for node, cid in all_dangling:
            if cid not in seen:
                seen.add(cid)
                cd = component_data[cid]
                loc = _centroid(cd["contour_segments"])
                results.append({
                    "type": "missing_bridge",
                    "contour_segments": cd["contour_segments"],
                    "location": loc,
                    "diameter": round(cd["diameter"], 2),
                    "gap": 0.0,
                    "nodes": cd["sub"].number_of_nodes(),
                    "edges": cd["sub"].number_of_edges(),
                    "has_bridge": False,
                })
        return results

    # --- step 2: greedily pair dangling ends by proximity ---
    remaining = list(all_dangling)  # each entry is ((x,y), comp_idx)
    paired_ok = []  # (ok, location)

    while len(remaining) >= 2:
        best_i = best_j = 0
        best_d = float("inf")
        for i in range(len(remaining)):
            for j in range(i + 1, len(remaining)):
                d = math.hypot(
                    remaining[i][0][0] - remaining[j][0][0],
                    remaining[i][0][1] - remaining[j][0][1],
                )
                if d < best_d:
                    best_d = d
                    best_i, best_j = i, j

        # pop larger index first
        pair = (
            remaining.pop(best_j),
            remaining.pop(best_i),
        )
        mid_x = (pair[0][0][0] + pair[1][0][0]) / 2
        mid_y = (pair[0][0][1] + pair[1][0][1]) / 2
        valid = min_bridge <= best_d <= max_bridge
        paired_ok.append((valid, (mid_x, mid_y), best_d))

    # --- mark errors ---
    for valid, loc, gap in paired_ok:
        if not valid:
            results.append({
                "type": "missing_bridge",
                "contour_segments": [],
                "location": loc,
                "diameter": 0.0,
                "gap": round(gap, 3),
                "nodes": 0,
                "edges": 0,
                "has_bridge": False,
            })

    return results
