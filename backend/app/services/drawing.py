"""2D top view of the concept layout: SVG for viewing, DXF (R12, mm) for CAD.

Drawing coordinates: x along the flow, y across. The operator side (+y in the layout) is drawn at
the bottom, as in a front-facing plan view.
"""

from __future__ import annotations

from datetime import date
from xml.sax.saxutils import escape

from app.models import MachineDesign
from app.services.layout import Layout, LayoutBox

MARGIN = 800.0  # mm around the machine, room for dimensions and the title block

FILL = {
    "process": "#fde68a", "transport": "#e2e8f0", "inspection": "#bae6fd",
    "control": "#cbd5e1", "utility": "#99f6e4", "base": "none", "guard": "none",
}
DXF_LAYERS = {  # name: AutoCAD color index
    "MF_STATIONS": 2, "MF_CABINETS": 8, "MF_GUARD": 5, "MF_FRAME": 9, "MF_FLOW": 1, "MF_TEXT": 7, "MF_DIMS": 3,
}


def _layer(box: LayoutBox) -> str:
    return {"guard": "MF_GUARD", "base": "MF_FRAME", "control": "MF_CABINETS", "utility": "MF_CABINETS"}.get(
        box.kind, "MF_STATIONS")


def _bounds(layout: Layout, sign: float) -> tuple[float, float, float, float]:
    """Extents in drawing coordinates, where drawing y = sign * layout y."""
    if not layout.boxes:
        return 0.0, 0.0, 1000.0, 1000.0
    xs = [b.x - b.length / 2 for b in layout.boxes] + [b.x + b.length / 2 for b in layout.boxes]
    ys = [sign * (b.y + b.width / 2) for b in layout.boxes] + [sign * (b.y - b.width / 2) for b in layout.boxes]
    return min(xs), min(ys), max(xs), max(ys)


# --- SVG -------------------------------------------------------------------------------------------


def to_svg(layout: Layout, design: MachineDesign, revision: int) -> str:
    # SVG y points down, so drawing y = +layout y puts the operator side at the bottom.
    x0, y0, x1, y1 = _bounds(layout, +1)
    left, top = x0 - MARGIN, y0 - MARGIN
    width, height = (x1 - x0) + 2 * MARGIN, (y1 - y0) + 2 * MARGIN + 600  # + title block
    font = max(width, height) / 90

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{left:.0f} {top:.0f} {width:.0f} {height:.0f}" '
        f'font-family="Helvetica, Arial, sans-serif">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#ea580c"/></marker></defs>',
        f'<rect x="{left:.0f}" y="{top:.0f}" width="{width:.0f}" height="{height:.0f}" fill="#ffffff"/>',
    ]
    order = {"base": 0, "guard": 3}
    for box in sorted(layout.boxes, key=lambda b: order.get(b.kind, 1)):
        x, y = box.x - box.length / 2, box.y - box.width / 2
        style = {
            "guard": 'fill="none" stroke="#2563eb" stroke-width="12" stroke-dasharray="80 40"',
            "base": 'fill="#f1f5f9" stroke="#94a3b8" stroke-width="6"',
        }.get(box.kind, f'fill="{FILL.get(box.kind, "#e5e7eb")}" stroke="#0f172a" stroke-width="10"')
        parts.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{box.length:.0f}" height="{box.width:.0f}" {style}/>')
        if box.kind not in ("guard", "base"):
            label = f"{box.sequence}. {box.label}" if box.sequence else box.label
            parts.append(
                f'<text x="{box.x:.0f}" y="{box.y:.0f}" font-size="{font:.0f}" text-anchor="middle" '
                f'dominant-baseline="middle" fill="#0f172a">{escape(label)}</text>'
            )
    if len(layout.flow) >= 2:
        points = " ".join(f"{x:.0f},{y:.0f}" for x, y, _z in layout.flow)
        parts.append(f'<polyline points="{points}" fill="none" stroke="#ea580c" stroke-width="14" '
                     f'marker-end="url(#arrow)"/>')

    # Overall dimensions.
    dim_y = y1 + MARGIN * 0.45
    dim_x = x0 - MARGIN * 0.45
    parts += [
        f'<line x1="{x0:.0f}" y1="{dim_y:.0f}" x2="{x1:.0f}" y2="{dim_y:.0f}" stroke="#15803d" stroke-width="8" '
        f'marker-start="url(#arrow)" marker-end="url(#arrow)"/>',
        f'<text x="{(x0 + x1) / 2:.0f}" y="{dim_y - font * 0.6:.0f}" font-size="{font:.0f}" text-anchor="middle" '
        f'fill="#15803d">{x1 - x0:.0f} mm</text>',
        f'<line x1="{dim_x:.0f}" y1="{y0:.0f}" x2="{dim_x:.0f}" y2="{y1:.0f}" stroke="#15803d" stroke-width="8" '
        f'marker-start="url(#arrow)" marker-end="url(#arrow)"/>',
        f'<text x="{dim_x - font * 0.6:.0f}" y="{(y0 + y1) / 2:.0f}" font-size="{font:.0f}" text-anchor="middle" '
        f'fill="#15803d" transform="rotate(-90 {dim_x - font * 0.6:.0f} {(y0 + y1) / 2:.0f})">{y1 - y0:.0f} mm</text>',
    ]

    # Title block.
    tb_y = y1 + MARGIN
    parts += [
        f'<line x1="{left:.0f}" y1="{tb_y:.0f}" x2="{left + width:.0f}" y2="{tb_y:.0f}" stroke="#0f172a" stroke-width="6"/>',
        f'<text x="{x0:.0f}" y="{tb_y + font * 1.8:.0f}" font-size="{font * 1.3:.0f}" font-weight="bold" '
        f'fill="#0f172a">{escape(design.name)}</text>',
        f'<text x="{x0:.0f}" y="{tb_y + font * 3.4:.0f}" font-size="{font * 0.9:.0f}" fill="#475569">'
        f'Top view · concept layout, not to scale for manufacturing · revision {revision} · {date.today():%Y-%m-%d} · '
        f'operator side at the bottom · dimensions in mm</text>',
        "</svg>",
    ]
    return "\n".join(parts)


