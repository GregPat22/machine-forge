"""Offline demo provider.

Builds one of a few fixed demo machines, picked by an explicit scenario id (`MF_MOCK_SCENARIO`,
default blister), and answers every later request with its next scripted edit. It never reads the
problem or the request text (Phase 1 spec, section F). It is for tests, demos without an API key
and UI development, not for real design work. Like a real model it answers with patches, which the
designer validates.

The demo machines follow the rules of the system prompt where the data allows: every component
has its signals and, where one fits, a role; moving axes are mechanisms, linked to the components
that drive them, with a stroke only where a component spec states it and no speeds. Their steps
are still one fixed-duration step per station (the v1 cycle times) until the Phase 2 timing engine.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from app.llm.base import LLMError, LLMNotConfigured, ProgressFn, T, Turn, progress_from_text
from app.models import (
    Component,
    ComponentRole,
    MachineDesign,
    Mechanism,
    Product,
    Signals,
    Spec,
    Station,
    Step,
    Transport,
)
from app.services.patch import PatchOp, PatchUpdate

DEFAULT_SCENARIO = "blister"


def _io(**counts: int) -> Signals:
    return Signals(**counts)


def _c(
    cid: str,
    name: str,
    category: str,
    qty: int = 1,
    specs: dict[str, str] | None = None,
    *,
    role: ComponentRole | None,
    io: Signals,
    **kw: Any,
) -> Component:
    return Component(
        id=cid,
        name=name,
        category=category,  # type: ignore[arg-type]
        quantity=qty,
        specs=[Spec(name=k, value=v) for k, v in (specs or {}).items()],
        role=role,
        signals=io,
        **kw,
    )


def _station(cycle_time_s: float | None = None, **kw: Any) -> Station:
    """A station; a known cycle time becomes one fixed-duration step and the target cycle time."""
    steps = []
    if cycle_time_s is not None:
        steps = [Step(id=f"{kw['id']}-cycle", order=1, kind="fixed_duration", duration_s=cycle_time_s)]
    return Station(steps=steps, target_cycle_time_s=cycle_time_s, **kw)


def _axis(mid: str, kind: str, stroke: float | None = None) -> Mechanism:
    """A moving axis. Speed and acceleration stay unknown until a drive is chosen."""
    return Mechanism(id=mid, kind=kind, stroke=stroke)  # type: ignore[arg-type]


def _belts(flow: list[str]) -> list[Transport]:
    """The process graph of a straight line: one belt between consecutive stations, numbers unknown."""
    return [Transport(id=f"tr-{a}-{b}", from_station=a, to_station=b, kind="belt") for a, b in zip(flow, flow[1:])]


def _servo(cid: str, name: str, torque: str, motion: str) -> Component:
    return _c(cid, name, "servo_motor", specs={"rated torque": torque, "feedback": "absolute encoder"},
              role="actuator", io=_io(axes=1), motion=motion,
              manufacturer="Siemens", criticality="A", recommended_spares=1)


def _cylinder(cid: str, name: str, bore: str, stroke: str, motion: str, criticality: str = "A") -> Component:
    return _c(cid, name, "pneumatic_actuator", 1, {"bore": bore, "stroke": stroke},
              role="actuator", io=_io(do=1, di=2), motion=motion,
              manufacturer="Festo", criticality=criticality, recommended_spares=1)


def _blister() -> list[Station]:
    return [
        _station(id="st-forming", name="Film unwind and forming", kind="process",
                 function="Unwinds PVC film, heats it and thermoforms the blister cavities", cycle_time_s=1.2,
                 mechanisms=[_axis("m-film-index", "linear"), _axis("m-forming-lift", "linear", 50)],
                 components=[
                     _c("forming-heater", "Contact heating plates", "heating", 2, {"power": "1.5 kW", "max temp": "160 C"},
                        role="actuator", io=_io(do=1), wear_part=True, criticality="A", recommended_spares=1),
                     _c("forming-die", "Forming die (format part)", "custom_part", 1, {"material": "aluminium 7075"},
                        role="tooling", io=_io(), make_or_buy="make", criticality="A"),
                     _servo("forming-servo", "Film index servo", "6 Nm", "m-film-index"),
                     _cylinder("forming-cyl", "Forming station cylinder", "80 mm", "50 mm", "m-forming-lift"),
                 ]),
        _station(id="st-feeding", name="Product feeding", kind="process",
                 function="Fills each cavity with one product", cycle_time_s=1.2,
                 components=[
                     _c("feeder-brush", "Brush feeder", "dosing", 1, {"width": "250 mm"}, role="tooling", io=_io(),
                        wear_part=True, criticality="B", recommended_spares=1),
                     _c("feeder-motor", "Brush feeder gearmotor", "motor", 1, {"power": "0.37 kW", "voltage": "400 V"},
                        role="actuator", io=_io(do=1, di=1), manufacturer="SEW-Eurodrive", criticality="B"),
                     _c("feeder-check", "Empty cavity sensor", "sensor", 4, {"type": "diffuse photoelectric", "IP": "IP67"},
                        role="sensor", io=_io(di=1), manufacturer="SICK", criticality="B", recommended_spares=2),
                 ]),
        _station(id="st-sealing", name="Lidding and sealing", kind="process",
                 function="Seals aluminium lidding foil onto the formed web", cycle_time_s=1.2,
                 mechanisms=[_axis("m-sealing-lift", "linear", 40)],
                 components=[
                     _c("sealing-plate", "Heated sealing plate", "sealing", 1, {"power": "2 kW", "pattern": "knurled"},
                        role="tooling", io=_io(do=1), make_or_buy="make", wear_part=True, criticality="A",
                        recommended_spares=1),
                     _cylinder("sealing-cyl", "Sealing cylinder", "100 mm", "40 mm", "m-sealing-lift"),
                     _c("sealing-tc", "Thermocouple type J", "sensor", 2, {"type": "J", "length": "100 mm"},
                        role="sensor", io=_io(ai=1), wear_part=True, criticality="A", recommended_spares=2),
                 ]),
        _station(id="st-cutting", name="Punching", kind="process",
                 function="Punches individual blisters out of the web", cycle_time_s=1.2,
                 mechanisms=[_axis("m-punch", "linear")],
                 components=[
                     _c("punch-tool", "Punching tool (format part)", "cutting", 1, {"material": "tool steel"},
                        role="tooling", io=_io(), make_or_buy="make", wear_part=True, criticality="A",
                        recommended_spares=1),
                     _servo("punch-servo", "Punch drive servo", "10 Nm", "m-punch"),
                 ]),
    ]


def _cartoner() -> list[Station]:
    return [
        _station(id="st-magazine", name="Carton magazine and erection", kind="process",
                 function="Picks flat cartons from the magazine and opens them", cycle_time_s=0.4,
                 mechanisms=[_axis("m-picker", "rotary")],
                 components=[
                     _c("erect-cups", "Vacuum suction cups", "vacuum", 6, {"diameter": "30 mm", "material": "NBR"},
                        role="tooling", io=_io(), manufacturer="Schmalz", wear_part=True, criticality="A",
                        recommended_spares=12),
                     _c("erect-ejector", "Vacuum ejector", "vacuum", 1, {"flow": "70 Nl/min"}, role="actuator",
                        io=_io(do=1, di=1), manufacturer="Schmalz", criticality="A", recommended_spares=1),
                     _servo("erect-servo", "Rotary picker servo", "4 Nm", "m-picker"),
                 ]),
        _station(id="st-insertion", name="Product insertion", kind="process",
                 function="Pushes product and leaflet into the open carton", cycle_time_s=0.4,
                 mechanisms=[_axis("m-pusher", "linear")],
                 components=[
                     _servo("insert-servo", "Pusher chain servo", "12 Nm", "m-pusher"),
                     _c("insert-chain", "Pusher chain", "transmission", 1, {"pitch": "12.7 mm (08B)"}, role=None,
                        io=_io(), wear_part=True, criticality="A", recommended_spares=1),
                 ]),
        _station(id="st-closing", name="Flap closing and gluing", kind="process",
                 function="Folds and glues the carton flaps", cycle_time_s=0.4,
                 components=[
                     _c("glue-unit", "Hot-melt unit", "dosing", 1, {"tank": "4 l"}, role="actuator",
                        io=_io(do=1, di=1), manufacturer="Nordson", criticality="A"),
                     _c("glue-guns", "Hot-melt guns", "dosing", 2, {"modules": "1"}, role="actuator", io=_io(do=1),
                        manufacturer="Nordson", wear_part=True, criticality="A", recommended_spares=1),
                 ]),
    ]


def _filling() -> list[Station]:
    return [
        _station(id="st-infeed", name="Bottle infeed", kind="transport",
                 function="Spaces bottles with an infeed screw and star wheel", cycle_time_s=0.5,
                 mechanisms=[_axis("m-star-wheel", "rotary")],
                 components=[
                     _c("infeed-screw", "Timing screw (format part)", "custom_part", 1, {"material": "UHMW-PE"},
                        role="tooling", io=_io(), make_or_buy="make", wear_part=True, criticality="A",
                        recommended_spares=1),
                     _servo("infeed-servo", "Star wheel servo", "6 Nm", "m-star-wheel"),
                 ]),
        _station(id="st-filling", name="Filling", kind="process",
                 function="Doses liquid with peristaltic pumps and checkweighs", cycle_time_s=0.5,
                 components=[
                     _c("fill-pump", "Peristaltic dosing pump", "pump", 4, {"accuracy": "+/-0.5 %"}, role="actuator",
                        io=_io(do=1, di=1), manufacturer="Watson-Marlow", criticality="A", recommended_spares=1),
                     _c("fill-tube", "Pump tubing", "pump", 4, {"material": "silicone, pharma grade"},
                        role="consumable", io=_io(), wear_part=True, criticality="A", recommended_spares=8),
                     _c("fill-cell", "Load cell", "sensor", 4, {"capacity": "1 kg"}, role="sensor", io=_io(ai=1),
                        criticality="B", recommended_spares=1),
                 ]),
        _station(id="st-capping", name="Capping", kind="process",
                 function="Places and screws caps with torque control", cycle_time_s=0.5,
                 mechanisms=[_axis("m-capping-head", "rotary")],
                 components=[
                     _servo("cap-servo", "Capping head servo", "2 Nm", "m-capping-head"),
                     _c("cap-chuck", "Capping chuck inserts", "custom_part", 4, {"material": "PU"}, role="tooling",
                        io=_io(), make_or_buy="make", wear_part=True, criticality="A", recommended_spares=4),
                 ]),
    ]


def _assembly() -> list[Station]:
    return [
        _station(id="st-pick", name="Pick and place", kind="process",
                 function="Picks parts from the infeed and places them in the fixture", cycle_time_s=3.0,
                 mechanisms=[_axis("m-x", "linear", 600), _axis("m-z", "linear", 150), _axis("m-gripper", "linear")],
                 components=[
                     _c("pp-axis-x", "Linear axis X", "linear_motion", 1, {"stroke": "600 mm", "payload": "5 kg"},
                        role="actuator", io=_io(axes=1), motion="m-x", manufacturer="Festo", criticality="A"),
                     _c("pp-axis-z", "Linear axis Z", "linear_motion", 1, {"stroke": "150 mm"}, role="actuator",
                        io=_io(axes=1), motion="m-z", manufacturer="Festo", criticality="A"),
                     _c("pp-gripper", "Parallel gripper", "pneumatic_actuator", 1, {"stroke": "2x10 mm"},
                        role="actuator", io=_io(do=1, di=2), motion="m-gripper", manufacturer="SCHUNK",
                        wear_part=True, criticality="A", recommended_spares=1),
                 ]),
        _station(id="st-assembly", name="Assembly", kind="process",
                 function="Presses the parts together with force monitoring", cycle_time_s=3.0,
                 mechanisms=[_axis("m-press", "linear")],
                 components=[
                     _c("press", "Servo press", "servo_motor", 1, {"force": "5 kN"}, role="actuator", io=_io(axes=1),
                        motion="m-press", criticality="A"),
                     _c("press-fixture", "Assembly fixture", "custom_part", 1, {"material": "steel, hardened"},
                        role="tooling", io=_io(), make_or_buy="make", wear_part=True, criticality="A",
                        recommended_spares=1),
                 ]),
    ]


# Scenario id -> (machine type, product, required rate as stated, process stations).
SCENARIO_MACHINES: dict[str, tuple[str, str, str, Callable[[], list[Station]]]] = {
    "blister": ("Thermoforming blister packaging machine", "blisters", "300 tablets/min", _blister),
    "cartoner": ("Horizontal continuous-motion cartoner", "cartons", "120 tubes/min", _cartoner),
    "filling": ("Rotary filling and capping monoblock", "bottles", "60 bottles/min", _filling),
    "assembly": ("Automatic assembly cell", "parts", "20 pieces/min", _assembly),
}
SCENARIOS = tuple(SCENARIO_MACHINES)


def _infrastructure() -> list[Station]:
    return [
        _station(id="st-outfeed", name="Outfeed and reject", kind="transport",
                 function="Conveys good product out and rejects faulty product", cycle_time_s=None,
                 mechanisms=[_axis("m-reject", "linear", 100)],
                 components=[
                     _c("out-belt", "Outfeed conveyor belt", "conveyor", 1, {"width": "200 mm", "length": "1.5 m"},
                        role=None, io=_io(), wear_part=True, criticality="B", recommended_spares=1),
                     _c("out-motor", "Conveyor gearmotor", "motor", 1, {"power": "0.25 kW"}, role="actuator",
                        io=_io(do=1, di=1), manufacturer="SEW-Eurodrive", criticality="B"),
                     _cylinder("reject-cyl", "Reject pusher cylinder", "25 mm", "100 mm", "m-reject", criticality="B"),
                 ]),
        _station(id="st-frame", name="Machine frame", kind="frame",
                 function="Welded base frame and stainless steel cladding", components=[
                     _c("frame-base", "Welded base frame", "frame_structure", 1, {"material": "AISI 304"},
                        role="structure", io=_io(), make_or_buy="make"),
                     _c("frame-feet", "Levelling feet", "frame_structure", 6, {"load": "1000 kg"}, role="structure",
                        io=_io(), manufacturer="Elesa+Ganter"),
                 ]),
        _station(id="st-control", name="Control cabinet", kind="control",
                 function="PLC, drives, power distribution and HMI", components=[
                     _c("plc-cpu", "PLC CPU", "plc", 1, {"family": "SIMATIC S7-1500"}, role="controller", io=_io(),
                        manufacturer="Siemens", part_number="6ES7515-2AM02-0AB0", criticality="A", recommended_spares=1),
                     _c("servo-drives", "Servo drives", "drive", 4, {"family": "SINAMICS S210"}, role="drive",
                        io=_io(fieldbus=1), manufacturer="Siemens", criticality="A", recommended_spares=1),
                     _c("hmi", "HMI touch panel", "hmi", 1, {"size": "15 in"}, role="controller", io=_io(fieldbus=1),
                        manufacturer="Siemens", criticality="B"),
                     _c("psu", "24 V DC power supply", "electrical", 1, {"current": "20 A"}, role=None, io=_io(),
                        manufacturer="Phoenix Contact", criticality="A", recommended_spares=1),
                 ]),
        _station(id="st-safety", name="Safety", kind="safety",
                 function="Guarding, interlocked doors and emergency stop", components=[
                     _c("safety-relay", "Safety relay", "safety", 1, {"contacts": "3 NO + 1 NC", "supply": "24 V DC"},
                        role="controller", io=_io(di=1, do=1), manufacturer="Pilz", part_number="750104",
                        criticality="A", recommended_spares=1),
                     # Two channels; the model has no separate count for safety inputs yet.
                     _c("door-switch", "Interlock door switch", "safety", 4, {"type": "RFID coded"}, role="sensor",
                        io=_io(di=2), manufacturer="Schmersal", criticality="A", recommended_spares=1),
                     _c("guards", "Polycarbonate guards", "guarding", 4, {"thickness": "6 mm"}, role="structure",
                        io=_io(), make_or_buy="make"),
                 ]),
        _station(id="st-pneumatics", name="Compressed air", kind="utility",
                 function="Air treatment and valve terminal", components=[
                     _c("air-frl", "Filter regulator unit", "air_treatment", 1, {"port": "G1/2", "filter": "5 um"},
                        role=None, io=_io(do=1, di=1), manufacturer="Festo", criticality="A"),
                     _c("valve-terminal", "Valve terminal", "pneumatic_valve", 1, {"valves": "8", "bus": "PROFINET"},
                        role="actuator", io=_io(fieldbus=1), manufacturer="Festo", criticality="A",
                        recommended_spares=1),
                 ]),
    ]


# Station envelopes (length along the flow, width, height) in mm.
ENVELOPES: dict[str, tuple[float, float, float]] = {
    "st-forming": (1800, 900, 1900),
    "st-feeding": (1200, 900, 1700),
    "st-sealing": (1000, 900, 1800),
    "st-cutting": (900, 900, 1700),
    "st-magazine": (1400, 1000, 1800),
    "st-insertion": (2000, 900, 1500),
    "st-closing": (1200, 900, 1500),
    "st-infeed": (900, 700, 1400),
    "st-filling": (1400, 1400, 2000),
    "st-capping": (1200, 1400, 2000),
    "st-pick": (1200, 1000, 2000),
    "st-assembly": (1000, 900, 1900),
    "st-outfeed": (1500, 500, 1000),
    "st-vision": (700, 900, 1800),
    "st-control": (1600, 600, 2000),
    "st-pneumatics": (800, 300, 1000),
}


def _with_envelopes(stations: list[Station]) -> list[Station]:
    for station in stations:
        if station.id in ENVELOPES:
            station.length_mm, station.width_mm, station.height_mm = ENVELOPES[station.id]
    return stations


def demo_design(scenario: str = DEFAULT_SCENARIO) -> MachineDesign:
    """The demo machine of `scenario`, as its first answer builds it."""
    machine_type, product, rate, process_stations = SCENARIO_MACHINES[scenario]
    process = process_stations()
    return MachineDesign(
        name=f"{machine_type} (demo)",
        machine_type=machine_type,
        summary=f"{machine_type} built by the offline demo engine (scenario '{scenario}'). "
        "It does not read the problem text.",
        product=Product(description=product),
        target_rate_text=rate,
        footprint=None,
        stations=_with_envelopes([*process, *_infrastructure()]),
        transports=_belts([*(s.id for s in process), "st-outfeed"]),
        utilities=["400 V 3~ 50 Hz", "6 bar dry compressed air"],
        assumptions=["Generated by the offline demo engine, not by an AI model."],
        open_questions=["Axis speeds and accelerations are not set: which drives and cylinders, at what settings?"],
    )


def _vision_station() -> Station:
    return _station(id="st-vision", name="Vision inspection", kind="inspection",
                    function="Checks presence and integrity of every product", cycle_time_s=None,
                    components=[
                        _c("vision-cam", "Smart camera", "vision", 1, {"resolution": "5 MP"}, role="sensor",
                           io=_io(fieldbus=1, do=1, di=1), manufacturer="Cognex", criticality="B"),
                        _c("vision-light", "Ring light", "vision", 1, {"colour": "red, 625 nm"}, role=None, io=_io(),
                           criticality="B", recommended_spares=1),
                    ])


def _design_patches(design: MachineDesign) -> list[PatchOp]:
    """The patches that build `design` from an empty design."""
    machine = [("name", design.name), ("machine_type", design.machine_type), ("summary", design.summary),
               ("layout_style", design.layout_style), ("target_rate_text", design.target_rate_text)]
    return [
        *(PatchOp(op="set_param", name=name, text=text) for name, text in machine if text is not None),
        PatchOp(op="set_product", product=design.product),
        *(PatchOp(op="add_station", station=s) for s in design.stations),
        *(PatchOp(op="connect", transport=t) for t in design.transports),
        PatchOp(op="set_utility", items=design.utilities),
        *(PatchOp(op="add_assumption", text=a) for a in design.assumptions),
        *(PatchOp(op="add_open_question", text=q) for q in design.open_questions),
    ]


def _add_vision(design: MachineDesign) -> list[PatchOp]:
    """Add the vision station at the end of the line, before the outfeed when there is one."""
    vision = _with_envelopes([_vision_station()])[0]
    patches = [PatchOp(op="add_station", station=vision)]
    into_outfeed = [t for t in design.transports if t.to_station == "st-outfeed"]
    if into_outfeed:
        for t in into_outfeed:
            patches += [PatchOp(op="disconnect", transport_id=t.id),
                        PatchOp(op="connect", transport=Transport(id=f"tr-{t.from_station}-st-vision",
                                                                  from_station=t.from_station, to_station="st-vision"))]
        patches.append(PatchOp(op="connect", transport=Transport(id="tr-st-vision-st-outfeed",
                                                                 from_station="st-vision", to_station="st-outfeed")))
    else:
        flow = [s for s in design.stations if s.sequence > 0]
        if flow:
            last = max(flow, key=lambda s: s.sequence).id
            patches.append(PatchOp(op="connect", transport=Transport(id=f"tr-{last}-st-vision",
                                                                     from_station=last, to_station="st-vision")))
    return patches


def _layout(style: str) -> list[PatchOp]:
    return [PatchOp(op="set_param", name="layout_style", text=style)]


SCRIPT_NOTE = "Demo engine: it does not read requests; each one applies its next scripted edit."


def _refine(design: MachineDesign) -> PatchUpdate:
    """The next scripted edit, chosen from the design: add vision in a U-shape, then switch the layout."""
    if not any(s.id == "st-vision" for s in design.stations):
        return PatchUpdate(reply=f"{SCRIPT_NOTE} Added a vision inspection station before the outfeed and "
                                 "arranged the line in a U-shape.",
                           patches=[*_add_vision(design), *_layout("u_shape")])
    style, label = ("inline", "a straight line") if design.layout_style == "u_shape" else ("u_shape", "a U-shape")
    return PatchUpdate(reply=f"{SCRIPT_NOTE} Arranged the line in {label}.", patches=_layout(style))


class MockProvider:
    name = "mock"
    model = "demo-engine"
    strict_schema = True  # answers are built as PatchUpdate objects, so they always match the schema
    tools = False
    thinking = False

    def __init__(self, scenario: str | None = None) -> None:
        chosen = scenario or os.environ.get("MF_MOCK_SCENARIO", "").strip().lower() or DEFAULT_SCENARIO
        if chosen not in SCENARIO_MACHINES:
            raise LLMNotConfigured(f"Unknown MF_MOCK_SCENARIO '{chosen}'. Use one of: {', '.join(SCENARIOS)}.")
        self.scenario = chosen

    def structured(
        self, *, system: str, turns: list[Turn], output: type[T], on_progress: ProgressFn | None = None
    ) -> T:
        if output is not PatchUpdate:
            raise LLMError("The demo engine only produces design patches.")
        if on_progress:
            on_progress(progress_from_text("thinking", "", f"Demo engine: scenario '{self.scenario}'"))
        result = self._answer(turns)
        if on_progress:
            on_progress(progress_from_text("writing", result.model_dump_json()))
        return result  # type: ignore[return-value]

    def _answer(self, turns: list[Turn]) -> PatchUpdate:
        # The current design is structured data inside the refine turn; the request text is never read.
        current = re.search(r"<current_design>\n(.*?)\n</current_design>", turns[-1]["content"], re.S)
        if current:
            return _refine(MachineDesign.model_validate(json.loads(current.group(1))))
        design = demo_design(self.scenario)
        reply = (f"Demo machine '{self.scenario}': {len(design.stations)} stations. The demo engine does not read "
                 f"your text; set MF_MOCK_SCENARIO to {', '.join(SCENARIOS)} for another machine, or set up an AI "
                 "provider for real designs.")
        return PatchUpdate(reply=reply, patches=_design_patches(design))
