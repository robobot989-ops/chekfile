import ezdxf
from shapely.geometry import LineString, Point, box
from typing import List, Tuple
from dataclasses import dataclass

@dataclass
class Segment:
    geom: LineString
    layer: str
    handle: str
    entity_type: str

def load_dxf_segments(filepath: str, max_arc_angle: float = 1.0) -> Tuple[List[Segment], dict]:
    """Загружает DXF и возвращает список сегментов + метаданные.

    Все кривые (ARC, CIRCLE, SPLINE, ELLIPSE, POLYLINE) аппроксимируются
    отрезками с шагом max_arc_angle градусов.
    """
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    segments = []

    for entity in msp:
        dxftype = entity.dxftype()
        handle = entity.dxf.handle
        layer = entity.dxf.layer

        if dxftype == "LINE":
            start = (entity.dxf.start.x, entity.dxf.start.y)
            end = (entity.dxf.end.x, entity.dxf.end.y)
            segments.append(Segment(LineString([start, end]), layer, handle, dxftype))

        elif dxftype == "LWPOLYLINE":
            points = list(entity.get_points())
            if len(points) >= 2:
                for i in range(len(points) - 1):
                    p1 = (points[i][0], points[i][1])
                    p2 = (points[i + 1][0], points[i + 1][1])
                    segments.append(Segment(LineString([p1, p2]), layer, handle, dxftype))
                if entity.closed:
                    p1 = (points[-1][0], points[-1][1])
                    p2 = (points[0][0], points[0][1])
                    segments.append(Segment(LineString([p1, p2]), layer, handle, dxftype))

        elif dxftype == "POLYLINE":
            points = list(entity.get_points())
            if len(points) >= 2:
                for i in range(len(points) - 1):
                    p1 = (points[i][0], points[i][1])
                    p2 = (points[i + 1][0], points[i + 1][1])
                    segments.append(Segment(LineString([p1, p2]), layer, handle, dxftype))
                if entity.closed:
                    p1 = (points[-1][0], points[-1][1])
                    p2 = (points[0][0], points[0][1])
                    segments.append(Segment(LineString([p1, p2]), layer, handle, dxftype))

        elif dxftype == "ARC":
            arc = entity
            cx, cy = arc.dxf.center.x, arc.dxf.center.y
            r = arc.dxf.radius
            start_angle = arc.dxf.start_angle
            end_angle = arc.dxf.end_angle
            if end_angle < start_angle:
                end_angle += 360
            import math
            angle = start_angle
            pts = []
            while angle < end_angle:
                rad = math.radians(angle)
                pts.append((cx + r * math.cos(rad), cy + r * math.sin(rad)))
                angle += max_arc_angle
            rad = math.radians(end_angle)
            pts.append((cx + r * math.cos(rad), cy + r * math.sin(rad)))
            if len(pts) >= 2:
                for i in range(len(pts) - 1):
                    segments.append(Segment(LineString([pts[i], pts[i + 1]]), layer, handle, dxftype))

        elif dxftype == "CIRCLE":
            circle = entity
            cx, cy = circle.dxf.center.x, circle.dxf.center.y
            r = circle.dxf.radius
            import math
            pts = []
            for angle in range(0, 360, int(max_arc_angle)):
                rad = math.radians(angle)
                pts.append((cx + r * math.cos(rad), cy + r * math.sin(rad)))
            if len(pts) >= 2:
                for i in range(len(pts)):
                    j = (i + 1) % len(pts)
                    segments.append(Segment(LineString([pts[i], pts[j]]), layer, handle, dxftype))

        elif dxftype == "SPLINE":
            try:
                pts = list(entity.render_as_vertices(segments=64))
                if len(pts) >= 2:
                    for i in range(len(pts) - 1):
                        p1 = (pts[i][0], pts[i][1])
                        p2 = (pts[i + 1][0], pts[i + 1][1])
                        segments.append(Segment(LineString([p1, p2]), layer, handle, dxftype))
            except Exception:
                pass

        elif dxftype == "ELLIPSE":
            try:
                ellipse = entity
                from ezdxf.math import param_to_angle
                pts = list(ellipse.render_vertices(64))
                if len(pts) >= 2:
                    for i in range(len(pts) - 1):
                        p1 = (pts[i].x, pts[i].y)
                        p2 = (pts[i + 1].x, pts[i + 1].y)
                        segments.append(Segment(LineString([p1, p2]), layer, handle, dxftype))
            except Exception:
                pass

    metadata = {
        "filepath": filepath,
        "filename": str(filepath).split("\\")[-1].split("/")[-1],
        "entity_count": len(segments),
    }
    return segments, metadata
