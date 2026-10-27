"""Services read structured fields (role, signals, motion), never names or free text (rule 1)."""

from __future__ import annotations

from app.llm.mock import SCENARIOS, demo_design
from app.models import Component, MachineDesign, Mechanism, Signals, Spec, Station, Step
from app.services.diff import diff_designs
from app.services.documents import build_document, cycle_check
from app.services.io_points import components_without_signals, io_points
from app.services.layout import compute_layout
from app.services.spare_parts import build_catalog

# Words the v0.3 rules looked for in names and specs. A rename to them must change nothing.
KEYWORDS = "thermocouple ejector gun tube door relay camera terminal axis heat power analog 4-20"


def _renamed(design: MachineDesign) -> MachineDesign:
    """Every display name and free text replaced; ids and structured fields untouched."""
    out = design.model_copy(deep=True)
    out.name, out.summary, out.machine_type = KEYWORDS, KEYWORDS, KEYWORDS
    out.target_rate_text, out.product.description = "7 parts/h", KEYWORDS
    for i, station in enumerate(out.stations):
        station.name, station.function = f"{KEYWORDS} {i}", KEYWORDS
        for j, component in enumerate(station.components):
            component.name = f"{KEYWORDS} {j}"
            component.specs = [Spec(name=KEYWORDS, value=KEYWORDS)]
    return out


def _station(*components: Component, kind: str = "process") -> MachineDesign:
    return MachineDesign(name="t", machine_type="t", summary="t", stations=[
        Station(id="s1", name="Station", function="f", kind=kind,  # type: ignore[arg-type]
                mechanisms=[Mechanism(id="m-lift", kind="linear"), Mechanism(id="m-turn", kind="rotary")],
                components=list(components)),
    ])


def _points(design: MachineDesign) -> list[tuple[str, str, str, str | None]]:
    return [(p.tag, p.kind, p.description, p.mechanism) for p in io_points(design)]


def test_io_points_follow_role_signals_and_motion() -> None:
    design = _station(
        # Counts come from signals, not from the category: this cylinder has one end-position sensor.
        Component(id="cyl", name="Thermocouple", category="pneumatic_actuator", quantity=1, role="actuator",
                  signals=Signals(do=1, di=1), motion="m-lift"),
        Component(id="probe", name="Door", category="sensor", quantity=1, role="sensor", signals=Signals(di=1, ai=1)),
        # The role decides whether a safety device's inputs are safety inputs.
        Component(id="door", name="Relay", category="safety", quantity=1, role="sensor", signals=Signals(di=2)),
        Component(id="relay", name="Door switch", category="safety", quantity=1, role="controller",
                  signals=Signals(di=1, do=1)),
        Component(id="servo", name="Gun", category="servo_motor", quantity=2, role="actuator",
                  signals=Signals(axes=1), motion="m-turn"),
        Component(id="extra", name="Camera", category="other", quantity=1, role=None, signals=Signals(ao=1, di=2)),
        Component(id="frame", name="Axis", category="frame_structure", quantity=1, role="structure", signals=Signals()),
    )
    assert _points(design) == [
        ("S01.cyl.DO1", "DO", "valve coil", "m-lift"),
        ("S01.cyl.DI1", "DI", "end position 1", "m-lift"),
        ("S01.probe.DI1", "DI", "signal", None),
        ("S01.probe.AI1", "AI", "measurement", None),
        ("S01.door.SafetyDI1", "Safety DI", "channel A", None),
        ("S01.door.SafetyDI2", "Safety DI", "channel B", None),
        ("S01.relay.DI1", "DI", "safety relay status", None),
        ("S01.relay.DO1", "DO", "safety relay reset", None),
        ("S01.servo.1.Axis1", "Axis", "servo axis", "m-turn"),
        ("S01.servo.2.Axis1", "Axis", "servo axis", "m-turn"),
        ("S01.extra.DI1", "DI", "input 1", None),
        ("S01.extra.DI2", "DI", "input 2", None),
        ("S01.extra.AO1", "AO", "analog output 1", None),
    ]


def test_components_without_signals_get_no_io_points_and_are_listed() -> None:
    unknown = Component(id="cyl", name="Cylinder", category="pneumatic_actuator", quantity=2, role="actuator")
    design = _station(unknown)
    assert io_points(design) == []
    assert [(s.id, c.id) for s, c in components_without_signals(design)] == [("s1", "cyl")]
    io = next(s for s in build_document(design, 1).sections if s.id == "io")
    assert "No signals given for 1 component, not counted: Cylinder (Station)." in io.paragraphs


