"""Patch operations and their validator (Phase 1 step 2, `app/services/patch.py`)."""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.models import (
    Component, MachineDesign, Mechanism, Parameter, Placement, Product, Signals, Station, Step, Transport,
)
from app.services.patch import ERROR_CODES, PatchOp, apply_patches, empty_design


def _base() -> MachineDesign:
    """Two connected process stations and a frame. st-a has a lift with a motion step and a cylinder."""
    return MachineDesign(
        name="Test machine", machine_type="test", summary="for tests",
        stations=[
            Station(id="st-a", name="A", function="forms", mechanisms=[Mechanism(id="m-lift", kind="linear", stroke=50)],
                    steps=[Step(id="s-lift", order=1, kind="motion", mechanism_id="m-lift")],
                    components=[Component(id="a-cyl", name="Cylinder", category="pneumatic_actuator", quantity=1,
                                          role="actuator", motion="m-lift")]),
            Station(id="st-b", name="B", function="seals",
                    steps=[Step(id="s-seal", order=1, kind="fixed_duration", duration_s=1.0)]),
            Station(id="st-frame", name="Frame", kind="frame", function="carries"),
        ],
        transports=[Transport(id="tr-a-b", from_station="st-a", to_station="st-b")],
    )


def _op(op: str, **kw: Any) -> PatchOp:
    return PatchOp(op=op, **kw)  # type: ignore[arg-type]


def _station(sid: str, **kw: Any) -> Station:
    return Station(id=sid, name=sid.upper(), function="does something", **kw)


def _component(cid: str, **kw: Any) -> Component:
    return Component(**{"id": cid, "name": cid, "category": "sensor", "quantity": 1, **kw})


def _rejected(design: MachineDesign, *ops: PatchOp) -> list[tuple[int | None, str, str]]:
    before = design.model_dump()
    result = apply_patches(design, list(ops))
    assert not result.ok and result.design is None
    assert design.model_dump() == before  # the input is never touched
    return [(e.index, e.code, e.message) for e in result.errors]


def _applied(design: MachineDesign, *ops: PatchOp) -> MachineDesign:
    result = apply_patches(design, list(ops))
    assert result.ok, result.errors
    assert result.design is not None
    return result.design


# --- One test per error code, with the exact message ---------------------------------------


def test_error_codes_are_the_documented_set() -> None:
    assert set(ERROR_CODES) == {
        "unknown_station", "unknown_component", "unknown_mechanism", "unknown_step", "unknown_transport",
        "duplicate_id", "missing_operand", "invalid_value", "computed_field", "graph_cycle",
        "orphan_transport", "unknown_op",
    }


def test_unknown_station() -> None:
    assert _rejected(_base(), _op("add_component", station_id="st-x", component=_component("c1"))) == [
        (0, "unknown_station", "station 'st-x' does not exist"),
    ]
    assert _rejected(_base(), _op("connect", transport=Transport(id="tr-b-x", from_station="st-b", to_station="st-x"))) == [
        (0, "unknown_station", "transport 'tr-b-x': station 'st-x' does not exist"),
    ]


def test_unknown_component() -> None:
    assert _rejected(_base(), _op("remove_component", component_id="c-x")) == [
        (0, "unknown_component", "component 'c-x' does not exist"),
    ]


def test_unknown_mechanism() -> None:
    step = Step(id="s-push", order=2, kind="motion", mechanism_id="m-push")
    assert _rejected(_base(), _op("add_step", station_id="st-a", step=step)) == [
        (0, "unknown_mechanism", "step 's-push': station 'st-a' has no mechanism 'm-push'"),
    ]
    assert _rejected(_base(), _op("set_mechanism", station_id="st-b", mechanism=Mechanism(id="m-lift", kind="linear"))) == [
        (0, "unknown_mechanism", "station 'st-b' has no mechanism 'm-lift'"),
    ]


def test_unknown_step() -> None:
    assert _rejected(_base(), _op("remove_step", station_id="st-a", step_id="s-x")) == [
        (0, "unknown_step", "station 'st-a' has no step 's-x'"),
    ]


def test_unknown_transport() -> None:
    assert _rejected(_base(), _op("disconnect", transport_id="tr-x")) == [
        (0, "unknown_transport", "transport 'tr-x' does not exist"),
    ]


