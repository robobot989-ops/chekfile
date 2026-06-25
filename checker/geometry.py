import math
from shapely import STRtree
from shapely.geometry import LineString, Point
from typing import List, Tuple, Set
from .dxf_loader import Segment
from itertools import combinations
import math

def find_double_lines(segments: List[Segment], tolerance: float = 0.1) -> List[dict]:
    """Находит пары сегментов, расстояние между которыми меньше tolerance.

    Использует пространственный индекс (R-tree) для эффективности O(n log n).
    Возвращает список проблем: {segment1, segment2, distance, location}.
    """
    if len(segments) < 2:
        return []

    geoms = [s.geom for s in segments]
    tree = STRtree(geoms)

    problems = []
    seen_pairs: Set[Tuple[int, int]] = set()

    for i, seg in enumerate(segments):
        envelope = seg.geom.buffer(tolerance)
        candidates_indices = tree.query(envelope, predicate="intersects")

        for j in candidates_indices:
            if j == i:
                continue

            if isinstance(j, (int,)):
                j_idx = j
            else:
                j_idx = j

            # Пропускаем сегменты из одного и того же примитива
            if seg.handle == segments[j_idx].handle:
                continue

            pair_key = (min(i, j_idx), max(i, j_idx))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            dist = seg.geom.distance(segments[j_idx].geom)

            if dist < tolerance and dist > 1e-10:
                loc = _find_problem_location(seg.geom, segments[j_idx].geom)
                problems.append({
                    "i": i,
                    "j": j_idx,
                    "segment1": seg,
                    "segment2": segments[j_idx],
                    "distance": round(dist, 4),
                    "location": loc,
                })

    problems.sort(key=lambda p: p["distance"])
    return problems


def _find_problem_location(s1: LineString, s2: LineString) -> Tuple[float, float]:
    """Находит точку, где расстояние между двумя сегментами минимально."""
    dist = s1.distance(s2)
    if dist < 1e-10:
        inter = s1.intersection(s2)
        if inter.is_empty:
            return (0.0, 0.0)
        if inter.geom_type == "Point":
            return (inter.x, inter.y)
        return (inter.centroid.x, inter.centroid.y)

    from shapely.ops import nearest_points
    pt1, pt2 = nearest_points(s1, s2)
    return (pt1.x, pt1.y)


def find_overlapping_segments(segments: List[Segment], tolerance: float = 0.1) -> List[dict]:
    """Находит сегменты, которые почти полностью перекрывают друг друга."""
    problems = []
    geoms = [s.geom for s in segments]
    tree = STRtree(geoms)
    seen_pairs: Set[Tuple[int, int]] = set()

    for i, seg in enumerate(segments):
        envelope = seg.geom.buffer(tolerance)
        candidates_indices = tree.query(envelope, predicate="intersects")

        for j in candidates_indices:
            if j == i:
                continue
            j_idx = j if isinstance(j, (int,)) else j

            if seg.handle == segments[j_idx].handle:
                continue

            pair_key = (min(i, j_idx), max(i, j_idx))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            overlap = seg.geom.intersection(segments[j_idx].geom)
            if not overlap.is_empty:
                overlap_len = overlap.length
                len1 = seg.geom.length
                len2 = segments[j_idx].geom.length
                min_len = min(len1, len2)
                if min_len > 0 and overlap_len / min_len > 0.5:
                    loc = (overlap.centroid.x, overlap.centroid.y) if not overlap.is_empty else (0, 0)
                    problems.append({
                        "i": i,
                        "j": j_idx,
                        "segment1": seg,
                        "segment2": segments[j_idx],
                        "distance": 0.0,
                        "overlap_ratio": round(overlap_len / min_len, 3),
                        "location": loc,
                    })

    return problems


def _cluster_problems(problems: List[dict], cluster_tolerance: float = 20.0) -> List[dict]:
    """Группирует проблемы, находящиеся рядом, в одну (через связные компоненты)."""
    if not problems:
        return []

    n = len(problems)
    adj = [[] for _ in range(n)]

    for i in range(n):
        ix, iy = problems[i]["location"]
        for j in range(i + 1, n):
            jx, jy = problems[j]["location"]
            if math.hypot(ix - jx, iy - jy) < cluster_tolerance:
                adj[i].append(j)
                adj[j].append(i)

    visited = [False] * n
    clustered = []

    for i in range(n):
        if visited[i]:
            continue

        stack = [i]
        visited[i] = True
        cluster = []

        while stack:
            v = stack.pop()
            cluster.append(problems[v])
            for u in adj[v]:
                if not visited[u]:
                    visited[u] = True
                    stack.append(u)

        rep = min(cluster, key=lambda x: x["distance"])
        rep["cluster_size"] = len(cluster)
        rep["id"] = len(clustered) + 1
        clustered.append(rep)

    return clustered


def run_full_check(segments: List[Segment], tolerance: float = 0.1) -> dict:
    """Запускает полную проверку: двойные линии + перекрытия."""
    double_lines = find_double_lines(segments, tolerance)
    overlaps = find_overlapping_segments(segments, tolerance)

    # Объединяем, исключая дубликаты
    seen_keys = set()
    all_problems = []
    for p in double_lines + overlaps:
        key = (p["i"], p["j"])
        if key not in seen_keys:
            seen_keys.add(key)
            all_problems.append(p)

    # Кластеризация — группируем близкие проблемы (для дуг и кривых)
    clustered = _cluster_problems(all_problems, cluster_tolerance=max(tolerance * 200, 20.0))

    return {
        "problems": clustered,
        "total_segments": len(segments),
        "total_problems": len(clustered),
        "has_errors": len(clustered) > 0,
    }
