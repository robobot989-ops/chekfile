import ezdxf
from shapely.geometry import LineString, Point, box
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

# DXF ACI colors to hex
ACI_COLORS = {
    1: "#ff0000", 2: "#ffff00", 3: "#00ff00", 4: "#00ffff", 5: "#0000ff",
    6: "#ff00ff", 7: "#ffffff", 8: "#808080", 9: "#c0c0c0",
    10: "#ff0000", 11: "#ff6666", 12: "#ffa500", 13: "#ffff00",
    14: "#ffff66", 15: "#00ff00", 16: "#66ff66", 17: "#00ffff",
    18: "#66ffff", 19: "#0000ff", 20: "#6666ff", 21: "#ff00ff",
    30: "#ff6666", 31: "#ff9999", 32: "#ffcc99", 33: "#ffff99",
    40: "#ccffcc", 41: "#99ff99", 42: "#66ffcc", 43: "#66ffff",
    50: "#9999ff", 51: "#cc99ff", 52: "#ff99ff", 53: "#ffccff",
    60: "#ffcccc", 61: "#ffcccc", 62: "#ffcccc", 63: "#ccccff",
    70: "#ccffcc", 80: "#ffcc99", 90: "#99ccff", 100: "#cc99ff",
    110: "#ff99cc", 120: "#99ffcc", 130: "#ccff99", 140: "#ffcc66",
    150: "#66ccff", 160: "#cc66ff", 170: "#ff66cc", 180: "#66ffcc",
    190: "#cccc66", 200: "#66cccc", 210: "#cc66cc", 220: "#cccc99",
    230: "#99cccc", 240: "#cc99cc", 250: "#666666", 251: "#555555",
    252: "#444444", 253: "#333333", 254: "#222222", 255: "#111111",
}

CYAN = (0, 255, 255)


@dataclass
class Segment:
    geom: LineString
    layer: str
    handle: str
    entity_type: str
    color: Optional[str] = None
    layer_color: Optional[str] = None


def _get_entity_color(entity, doc) -> Optional[str]:
    """Get entity color, falling back to layer color, then default."""
    try:
        ci = entity.dxf.color
        if ci is not None and ci != 256:
            return ACI_COLORS.get(ci)
    except AttributeError:
        pass
    try:
        layer_name = entity.dxf.layer
        layer = doc.layers.get(layer_name)
        if layer:
            lci = layer.dxf.color
            if lci is not None and lci != 256:
                return ACI_COLORS.get(lci)
    except AttributeError:
        pass
    return None


def load_dxf_segments(filepath: str, max_arc_angle: float = 1.0) -> Tuple[List[Segment], dict]:
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    segments = []
    layer_colors = {}

    for entity in msp:
        dxftype = entity.dxftype()
        handle = entity.dxf.handle
        layer = entity.dxf.layer
        color = _get_entity_color(entity, doc)

        # Track layer colors
        if layer not in layer_colors:
            layer_colors[layer] = color

        pts = None

        if dxftype == "LINE":
            pts = [(entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y)]

        elif dxftype == "LWPOLYLINE":
            raw = list(entity.get_points())
            pts = [(p[0], p[1]) for p in raw]

        elif dxftype == "POLYLINE":
            raw = list(entity.get_points())
            pts = [(p[0], p[1]) for p in raw]

        elif dxftype == "ARC":
            import math as m
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            r = entity.dxf.radius
            sa, ea = entity.dxf.start_angle, entity.dxf.end_angle
            if ea < sa:
                ea += 360
            pts = []
            a = sa
            while a < ea:
                rad = m.radians(a)
                pts.append((cx + r * m.cos(rad), cy + r * m.sin(rad)))
                a += max_arc_angle
            pts.append((cx + r * m.cos(m.radians(ea)), cy + r * m.sin(m.radians(ea))))

        elif dxftype == "CIRCLE":
            import math as m
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            r = entity.dxf.radius
            pts = []
            for a in range(0, 360, int(max_arc_angle)):
                rad = m.radians(a)
                pts.append((cx + r * m.cos(rad), cy + r * m.sin(rad)))

        elif dxftype == "SPLINE":
            try:
                raw = list(entity.render_as_vertices(segments=64))
                pts = [(p[0], p[1]) for p in raw]
            except Exception:
                pass

        elif dxftype == "ELLIPSE":
            try:
                raw = list(entity.render_vertices(64))
                pts = [(p.x, p.y) for p in raw]
            except Exception:
                pass

        if pts and len(pts) >= 2:
            closed = False
            if dxftype in ("LWPOLYLINE", "POLYLINE"):
                try:
                    closed = entity.closed
                except Exception:
                    pass
            elif dxftype == "CIRCLE":
                closed = True
            elif dxftype == "SPLINE":
                try:
                    closed = entity.closed
                except Exception:
                    pass

            for i in range(len(pts) - 1):
                segments.append(Segment(LineString([pts[i], pts[i + 1]]), layer, handle, dxftype, color))

            if closed and len(pts) >= 3:
                segments.append(Segment(LineString([pts[-1], pts[0]]), layer, handle, dxftype, color))

    # Resolve BYLAYER colors (color=256)
    for seg in segments:
        if seg.color is None and seg.layer in layer_colors:
            seg.color = layer_colors[seg.layer]

    metadata = {
        "filepath": str(filepath),
        "filename": str(filepath).split("\\")[-1].split("/")[-1],
        "entity_count": len(segments),
        "layer_colors": layer_colors,
    }
    return segments, metadata