def test_duplicate_id() -> None:
    assert _rejected(_base(), _op("add_station", station=_station("st-b"))) == [
        (0, "duplicate_id", "station id 'st-b' is already used"),
    ]
    assert _rejected(_base(), _op("add_component", station_id="st-b", component=_component("a-cyl"))) == [
        (0, "duplicate_id", "component id 'a-cyl' is already used"),
    ]
    assert _rejected(_base(), _op("add_mechanism", station_id="st-a", mechanism=Mechanism(id="m-lift", kind="rotary"))) == [
        (0, "duplicate_id", "mechanism id 'm-lift' is already used in station 'st-a'"),
    ]


def test_missing_operand() -> None:
    assert _rejected(_base(), _op("add_station")) == [(0, "missing_operand", "add_station needs 'station'")]
    assert _rejected(_base(), _op("add_step", step=Step(id="s1", order=1, kind="fixed_duration"))) == [
        (0, "missing_operand", "add_step needs 'station_id'"),
    ]


def test_invalid_value_names_the_value_and_the_limit() -> None:
    assert _rejected(_base(), _op("set_product", product=Product(lanes=0, mass_g=-5))) == [
        (0, "invalid_value", "product mass_g is -5.0; it must be greater than 0"),
        (0, "invalid_value", "product lanes is 0; it must be at least 1"),
    ]
    reject = Transport(id="tr-b-frame", from_station="st-b", to_station="st-frame", reject_to="st-a", reject_rate=1.5)
    assert _rejected(_base(), _op("connect", transport=reject)) == [
        (0, "invalid_value", "transport 'tr-b-frame' reject_rate is 1.5; it must be between 0 and 1"),
    ]
    assert _rejected(_base(), _op("add_station", station=_station("St Feeding"))) == [
        (0, "invalid_value", "station id 'St Feeding' must be a lowercase slug (letters, digits and single hyphens, e.g. 'st-feeding')"),
    ]
    assert _rejected(_base(), _op("remove_station", station_id="st-frame", text="why")) == [
        (0, "invalid_value", "remove_station does not use 'text'; leave it null"),
    ]


def test_computed_fields_cannot_be_set_by_patch() -> None:
    """Rule 3: derived values, coordinates, bookkeeping and motion durations are written by code."""
    for name in ("sequence", "cycle_time_s", "placement", "schema_version", "footprint"):
        for station_id in (None, "st-a"):
            assert _rejected(_base(), _op("set_param", station_id=station_id, name=name, value=1.0)) == [
                (0, "computed_field", f"{name} is computed by the software and cannot be set"),
            ]
    placed = _station("st-c", placement=Placement(x_mm=0, y_mm=0, rotation_deg=0))
    assert _rejected(_base(), _op("add_station", station=placed)) == [
        (0, "computed_field", "station 'st-c' placement comes from the layout and cannot be set"),
    ]
    timed = Step(id="s-down", order=2, kind="motion", mechanism_id="m-lift", duration_s=0.3)
    assert _rejected(_base(), _op("add_step", station_id="st-a", step=timed)) == [
        (0, "computed_field", "step 's-down' is a motion step: its duration is computed, leave duration_s null"),
    ]


def test_graph_cycle() -> None:
    back = Transport(id="tr-b-a", from_station="st-b", to_station="st-a")
    assert _rejected(_base(), _op("connect", transport=back)) == [
        (0, "graph_cycle", "transport 'tr-b-a' would close a loop: the process graph has a cycle through st-a, st-b"),
    ]


def test_orphan_transport() -> None:
    assert _rejected(_base(), _op("remove_station", station_id="st-b")) == [
        (0, "orphan_transport", "station 'st-b' is still connected by transport tr-a-b; disconnect it first"),
    ]


def test_unknown_op() -> None:
    assert _rejected(_base(), PatchOp.model_construct(op="explode")) == [(0, "unknown_op", "unknown operation 'explode'")]


# --- Semantics ------------------------------------------------------------------------------


def test_apply_is_all_or_nothing() -> None:
    design = _base()
    errors = _rejected(
        design,
        _op("add_assumption", text="valid on its own"),
        _op("disconnect", transport_id="tr-x"),
        _op("add_open_question", text="also valid"),
        _op("set_product", product=Product(lanes=0)),
    )
    # Every failing op is reported, with its index; the valid ones are not applied either.
    assert [(i, code) for i, code, _ in errors] == [(1, "unknown_transport"), (3, "invalid_value")]
    assert design.assumptions == [] and design.open_questions == []