# --- DXF (R12, ASCII) -----------------------------------------------------------------------------


def _dxf_pairs(*pairs: tuple[int, object]) -> list[str]:
    out = []
    for code, value in pairs:
        out += [str(code), f"{value:.3f}" if isinstance(value, float) else str(value)]
    return out


def _line(layer: str, x1: float, y1: float, x2: float, y2: float) -> list[str]:
    return _dxf_pairs((0, "LINE"), (8, layer), (10, x1), (20, y1), (30, 0.0), (11, x2), (21, y2), (31, 0.0))


def _text(layer: str, x: float, y: float, height: float, text: str, centered: bool = False) -> list[str]:
    clean = text.replace("\n", " ").encode("ascii", "replace").decode("ascii")
    pairs: list[tuple[int, object]] = [(0, "TEXT"), (8, layer), (10, x), (20, y), (30, 0.0), (40, height), (1, clean)]
    if centered:
        pairs += [(72, 1), (11, x), (21, y), (31, 0.0)]
    return _dxf_pairs(*pairs)


def _rect(layer: str, box: LayoutBox) -> list[str]:
    xa, xb = box.x - box.length / 2, box.x + box.length / 2
    ya, yb = -(box.y + box.width / 2), -(box.y - box.width / 2)
    return (_line(layer, xa, ya, xb, ya) + _line(layer, xb, ya, xb, yb)
            + _line(layer, xb, yb, xa, yb) + _line(layer, xa, yb, xa, ya))


def to_dxf(layout: Layout, design: MachineDesign, revision: int) -> str:
    # DXF y points up, so drawing y = -layout y puts the operator side at the bottom.
    x0, y0, x1, y1 = _bounds(layout, -1)
    text_h = max(x1 - x0, y1 - y0) / 80 or 50.0
    lines = ["0", "SECTION", "2", "HEADER"]
    lines += _dxf_pairs((9, "$ACADVER"), (1, "AC1009"), (9, "$EXTMIN"), (10, x0), (20, y0),
                        (9, "$EXTMAX"), (10, x1), (20, y1))
    lines += ["0", "ENDSEC", "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER", "70", str(len(DXF_LAYERS))]
    for name, color in DXF_LAYERS.items():
        lines += _dxf_pairs((0, "LAYER"), (2, name), (70, 0), (62, color), (6, "CONTINUOUS"))
    lines += ["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]

    for box in layout.boxes:
        lines += _rect(_layer(box), box)
        if box.kind not in ("guard", "base"):
            label = f"{box.sequence}. {box.label}" if box.sequence else box.label
            lines += _text("MF_TEXT", box.x, -box.y, text_h, label, centered=True)
    for (xa, ya, _), (xb, yb, _) in zip(layout.flow, layout.flow[1:]):
        lines += _line("MF_FLOW", xa, -ya, xb, -yb)

    dim_y = y0 - MARGIN * 0.45  # in DXF, +y is up: dimensions below the drawing
    lines += _line("MF_DIMS", x0, dim_y, x1, dim_y)
    lines += _text("MF_DIMS", (x0 + x1) / 2, dim_y - text_h * 1.5, text_h, f"{x1 - x0:.0f} mm", centered=True)
    lines += _text("MF_TEXT", x0, dim_y - text_h * 5, text_h * 1.2,
                   f"{design.name} - concept top view - revision {revision} - units mm")
    lines += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(lines) + "\n"
