import os
import math
from pathlib import Path
from shapely.geometry import LineString, Point, MultiLineString
from .dxf_loader import Segment
from .geometry import run_full_check
from jinja2 import Environment, FileSystemLoader
from datetime import datetime

TEMPLATE_DIR = Path(__file__).parent.parent / "web" / "templates"


def _compute_bounds(segments):
    """Вычисляет bounding box всех сегментов."""
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for s in segments:
        for x, y in s.geom.coords:
            minx = min(minx, x)
            miny = min(miny, y)
            maxx = max(maxx, x)
            maxy = max(maxy, y)

    # Добавляем отступ 5%
    dx = (maxx - minx) or 1
    dy = (maxy - miny) or 1
    margin_x = dx * 0.05
    margin_y = dy * 0.05
    return {
        "minx": minx - margin_x,
        "miny": miny - margin_y,
        "maxx": maxx + margin_x,
        "maxy": maxy + margin_y,
        "width": dx + 2 * margin_x,
        "height": dy + 2 * margin_y,
    }


def _segment_to_svg_path(seg: Segment, bounds: dict, viewbox_size: tuple) -> str:
    """Конвертирует сегмент в SVG path строку."""
    vbw, vbh = viewbox_size
    bw = bounds["width"]
    bh = bounds["height"]
    scale = min(vbw / bw, vbh / bh) * 0.9

    cx = bounds["minx"] + bw / 2
    cy = bounds["miny"] + bh / 2
    ox = vbw / 2 - cx * scale
    oy = vbh / 2 - cy * scale

    def transform(x, y):
        return (x * scale + ox, y * scale + oy)

    parts = []
    coords = list(seg.geom.coords)
    if not coords:
        return ""
    x, y = transform(coords[0][0], coords[0][1])
    parts.append(f"M {x:.2f},{y:.2f}")
    for i in range(1, len(coords)):
        x, y = transform(coords[i][0], coords[i][1])
        parts.append(f"L {x:.2f},{y:.2f}")
    return " ".join(parts)


def _generate_svg_base(segments: list, bounds: dict, viewbox_size=(1000, 1000)):
    """Генерирует базовый SVG с линиями чертежа."""
    svg_parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {viewbox_size[0]} {viewbox_size[1]}" style="background:#1a1a2e;width:100%;height:auto;">']
    svg_parts.append(f'<g id="dxf-lines" stroke="#e0e0e0" stroke-width="1" fill="none">')

    for seg in segments:
        path = _segment_to_svg_path(seg, bounds, viewbox_size)
        if path:
            opacity = 0.7
            svg_parts.append(f'<path d="{path}" opacity="{opacity}" />')

    svg_parts.append("</g>")
    return "\n".join(svg_parts)


def _generate_svg_problems(problems: list, bounds: dict, viewbox_size=(1000, 1000)):
    """Генерирует SVG элементы для подсветки проблемных мест."""
    svg_parts = ['<g id="problems">']

    vbw, vbh = viewbox_size
    bw = bounds["width"]
    bh = bounds["height"]
    scale = min(vbw / bw, vbh / bh) * 0.9
    cx = bounds["minx"] + bw / 2
    cy = bounds["miny"] + bh / 2
    ox = vbw / 2 - cx * scale
    oy = vbh / 2 - cy * scale

    def transform(x, y):
        return (x * scale + ox, y * scale + oy)

    for p in problems:
        loc = p.get("location", (0, 0))
        px, py = loc
        sx, sy = transform(px, py)
        radius = max(6, scale * 0.5)

        # Подсветка проблемных сегментов
        for seg_key in ["segment1", "segment2"]:
            seg = p.get(seg_key)
            if seg:
                path = _segment_to_svg_path(seg, bounds, viewbox_size)
                if path:
                    svg_parts.append(f'<path d="{path}" stroke="#ff3333" stroke-width="3" opacity="0.9" />')

        # Маркер
        svg_parts.append(
            f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="{radius:.1f}" '
            f'stroke="#ff0000" stroke-width="2" fill="rgba(255,0,0,0.25)" '
            f'class="problem-marker" data-problem-id="{p.get("id", 0)}" />'
        )

    svg_parts.append("</g>")
    return "\n".join(svg_parts)


def generate_report(filepath: str, output_dir: str | Path, tolerance: float = 0.1) -> dict:
    """Полный цикл: загрузка DXF → проверка → генерация HTML."""
    from .dxf_loader import load_dxf_segments

    segments, metadata = load_dxf_segments(filepath)
    result = run_full_check(segments, tolerance)
    bounds = _compute_bounds(segments)
    svg_base = _generate_svg_base(segments, bounds)
    svg_problems = _generate_svg_problems(result["problems"], bounds)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("report.html")

    filename = metadata["filename"]
    report_path = Path(output_dir) / f"{Path(filepath).stem}_report.html"

    html = template.render(
        filename=filename,
        filepath=str(filepath),
        total_segments=result["total_segments"],
        total_problems=result["total_problems"],
        has_errors=result["has_errors"],
        svg_base=svg_base,
        svg_problems=svg_problems,
        problems=result["problems"],
        tolerance=tolerance,
        checked_at=datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_path.write_text(html, encoding="utf-8")

    return {
        "report_file": str(report_path),
        "has_errors": result["has_errors"],
        "total_problems": result["total_problems"],
        "filename": filename,
    }