def test_every_operation_applies() -> None:
    design = _applied(
        empty_design(),
        _op("set_param", name="name", text="Blister line"),
        _op("set_param", name="machine_type", text="Thermoforming blister machine"),
        _op("set_param", name="summary", text="Forms, fills and seals blisters"),
        _op("set_param", name="layout_style", text="u_shape"),
        _op("set_product", product=Product(name="blister", mass_g=12.5, lanes=2)),
        _op("add_station", station=_station("st-a")),
        _op("add_station", station=_station("st-b")),
        _op("add_station", station=_station("st-c")),
        _op("connect", transport=Transport(id="tr-a-b", from_station="st-a", to_station="st-b", speed_mm_s=200)),
        _op("connect", transport=Transport(id="tr-b-c", from_station="st-b", to_station="st-c")),
        _op("disconnect", transport_id="tr-b-c"),
        _op("remove_station", station_id="st-c"),
        _op("set_param", station_id="st-a", name="length_mm", value=1200),
        _op("set_param", station_id="st-a", name="kind", text="inspection"),
        _op("set_param", station_id="st-a", name="forming_depth", value=12, unit="mm"),
        _op("set_param", station_id="st-a", name="forming_depth", value=14, unit="mm"),
        _op("add_mechanism", station_id="st-a", mechanism=Mechanism(id="m-lift", kind="linear", stroke=40)),
        _op("set_mechanism", station_id="st-a", mechanism=Mechanism(id="m-lift", kind="linear", stroke=60, max_speed=500)),
        _op("add_step", station_id="st-a", step=Step(id="s-lift", order=1, kind="motion", mechanism_id="m-lift")),
        _op("add_step", station_id="st-b", step=Step(id="s-seal", order=1, kind="fixed_duration", duration_s=0.8)),
        _op("add_step", station_id="st-b", step=Step(id="s-cool", order=2, kind="fixed_duration", duration_s=0.4)),
        _op("remove_step", station_id="st-b", step_id="s-cool"),
        _op("add_component", station_id="st-a", component=_component("a-cyl", category="pneumatic_actuator",
                                                                      role="actuator", motion="m-lift")),
        _op("add_component", station_id="st-b", component=_component("b-tc", signals=Signals(ai=1))),
        _op("replace_component", component_id="b-tc", component=_component("b-tc", quantity=2)),
        _op("add_component", station_id="st-b", component=_component("b-spare")),
        _op("remove_component", component_id="b-spare"),
        _op("set_utility", items=["400 V 3~ 50 Hz", "6 bar dry air"]),
        _op("add_assumption", text="Two lanes"),
        _op("add_open_question", text="Film width?"),
    )
    assert (design.name, design.machine_type, design.layout_style) == ("Blister line", "Thermoforming blister machine", "u_shape")
    assert design.product.lanes == 2
    assert [s.id for s in design.stations] == ["st-a", "st-b"]
    a, b = design.stations
    assert (a.length_mm, a.kind) == (1200, "inspection")
    assert [(p.name, p.value, p.unit) for p in a.parameters] == [("forming_depth", 14, "mm")]
    assert a.mechanisms[0].stroke == 60 and a.components[0].motion == "m-lift"
    assert [s.id for s in b.steps] == ["s-seal"] and b.cycle_time_s == 0.8
    assert [(c.id, c.quantity) for c in b.components] == [("b-tc", 2)]
    assert [t.id for t in design.transports] == ["tr-a-b"] and (a.sequence, b.sequence) == (1, 2)
    assert design.utilities == ["400 V 3~ 50 Hz", "6 bar dry air"]
    assert (design.assumptions, design.open_questions) == (["Two lanes"], ["Film width?"])
    assert MachineDesign.model_validate(design.model_dump()) == design


def test_replace_component_keeps_the_component_id() -> None:
    """Ids are kept across revisions (model docstring): a new id is a remove plus an add."""
    assert _rejected(_base(), _op("replace_component", component_id="a-cyl", component=_component("a-cyl-2"))) == [
        (0, "invalid_value", "replace_component keeps the id 'a-cyl'; to use a new id, remove the component and add a new one"),
    ]


