"""Concept 3D layout computed from the design.

The AI only proposes station envelopes (length/width/height) and a layout style; positions are
computed here, because language models are unreliable with coordinates. Coordinates are in mm:
x along the product flow, y across it (+y = operator side), z up from the floor. Boxes are given
by their center and size.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.models import MachineDesign, Station

# Default envelopes (length along flow, width, height) when the design gives none.
DEFAULT_ENVELOPE: dict[str, tuple[float, float, float]] = {
    "process": (1000, 900, 1800),
    "transport": (1200, 400, 1000),
    "inspection": (600, 800, 1800),
    "control": (1200, 600, 2000),
    "utility": (800, 400, 1200),
}
STATION_GAP = 100       # between flow stations
ROW_GAP = 400           # between the two rows of a U-shape
AISLE = 1000            # between the line and the cabinets behind it
GUARD_MARGIN = 150
BASE_PLATE_HEIGHT = 80
MIN_SIZE, MAX_SIZE = 100.0, 20000.0
FLOW_KINDS = {"process", "transport", "inspection"}


class LayoutBox(BaseModel):
    id: str
    station_id: str | None
    label: str
    kind: str = ""  # station kind, or "guard" / "base"
    sequence: int | None = None
    x: float
    y: float
    z: float
    length: float
    width: float
    height: float


class Layout(BaseModel):
    style: str
    boxes: list[LayoutBox]
    flow: list[tuple[float, float, float]]
    footprint_length_mm: float
    footprint_width_mm: float


def _clamp(value: float | None, default: float) -> float:
    if value is None or value <= 0:
        return default
    return min(max(float(value), MIN_SIZE), MAX_SIZE)


def _envelope(station: Station) -> tuple[float, float, float]:
    dl, dw, dh = DEFAULT_ENVELOPE.get(station.kind, DEFAULT_ENVELOPE["process"])
    return _clamp(station.length_mm, dl), _clamp(station.width_mm, dw), _clamp(station.height_mm, dh)


def _box(station: Station, x: float, y: float, size: tuple[float, float, float], kind: str | None = None) -> LayoutBox:
    length, width, height = size
    return LayoutBox(
        id=station.id,
        station_id=station.id,
        label=station.name,
        kind=kind or station.kind,
        sequence=station.sequence if station.sequence > 0 else None,
        x=round(x, 1),
        y=round(y, 1),
        z=round(height / 2, 1),
        length=length,
        width=width,
        height=height,
    )


def _row(stations: list[Station], start_x: float, y: float, direction: int) -> tuple[list[LayoutBox], float]:
    """Place stations side by side along x. Returns the boxes and the x where the row ends."""
    boxes: list[LayoutBox] = []
    cursor = start_x
    for i, station in enumerate(stations):
        size = _envelope(station)
        if i:
            cursor += direction * STATION_GAP
        center = cursor + direction * size[0] / 2
        boxes.append(_box(station, center, y, size))
        cursor += direction * size[0]
    return boxes, cursor


def compute_layout(design: MachineDesign) -> Layout:
    flow_stations = sorted(
        (s for s in design.stations if s.sequence > 0 or s.kind in FLOW_KINDS),
        key=lambda s: (s.sequence <= 0, s.sequence),
    )
    others = [s for s in design.stations if s not in flow_stations]
    boxes: list[LayoutBox] = []

    # Process line.
    if design.layout_style == "u_shape" and len(flow_stations) >= 2:
        split = (len(flow_stations) + 1) // 2
        row_a, row_b = flow_stations[:split], flow_stations[split:]
        width_a = max(_envelope(s)[1] for s in row_a)
        width_b = max(_envelope(s)[1] for s in row_b)
        y_a = width_a / 2 + ROW_GAP / 2
        y_b = -(width_b / 2 + ROW_GAP / 2)
        boxes_a, end_x = _row(row_a, 0.0, y_a, +1)
        boxes_b, _ = _row(row_b, end_x, y_b, -1)
        flow_boxes = boxes_a + boxes_b
    else:
        flow_boxes, _ = _row(flow_stations, 0.0, 0.0, +1)
    boxes.extend(flow_boxes)

    if flow_boxes:
        min_x = min(b.x - b.length / 2 for b in flow_boxes)
        max_x = max(b.x + b.length / 2 for b in flow_boxes)
        min_y = min(b.y - b.width / 2 for b in flow_boxes)
        max_y = max(b.y + b.width / 2 for b in flow_boxes)
        max_h = max(b.height for b in flow_boxes)
    else:
        min_x = max_x = min_y = max_y = 0.0
        max_h = 1800.0

    # Base frame plate under the line and guarding around it.
    frames = [s for s in others if s.kind == "frame"]
    if frames and flow_boxes:
        boxes.append(LayoutBox(
            id="base", station_id=frames[0].id, label=frames[0].name, kind="base",
            x=(min_x + max_x) / 2, y=(min_y + max_y) / 2, z=BASE_PLATE_HEIGHT / 2,
            length=max_x - min_x + 2 * GUARD_MARGIN, width=max_y - min_y + 2 * GUARD_MARGIN,
            height=BASE_PLATE_HEIGHT,
        ))
    guards = [s for s in others if s.kind == "safety"]
    if guards and flow_boxes:
        height = max_h + 200
        boxes.append(LayoutBox(
            id="guard", station_id=guards[0].id, label=guards[0].name, kind="guard",
            x=(min_x + max_x) / 2, y=(min_y + max_y) / 2, z=height / 2,
            length=max_x - min_x + 2 * GUARD_MARGIN, width=max_y - min_y + 2 * GUARD_MARGIN, height=height,
        ))

    # Cabinets and utility panels in a row behind the line.
    cursor = min_x
    back_y = min_y - GUARD_MARGIN - AISLE
    for station in [s for s in others if s.kind not in ("frame", "safety")]:
        size = _envelope(station)
        boxes.append(_box(station, cursor + size[0] / 2, back_y - size[1] / 2, size))
        cursor += size[0] + 300

    # Product flow polyline at working height through the flow stations.
    working_height = 1000.0
    flow: list[tuple[float, float, float]] = []
    if flow_boxes:
        first, last = flow_boxes[0], flow_boxes[-1]
        # The line always starts towards -x; a U-shape's return row runs back towards -x too.
        flow.append((first.x - (first.length / 2 + 300), first.y, working_height))
        flow.extend((b.x, b.y, working_height) for b in flow_boxes)
        exit_dir = -1 if design.layout_style == "u_shape" and len(flow_boxes) >= 2 else 1
        flow.append((last.x + exit_dir * (last.length / 2 + 300), last.y, working_height))

    xs = [b.x - b.length / 2 for b in boxes] + [b.x + b.length / 2 for b in boxes]
    ys = [b.y - b.width / 2 for b in boxes] + [b.y + b.width / 2 for b in boxes]
    return Layout(
        style=design.layout_style,
        boxes=boxes,
        flow=[(round(x, 1), round(y, 1), z) for x, y, z in flow],
        footprint_length_mm=round(max(xs) - min(xs), 0) if xs else 0.0,
        footprint_width_mm=round(max(ys) - min(ys), 0) if ys else 0.0,
    )
