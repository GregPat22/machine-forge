"""Distinct validated components must remain distinct in ST and PLCopen output."""
import re
import xml.etree.ElementTree as ET

from hypothesis import given, settings, strategies as st

from app.models import Component, MachineDesign, Signals, Station
from app.services.io_points import io_points
from app.services.patch import PatchOp, apply_patches, empty_design
from app.services.plc import generate, to_plcopen_xml


def _design(base="motor", units=2, reverse=False):
    components = [Component(id=base, name="Motor group", category="motor", quantity=units, signals=Signals(do=2, di=1)),
                  Component(id=f"{base}-1", name="Other motor", category="motor", quantity=1, signals=Signals(do=2, di=1))]
    if reverse:
        components.reverse()
    result = apply_patches(empty_design(), [PatchOp(op="add_station", station=Station(
        id="st-test", name="Test", function="Test", components=components))])
    assert result.ok
    return result.design


def _names(design):
    return {(p.component.id, p.unit, p.kind, p.description): p.variable for p in io_points(design)}


def test_colliding_io_names_are_unique_in_st_and_xml():
    design = _design()
    names = list(_names(design).values())
    assert len({n.casefold() for n in names}) == len(names)
    st_file = next(f.content for f in generate(design, 1).files if f.name == "GVL_IO.st")
    declarations = re.findall(r"^\s+(\w+) : (?:BOOL|INT);", st_file, re.M)
    assert set(declarations) == set(names) and len(declarations) == len(names)
    root = ET.fromstring(to_plcopen_xml(design, "Synthetic review"))
    xml_names = [v.attrib["name"] for v in root.findall(".//{*}globalVars/{*}variable")]
    assert set(xml_names) == set(names) and len(xml_names) == len(names)
    assert all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in names)


def test_name_disambiguation_is_stable_when_components_are_reordered():
    assert _names(_design()) == _names(_design(reverse=True))


@settings(max_examples=75, derandomize=True, deadline=None)
@given(base=st.from_regex(r"[a-z]{1,8}(-[a-z]{1,8})?", fullmatch=True), units=st.integers(2, 6))
def test_generated_io_names_are_unique_for_valid_slugs(base, units):
    names = list(_names(_design(base, units)).values())
    assert len({n.casefold() for n in names}) == len(names)