def test_parameter_names_have_no_surrounding_spaces() -> None:
    """' stroke ' and 'stroke' would otherwise be two different parameters."""
    assert _rejected(_base(), _op("set_param", station_id="st-a", name=" stroke ", value=40)) == [
        (0, "invalid_value", "station 'st-a' parameter name ' stroke ' has leading or trailing spaces"),
    ]
    spaced = _station("st-c", parameters=[Parameter(name="stroke ", value=40)])
    assert _rejected(_base(), _op("add_station", station=spaced)) == [
        (0, "invalid_value", "station 'st-c' parameter name 'stroke ' has leading or trailing spaces"),
    ]


def test_an_empty_patch_list_returns_an_equal_copy() -> None:
    design = _base()
    result = apply_patches(design, [])
    assert result.ok and result.design == design and result.design is not design


def test_patches_do_not_share_objects_with_the_result() -> None:
    station = _station("st-c")
    design = _applied(_base(), _op("add_station", station=station))
    station.name = "changed after the patch"
    assert design.stations[-1].name == "ST-C"

    # Later ops edit the design, never the answer's own objects (the answer is sent back on repair).
    add = _op("add_station", station=_station("st-d"))
    _rejected(_base(), add, _op("set_param", station_id="st-d", name="name", text="Renamed"),
              _op("disconnect", transport_id="tr-x"))
    assert add.station is not None and add.station.name == "ST-D"


# --- Property tests --------------------------------------------------------------------------

POSITIVE = st.floats(min_value=0.001, max_value=1e6, allow_nan=False, allow_infinity=False)
OPTIONAL_POSITIVE = st.none() | POSITIVE
TEXT = st.text(alphabet=st.characters(categories=("L", "N", "Zs")), min_size=1, max_size=20).filter(str.strip)
CATEGORIES = ["sensor", "servo_motor", "pneumatic_actuator", "custom_part", "plc"]
ROLES = [None, "actuator", "sensor", "drive", "controller", "tooling", "structure", "consumable"]


def _fresh(prefix: str, used: set[str]) -> str:
    n = 1
    while f"{prefix}-{n}" in used:
        n += 1
    return f"{prefix}-{n}"


def _component_ids(design: MachineDesign) -> set[str]:
    return {c.id for s in design.stations for c in s.components}


def _draw_component(data: st.DataObject, design: MachineDesign, station: Station) -> Component:
    mechanisms = [m.id for m in station.mechanisms]
    return Component(
        id=_fresh("c", _component_ids(design)), name=data.draw(TEXT), category=data.draw(st.sampled_from(CATEGORIES)),
        quantity=data.draw(st.integers(1, 20)), recommended_spares=data.draw(st.integers(0, 5)),
        role=data.draw(st.sampled_from(ROLES)),
        signals=data.draw(st.none() | st.builds(Signals, di=st.integers(0, 8), do=st.integers(0, 8))),
        motion=data.draw(st.sampled_from([None, *mechanisms])),
    )


