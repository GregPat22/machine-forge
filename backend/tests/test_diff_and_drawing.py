from __future__ import annotations

import io

import ezdxf

from app.llm.mock import _initial_design
from app.services.diff import diff_designs
from app.services.drawing import to_dxf, to_svg
from app.services.layout import compute_layout
from tests.conftest import BLISTER_PROBLEM


def test_diff_reports_added_removed_and_modified() -> None:
    before = _initial_design(BLISTER_PROBLEM)
    after = before.model_copy(deep=True)
    after.layout_style = "u_shape"
    after.open_questions.append("Which film width?")
    forming = next(s for s in after.stations if s.id == "st-forming")
    forming.steps[0].duration_s = 1.0  # its derived cycle_time_s goes from 1.2 to 1.0
    cylinder = next(c for c in forming.components if c.id == "forming-cyl")
    cylinder.quantity = 2
    cylinder.specs[0].value = "100 mm"
    feeding = next(s for s in after.stations if s.id == "st-feeding")
    moved = next(c for c in feeding.components if c.id == "feeder-check")
    feeding.components.remove(moved)
    forming.components.append(moved)
    after.stations = [s for s in after.stations if s.id != "st-cutting"]

    d = diff_designs(before, after, 1, 2)
    assert [(f.field, f.before, f.after) for f in d.machine] == [("layout_style", "inline", "u_shape")]
    assert d.lists[0].field == "open_questions" and d.lists[0].added == ["Which film width?"]
    assert {(s.station_id, s.change) for s in d.stations} == {("st-forming", "modified"), ("st-cutting", "removed")}
    changes = {c.component_id: c for c in d.components}
    assert {f.field for f in changes["forming-cyl"].fields} == {"quantity", "specs"}
    assert [f.field for f in changes["feeder-check"].fields] == ["station"]
    assert changes["punch-tool"].change == "removed"
    assert d.counts["stations_removed"] == 1 and d.counts["components_removed"] == 2


def test_diff_of_identical_designs_is_empty() -> None:
    design = _initial_design(BLISTER_PROBLEM)
    d = diff_designs(design, design.model_copy(deep=True), 1, 1)
    assert not (d.machine or d.lists or d.stations or d.components)


def test_svg_top_view() -> None:
    design = _initial_design(BLISTER_PROBLEM)
    svg = to_svg(compute_layout(design), design, 3)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "1. Film unwind and forming" in svg and "revision 3" in svg and " mm</text>" in svg


def test_dxf_opens_in_ezdxf_with_layers_and_entities() -> None:
    design = _initial_design(BLISTER_PROBLEM)
    layout = compute_layout(design)
    doc = ezdxf.read(io.StringIO(to_dxf(layout, design, 1)))
    assert doc.dxfversion == "AC1009"
    assert {"MF_STATIONS", "MF_GUARD", "MF_FLOW"} <= {layer.dxf.name for layer in doc.layers}
    msp = doc.modelspace()
    lines = msp.query("LINE")
    assert len(lines) >= 4 * len(layout.boxes)
    texts = [t.dxf.text for t in msp.query("TEXT")]
    assert "1. Film unwind and forming" in texts
    # Operator side (+y in the layout) is drawn below the line axis (negative DXF y).
    guard = next(b for b in layout.boxes if b.kind == "guard")
    ys = [ln.dxf.start.y for ln in lines if ln.dxf.layer == "MF_GUARD"]
    assert min(ys) == -(guard.y + guard.width / 2)
