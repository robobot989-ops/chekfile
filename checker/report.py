from pathlib import Path
from shapely.geometry import LineString
from .geometry import run_full_check
from jinja2 import Environment, FileSystemLoader
from datetime import datetime

TEMPLATE_DIR = Path(__file__).parent.parent / "web" / "templates"


def _compute_bounds(segments):
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for s in segments:
        for x, y in s.geom.coords:
            minx = min(minx, x)
            miny = min(miny, y)
            maxx = max(maxx, x)
            maxy = max(maxy, y)
    dx = (maxx - minx) or 1
    dy = (maxy - miny) or 1
    mx, my = dx * 0.05, dy * 0.05
    return {"minx": minx - mx, "miny": miny - my, "maxx": maxx + mx, "maxy": maxy + my, "width": dx + 2*mx, "height": dy + 2*my}


def _make_transform(bounds, vbw=1000, vbh=1000):
    bw, bh = bounds["width"], bounds["height"]
    scale = min(vbw / bw, vbh / bh) * 0.9
    cx = bounds["minx"] + bw / 2
    cy = bounds["miny"] + bh / 2
    ox = vbw / 2 - cx * scale
    oy = vbh / 2 + cy * scale
    return lambda x, y: (x * scale + ox, -y * scale + oy)


def _seg_path(seg, t):
    coords = list(seg.geom.coords)
    if len(coords) < 2:
        return ""
    x, y = t(*coords[0])
    parts = [f"M {x:.2f},{y:.2f}"]
    for i in range(1, len(coords)):
        x, y = t(*coords[i])
        parts.append(f"L {x:.2f},{y:.2f}")
    return " ".join(parts)


def _generate_svg(segments, problems, bounds, vbw=1000, vbh=1000):
    t = _make_transform(bounds, vbw, vbh)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vbw} {vbh}" style="background:#1a1a2e;width:100%;height:auto;">']

    # Base lines with layer colors
    svg.append('<g id="dxf-lines" fill="none">')
    color_map = {}
    for seg in segments:
        c = seg.color or "#e0e0e0"
        if c not in color_map:
            color_map[c] = []
        path = _seg_path(seg, t)
        if path:
            color_map[c].append(path)
    for c, paths in color_map.items():
        svg.append(f'<g stroke="{c}" stroke-width="1" opacity="0.8">')
        for p in paths:
            svg.append(f'<path d="{p}" />')
        svg.append("</g>")
    svg.append("</g>")

    # Problem highlights
    svg.append('<g id="problems">')
    for p in problems:
        px, py = p.get("location", (0, 0))
        sx, sy = t(px, py)
        radius = max(6, min(vbw, vbh) * 0.006)
        ptype = p.get("problem_type", "double_line")

        if ptype == "missing_bridge":
            color = "#ff8800"
            for seg in p.get("contour_segments", []):
                path = _seg_path(seg, t)
                if path:
                    svg.append(f'<path d="{path}" stroke="{color}" stroke-width="3" stroke-dasharray="6,3" opacity="0.9" />')
            svg.append(f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="{radius*1.5:.1f}" stroke="{color}" stroke-width="2" fill="rgba(255,136,0,0.2)" class="problem-marker" data-problem-id="{p.get("id", 0)}" data-type="bridge" />')
        else:
            color = "#ff3333" if ptype == "double_line" else "#ff66ff"
            for sk in ["segment1", "segment2"]:
                seg = p.get(sk)
                if seg:
                    path = _seg_path(seg, t)
                    if path:
                        svg.append(f'<path d="{path}" stroke="{color}" stroke-width="3" opacity="0.9" />')
            svg.append(f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="{radius:.1f}" stroke="#ff0000" stroke-width="2" fill="rgba(255,0,0,0.25)" class="problem-marker" data-problem-id="{p.get("id", 0)}" />')
    svg.append("</g></svg>")
    return "\n".join(svg)


def generate_report(filepath, output_dir, settings=None, lang="ru"):
    from .dxf_loader import load_dxf_segments
    s = settings or {}

    segments, metadata = load_dxf_segments(filepath)
    result = run_full_check(
        segments,
        tolerance=s.get("checker.tolerance", s.get("tolerance", 0.1)),
        min_distance=s.get("checker.min_problem_distance", s.get("min_problem_distance", 0.001)),
        check_double_lines=s.get("checker.double_line_check", True),
        check_bridges=s.get("checker.bridge_check", True),
        bridge_min=s.get("checker.bridge_min", 1.0),
        bridge_max=s.get("checker.bridge_max", 6.0),
        bridge_max_hole=s.get("checker.bridge_max_hole_diameter", 10.0),
    )

    bounds = _compute_bounds(segments)

    # SVG with colors and problems
    svg = _generate_svg(segments, result["problems"], bounds)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    filename = metadata["filename"]
    report_path = Path(output_dir) / f"{Path(filepath).stem}_report.html"

    html = template = env.get_template("report.html")
    html = template.render(
        filename=filename,
        filepath=str(filepath),
        total_segments=result["total_segments"],
        total_problems=result["total_problems"],
        has_errors=result["has_errors"],
        svg=svg,
        problems=result["problems"],
        double_lines=result.get("double_lines", []),
        overlaps=result.get("overlaps", []),
        bridges=result.get("bridges", []),
        tolerance=s.get("checker.tolerance", s.get("tolerance", 0.1)),
        checked_at=datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        lang=lang,
    )

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    report_path.write_text(html, encoding="utf-8")

    return {
        "report_file": str(report_path),
        "has_errors": result["has_errors"],
        "total_problems": result["total_problems"],
        "filename": filename,
        "problems": result["problems"],
        "total_segments": result["total_segments"],
    }