def _draw_valid_op(data: st.DataObject, design: MachineDesign, removals: bool = True) -> PatchOp:
    stations = design.stations
    station_ids = {s.id for s in stations}
    kinds = ["add_station", "set_product", "set_utility", "add_assumption", "add_open_question", "set_param_machine"]
    if stations:
        kinds += ["add_component", "add_mechanism", "add_step", "set_param_station"]
        if any(s.mechanisms for s in stations):
            kinds.append("set_mechanism")
    if len(stations) >= 2:
        kinds.append("connect")
    if removals:
        if any(s.components for s in stations):
            kinds += ["remove_component", "replace_component"]
        if any(s.steps for s in stations):
            kinds.append("remove_step")
        if design.transports:
            kinds.append("disconnect")
        connected = {n for t in design.transports for n in (t.from_station, t.to_station, t.reject_to)}
        if any(s.id not in connected for s in stations):
            kinds.append("remove_station")
    kind = data.draw(st.sampled_from(kinds))

    if kind == "add_station":
        return _op(kind, station=Station(
            id=_fresh("st", station_ids), name=data.draw(TEXT), function=data.draw(TEXT),
            kind=data.draw(st.sampled_from(["process", "transport", "inspection", "frame", "control"])),
            length_mm=data.draw(OPTIONAL_POSITIVE), target_cycle_time_s=data.draw(OPTIONAL_POSITIVE)))
    if kind == "set_product":
        return _op(kind, product=Product(name=data.draw(st.none() | TEXT), mass_g=data.draw(OPTIONAL_POSITIVE),
                                         lanes=data.draw(st.none() | st.integers(1, 12)),
                                         pitch_mm=data.draw(OPTIONAL_POSITIVE)))
    if kind == "set_utility":
        return _op(kind, items=data.draw(st.lists(TEXT, max_size=4)))
    if kind in ("add_assumption", "add_open_question"):
        return _op(kind, text=data.draw(TEXT))
    if kind == "set_param_machine":
        name, text = data.draw(st.sampled_from([("name", TEXT), ("summary", TEXT),
                                                ("layout_style", st.sampled_from(["inline", "u_shape"]))]))
        return _op("set_param", name=name, text=data.draw(text))

    station = data.draw(st.sampled_from(stations))
    if kind == "add_component":
        return _op(kind, station_id=station.id, component=_draw_component(data, design, station))
    if kind == "add_mechanism":
        return _op(kind, station_id=station.id, mechanism=Mechanism(
            id=_fresh("m", {m.id for m in station.mechanisms}), kind=data.draw(st.sampled_from(["linear", "rotary"])),
            stroke=data.draw(OPTIONAL_POSITIVE), max_speed=data.draw(OPTIONAL_POSITIVE)))
    if kind == "set_mechanism":
        station = data.draw(st.sampled_from([s for s in stations if s.mechanisms]))
        old = data.draw(st.sampled_from(station.mechanisms))
        return _op(kind, station_id=station.id, mechanism=Mechanism(
            id=old.id, kind=old.kind, stroke=data.draw(OPTIONAL_POSITIVE), acceleration=data.draw(OPTIONAL_POSITIVE)))
    if kind == "add_step":
        step_id = _fresh("s", {s.id for s in station.steps})
        order = data.draw(st.integers(1, 10))
        if station.mechanisms and data.draw(st.booleans()):
            step = Step(id=step_id, order=order, kind="motion",
                        mechanism_id=data.draw(st.sampled_from([m.id for m in station.mechanisms])))
        else:
            step = Step(id=step_id, order=order, kind="fixed_duration", duration_s=data.draw(OPTIONAL_POSITIVE))
        return _op(kind, station_id=station.id, step=step)
    if kind == "set_param_station":
        if data.draw(st.booleans()):
            return _op("set_param", station_id=station.id, name=data.draw(st.sampled_from(["width_mm", "height_mm"])),
                       value=data.draw(OPTIONAL_POSITIVE))
        return _op("set_param", station_id=station.id, name=data.draw(st.sampled_from(["stroke", "pressure", "temp"])),
                   value=data.draw(st.none() | st.floats(-1e3, 1e3)), unit=data.draw(st.none() | TEXT))
    if kind == "connect":
        # Only forward along the station list, so the graph stays acyclic.
        i, j = sorted(data.draw(st.lists(st.integers(0, len(stations) - 1), min_size=2, max_size=2, unique=True)))
        return _op(kind, transport=Transport(
            id=_fresh("tr", {t.id for t in design.transports}), from_station=stations[i].id,
            to_station=stations[j].id, kind=data.draw(st.sampled_from(["belt", "indexing", "rotary"])),
            speed_mm_s=data.draw(OPTIONAL_POSITIVE), buffer_capacity=data.draw(st.none() | st.integers(0, 50)),
            reject_rate=data.draw(st.none() | st.floats(0, 1))))
    if kind in ("remove_component", "replace_component"):
        station = data.draw(st.sampled_from([s for s in stations if s.components]))
        old = data.draw(st.sampled_from(station.components))
        if kind == "remove_component":
            return _op(kind, component_id=old.id)
        replacement = _draw_component(data, design, station).model_copy(update={"id": old.id})
        return _op(kind, component_id=old.id, component=replacement)
    if kind == "remove_step":
        station = data.draw(st.sampled_from([s for s in stations if s.steps]))
        return _op(kind, station_id=station.id, step_id=data.draw(st.sampled_from(station.steps)).id)
    if kind == "disconnect":
        return _op(kind, transport_id=data.draw(st.sampled_from(design.transports)).id)
    assert kind == "remove_station"
    connected = {n for t in design.transports for n in (t.from_station, t.to_station, t.reject_to)}
    return _op(kind, station_id=data.draw(st.sampled_from([s for s in stations if s.id not in connected])).id)


