from __future__ import annotations

from app.llm.mock import demo_design
from app.models import MachineDesign, Station, Transport
from app.services.layout import DEFAULT_ENVELOPE, compute_layout


def _flow_boxes(layout):
    return sorted((b for b in layout.boxes if b.sequence is not None), key=lambda b: b.sequence)


def test_inline_layout_places_stations_in_order_without_overlap() -> None:
    layout = compute_layout(demo_design("blister"))
    flow = _flow_boxes(layout)
    assert len(flow) == 5  # 4 process stations + outfeed
    for a, b in zip(flow, flow[1:]):
        assert a.x + a.length / 2 <= b.x - b.length / 2  # left to right, no overlap
        assert a.y == b.y == 0
    assert flow[0].length == 1800  # envelope from the design

    guard = next(b for b in layout.boxes if b.kind == "guard")
    for box in flow:
        assert guard.x - guard.length / 2 < box.x - box.length / 2
        assert guard.x + guard.length / 2 > box.x + box.length / 2
    cabinet = next(b for b in layout.boxes if b.station_id == "st-control")
    assert cabinet.y < guard.y - guard.width / 2  # behind the guarded line
    assert layout.footprint_length_mm > sum(b.length for b in flow)
    assert len(layout.flow) == len(flow) + 2


def test_u_shape_uses_two_rows_and_returns() -> None:
    design = demo_design("blister")
    inline = compute_layout(design)
    design.layout_style = "u_shape"
    layout = compute_layout(design)
    flow = _flow_boxes(layout)
    row_a, row_b = flow[:3], flow[3:]
    assert {b.y for b in row_a} == {row_a[0].y} and row_a[0].y > 0
    assert {b.y for b in row_b} == {row_b[0].y} and row_b[0].y < 0
    assert row_b[0].x > row_b[-1].x  # second row runs back
    assert layout.footprint_length_mm < inline.footprint_length_mm


def test_defaults_and_clamping_for_missing_or_absurd_envelopes() -> None:
    design = MachineDesign(name="t", machine_type="t", summary="t", stations=[
        Station(id="a", name="A", function="f"),
        Station(id="b", name="B", function="f", length_mm=1e9, width_mm=-5, height_mm=None),
    ], transports=[Transport(id="ab", from_station="a", to_station="b")])
    a, b = _flow_boxes(compute_layout(design))
    assert (a.length, a.width, a.height) == DEFAULT_ENVELOPE["process"]
    assert b.length == 20000 and b.width == DEFAULT_ENVELOPE["process"][1]


def test_empty_design_has_empty_layout() -> None:
    layout = compute_layout(MachineDesign(name="t", machine_type="t", summary="t"))
    assert layout.boxes == [] and layout.flow == [] and layout.footprint_length_mm == 0