def test_renaming_a_component_does_not_change_io_points() -> None:
    for scenario in SCENARIOS:
        design = demo_design(scenario)
        before = [(p.tag, p.kind, p.description) for p in io_points(design)]
        assert before, scenario
        assert [(p.tag, p.kind, p.description) for p in io_points(_renamed(design))] == before, scenario


def test_renaming_does_not_change_the_documents() -> None:
    def facts(design: MachineDesign) -> dict[str, object]:
        doc = build_document(design, 1)
        sections = {s.id: s for s in doc.sections}
        io, hazards, safety = sections["io"].table, sections["hazards"].table, sections["safety"].table
        assert io and hazards and safety
        return {
            "io_summary": doc.io_summary,
            "io": [[r[0], *r[3:]] for r in io.rows],  # without the station and component names
            "hazards": [r[1:3] + r[4:] for r in hazards.rows],
            "safety": safety.rows,
        }

    for scenario in SCENARIOS:
        design = demo_design(scenario)
        assert facts(_renamed(design)) == facts(design), scenario


def _timed(rate: str | None) -> MachineDesign:
    return MachineDesign(name="t", machine_type="t", summary="t", target_rate_text=rate, stations=[
        Station(id="s1", name="Press", function="f",
                steps=[Step(id="t", order=1, kind="fixed_duration", duration_s=1.0)]),
    ])


def test_documents_do_not_parse_the_stated_rate() -> None:
    lines = cycle_check(_timed("120 parts/min"))
    assert lines == [
        "Slowest station: Press at 1 s/cycle, so the line can run at most 60.0 cycles/min.",
        "Required throughput as stated: 120 parts/min (free text, not compared with the cycle time).",
    ]
    assert cycle_check(_timed(None)) == lines[:1]


def test_renaming_stations_does_not_change_the_spare_parts_catalog() -> None:
    def design(second_name: str) -> MachineDesign:
        part = {"category": "pneumatic_actuator", "quantity": 1, "manufacturer": "Festo", "part_number": "DSBC-32"}
        return MachineDesign(name="t", machine_type="t", summary="t", stations=[
            Station(id="s1", name="Gripper", function="f", components=[Component(id="c1", name="Cyl", **part)]),
            Station(id="s2", name=second_name, function="f", components=[Component(id="c2", name="Cyl", **part)]),
        ])

    same, different = build_catalog(design("Gripper")), build_catalog(design("Pusher"))
    assert [(p.key, p.quantity_in_machine, p.component_ids, len(p.used_in)) for p in same] == [
        (p.key, p.quantity_in_machine, p.component_ids, len(p.used_in)) for p in different
    ] == [("festo|DSBC32", 2, ["c1", "c2"], 2)]


def test_renaming_does_not_change_the_layout() -> None:
    def boxes(design: MachineDesign) -> list[dict[str, object]]:
        return [b.model_dump(exclude={"label"}) for b in compute_layout(design).boxes]

    for scenario in SCENARIOS:
        design = demo_design(scenario)
        assert boxes(_renamed(design)) == boxes(design), scenario


def test_renaming_a_component_shows_only_a_name_change_in_the_diff() -> None:
    before = demo_design("blister")
    after = before.model_copy(deep=True)
    after.stations[0].components[0].name = KEYWORDS
    d = diff_designs(before, after, 1, 2)
    assert [(c.component_id, [f.field for f in c.fields]) for c in d.components] == [
        (before.stations[0].components[0].id, ["name"])
    ]


def test_diff_reports_role_signals_and_motion() -> None:
    before = _station(Component(id="cyl", name="Cylinder", category="pneumatic_actuator", quantity=1,
                                role="actuator", signals=Signals(do=1, di=2), motion="m-lift"))
    after = before.model_copy(deep=True)
    cylinder = after.stations[0].components[0]
    cylinder.role, cylinder.signals, cylinder.motion = "tooling", Signals(do=1), None
    d = diff_designs(before, after, 1, 2)
    assert [(f.field, f.before, f.after) for f in d.components[0].fields] == [
        ("role", "actuator", "tooling"),
        ("signals", "DI 2, DO 1", "DO 1"),
        ("motion", "m-lift", None),
    ]