def _assert_consistent(design: MachineDesign) -> None:
    assert MachineDesign.model_validate(design.model_dump()) == design
    station_ids = [s.id for s in design.stations]
    assert len(station_ids) == len(set(station_ids))
    component_ids = [c.id for s in design.stations for c in s.components]
    assert len(component_ids) == len(set(component_ids))
    assert len({t.id for t in design.transports}) == len(design.transports)
    for t in design.transports:
        assert {t.from_station, t.to_station} <= set(station_ids)
    for s in design.stations:
        mechanisms = {m.id for m in s.mechanisms}
        assert all(step.mechanism_id in mechanisms for step in s.steps if step.kind == "motion")
        assert all(c.motion is None or c.motion in mechanisms for c in s.components)
    design.process_order()


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.data())
def test_valid_patch_sequences_keep_a_valid_design(data: st.DataObject) -> None:
    start = data.draw(st.sampled_from([empty_design(), _base()]))
    design, ops = start, []
    for _ in range(data.draw(st.integers(1, 25))):
        op = _draw_valid_op(data, design)
        design = _applied(design, op)
        _assert_consistent(design)
        ops.append(op)
    # The same ops sent as one answer give the same design.
    assert _applied(start, *ops) == design


def _draw_invalid_op(data: st.DataObject, design: MachineDesign) -> tuple[PatchOp, str]:
    """An op that must fail on `design` (which always holds _base()'s st-a -> st-b), and its error code."""
    station = data.draw(st.sampled_from(design.stations))
    family = data.draw(st.sampled_from([
        "unknown_station", "unknown_component", "unknown_mechanism", "duplicate_id", "invalid_value",
        "missing_operand", "computed_field", "graph_cycle", "orphan_transport",
    ]))
    if family == "unknown_station":
        return _op("add_component", station_id="nope-" + station.id, component=_component("c-bad")), family
    if family == "unknown_component":
        return _op("remove_component", component_id="nope-" + data.draw(st.sampled_from(["a", "b"]))), family
    if family == "unknown_mechanism":
        step = Step(id="s-bad", order=1, kind="motion", mechanism_id="nope")
        return _op("add_step", station_id=station.id, step=step), family
    if family == "duplicate_id":
        return _op("add_station", station=_station(station.id)), family
    if family == "invalid_value":
        bad = data.draw(st.sampled_from(["lanes", "mass_g", "speed", "quantity"]))
        if bad == "lanes":
            return _op("set_product", product=Product(lanes=data.draw(st.integers(-5, 0)))), family
        if bad == "mass_g":
            return _op("set_product", product=Product(mass_g=data.draw(st.floats(-1e6, 0)))), family
        if bad == "speed":
            return _op("connect", transport=Transport(id="tr-new", from_station="st-a", to_station="st-frame",
                                                      speed_mm_s=data.draw(st.floats(-1e6, 0)))), family
        return _op("add_component", station_id=station.id,
                   component=_component("c-bad", quantity=data.draw(st.integers(-3, 0)))), family
    if family == "missing_operand":
        return _op(data.draw(st.sampled_from(["add_station", "connect", "set_product", "remove_step", "add_assumption"]))), family
    if family == "computed_field":
        name = data.draw(st.sampled_from(["sequence", "cycle_time_s", "placement", "schema_version", "footprint"]))
        return _op("set_param", station_id=data.draw(st.sampled_from([None, station.id])), name=name, value=1.0), family
    if family == "graph_cycle":
        edge = data.draw(st.sampled_from(design.transports))
        return _op("connect", transport=Transport(id="tr-back", from_station=edge.to_station,
                                                  to_station=edge.from_station)), family
    assert family == "orphan_transport"
    edge = data.draw(st.sampled_from(design.transports))
    return _op("remove_station", station_id=data.draw(st.sampled_from([edge.from_station, edge.to_station]))), family


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.data())
def test_invalid_patches_are_rejected_and_leave_the_design_unchanged(data: st.DataObject) -> None:
    design = _base()
    for _ in range(data.draw(st.integers(0, 10))):
        design = _applied(design, _draw_valid_op(data, design, removals=False))
    valid = [_draw_valid_op(data, design, removals=False)]
    bad, code = _draw_invalid_op(data, design)
    errors = _rejected(design, *valid, bad)
    assert [(index, c) for index, c, _ in errors] == [(1, code)]
