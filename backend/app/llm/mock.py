"""Offline demo provider.

Builds a plausible machine from keywords in the problem statement and understands a few
refinement requests. It is for tests, demos without an API key and UI development, not for
real design work.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.llm.base import LLMError, ProgressFn, T, Turn, progress_from_text
from app.models import Component, DesignUpdate, MachineDesign, Spec, Station


def _c(cid: str, name: str, category: str, qty: int = 1, specs: dict[str, str] | None = None, **kw: Any) -> Component:
    return Component(
        id=cid,
        name=name,
        category=category,  # type: ignore[arg-type]
        quantity=qty,
        specs=[Spec(name=k, value=v) for k, v in (specs or {}).items()],
        **kw,
    )


def _servo(cid: str, name: str, torque: str) -> Component:
    return _c(cid, name, "servo_motor", specs={"rated torque": torque, "feedback": "absolute encoder"},
              manufacturer="Siemens", criticality="A", recommended_spares=1)


def _process_stations(problem: str) -> tuple[str, str, list[Station]]:
    p = problem.lower()
    if "blister" in p:
        return "Thermoforming blister packaging machine", "blisters", [
            Station(id="st-forming", name="Film unwind and forming", kind="process", sequence=1,
                    function="Unwinds PVC film, heats it and thermoforms the blister cavities", cycle_time_s=1.2,
                    components=[
                        _c("forming-heater", "Contact heating plates", "heating", 2, {"power": "1.5 kW", "max temp": "160 C"},
                           wear_part=True, criticality="A", recommended_spares=1),
                        _c("forming-die", "Forming die (format part)", "custom_part", 1, {"material": "aluminium 7075"},
                           make_or_buy="make", criticality="A"),
                        _servo("forming-servo", "Film index servo", "6 Nm"),
                        _c("forming-cyl", "Forming station cylinder", "pneumatic_actuator", 1, {"bore": "80 mm", "stroke": "50 mm"},
                           manufacturer="Festo", criticality="A", recommended_spares=1),
                    ]),
            Station(id="st-feeding", name="Product feeding", kind="process", sequence=2,
                    function="Fills each cavity with one product", cycle_time_s=1.2,
                    components=[
                        _c("feeder-brush", "Brush feeder", "dosing", 1, {"width": "250 mm"}, wear_part=True,
                           criticality="B", recommended_spares=1),
                        _c("feeder-motor", "Brush feeder gearmotor", "motor", 1, {"power": "0.37 kW", "voltage": "400 V"},
                           manufacturer="SEW-Eurodrive", criticality="B"),
                        _c("feeder-check", "Empty cavity sensor", "sensor", 4, {"type": "diffuse photoelectric", "IP": "IP67"},
                           manufacturer="SICK", criticality="B", recommended_spares=2),
                    ]),
            Station(id="st-sealing", name="Lidding and sealing", kind="process", sequence=3,
                    function="Seals aluminium lidding foil onto the formed web", cycle_time_s=1.2,
                    components=[
                        _c("sealing-plate", "Heated sealing plate", "sealing", 1, {"power": "2 kW", "pattern": "knurled"},
                           make_or_buy="make", wear_part=True, criticality="A", recommended_spares=1),
                        _c("sealing-cyl", "Sealing cylinder", "pneumatic_actuator", 1, {"bore": "100 mm", "stroke": "40 mm"},
                           manufacturer="Festo", criticality="A", recommended_spares=1),
                        _c("sealing-tc", "Thermocouple type J", "sensor", 2, {"type": "J", "length": "100 mm"},
                           wear_part=True, criticality="A", recommended_spares=2),
                    ]),
            Station(id="st-cutting", name="Punching", kind="process", sequence=4,
                    function="Punches individual blisters out of the web", cycle_time_s=1.2,
                    components=[
                        _c("punch-tool", "Punching tool (format part)", "cutting", 1, {"material": "tool steel"},
                           make_or_buy="make", wear_part=True, criticality="A", recommended_spares=1),
                        _servo("punch-servo", "Punch drive servo", "10 Nm"),
                    ]),
        ]
    if any(k in p for k in ("carton", "box", "astucc", "case")):
        return "Horizontal continuous-motion cartoner", "cartons", [
            Station(id="st-magazine", name="Carton magazine and erection", kind="process", sequence=1,
                    function="Picks flat cartons from the magazine and opens them", cycle_time_s=0.4,
                    components=[
                        _c("erect-cups", "Vacuum suction cups", "vacuum", 6, {"diameter": "30 mm", "material": "NBR"},
                           manufacturer="Schmalz", wear_part=True, criticality="A", recommended_spares=12),
                        _c("erect-ejector", "Vacuum ejector", "vacuum", 1, {"flow": "70 Nl/min"}, manufacturer="Schmalz",
                           criticality="A", recommended_spares=1),
                        _servo("erect-servo", "Rotary picker servo", "4 Nm"),
                    ]),
            Station(id="st-insertion", name="Product insertion", kind="process", sequence=2,
                    function="Pushes product and leaflet into the open carton", cycle_time_s=0.4,
                    components=[
                        _servo("insert-servo", "Pusher chain servo", "12 Nm"),
                        _c("insert-chain", "Pusher chain", "transmission", 1, {"pitch": "12.7 mm (08B)"},
                           wear_part=True, criticality="A", recommended_spares=1),
                    ]),
            Station(id="st-closing", name="Flap closing and gluing", kind="process", sequence=3,
                    function="Folds and glues the carton flaps", cycle_time_s=0.4,
                    components=[
                        _c("glue-unit", "Hot-melt unit", "dosing", 1, {"tank": "4 l"}, manufacturer="Nordson",
                           criticality="A"),
                        _c("glue-guns", "Hot-melt guns", "dosing", 2, {"modules": "1"}, manufacturer="Nordson",
                           wear_part=True, criticality="A", recommended_spares=1),
                    ]),
        ]
    if any(k in p for k in ("fill", "bottle", "vial", "liquid", "riemp", "flacon")):
        return "Rotary filling and capping monoblock", "bottles", [
            Station(id="st-infeed", name="Bottle infeed", kind="transport", sequence=1,
                    function="Spaces bottles with an infeed screw and star wheel", cycle_time_s=0.5,
                    components=[
                        _c("infeed-screw", "Timing screw (format part)", "custom_part", 1, {"material": "UHMW-PE"},
                           make_or_buy="make", wear_part=True, criticality="A", recommended_spares=1),
                        _servo("infeed-servo", "Star wheel servo", "6 Nm"),
                    ]),
            Station(id="st-filling", name="Filling", kind="process", sequence=2,
                    function="Doses liquid with peristaltic pumps and checkweighs", cycle_time_s=0.5,
                    components=[
                        _c("fill-pump", "Peristaltic dosing pump", "pump", 4, {"accuracy": "+/-0.5 %"},
                           manufacturer="Watson-Marlow", criticality="A", recommended_spares=1),
                        _c("fill-tube", "Pump tubing", "pump", 4, {"material": "silicone, pharma grade"},
                           wear_part=True, criticality="A", recommended_spares=8),
                        _c("fill-cell", "Load cell", "sensor", 4, {"capacity": "1 kg"}, criticality="B", recommended_spares=1),
                    ]),
            Station(id="st-capping", name="Capping", kind="process", sequence=3,
                    function="Places and screws caps with torque control", cycle_time_s=0.5,
                    components=[
                        _servo("cap-servo", "Capping head servo", "2 Nm"),
                        _c("cap-chuck", "Capping chuck inserts", "custom_part", 4, {"material": "PU"},
                           make_or_buy="make", wear_part=True, criticality="A", recommended_spares=4),
                    ]),
        ]
    return "Automatic assembly cell", "parts", [
        Station(id="st-pick", name="Pick and place", kind="process", sequence=1,
                function="Picks parts from the infeed and places them in the fixture", cycle_time_s=3.0,
                components=[
                    _c("pp-axis-x", "Linear axis X", "linear_motion", 1, {"stroke": "600 mm", "payload": "5 kg"},
                       manufacturer="Festo", criticality="A"),
                    _c("pp-axis-z", "Linear axis Z", "linear_motion", 1, {"stroke": "150 mm"}, manufacturer="Festo",
                       criticality="A"),
                    _c("pp-gripper", "Parallel gripper", "pneumatic_actuator", 1, {"stroke": "2x10 mm"},
                       manufacturer="SCHUNK", wear_part=True, criticality="A", recommended_spares=1),
                ]),
        Station(id="st-assembly", name="Assembly", kind="process", sequence=2,
                function="Presses the parts together with force monitoring", cycle_time_s=3.0,
                components=[
                    _c("press", "Servo press", "servo_motor", 1, {"force": "5 kN"}, criticality="A"),
                    _c("press-fixture", "Assembly fixture", "custom_part", 1, {"material": "steel, hardened"},
                       make_or_buy="make", wear_part=True, criticality="A", recommended_spares=1),
                ]),
    ]


def _infrastructure(last_seq: int) -> list[Station]:
    return [
        Station(id="st-outfeed", name="Outfeed and reject", kind="transport", sequence=last_seq + 1,
                function="Conveys good product out and rejects faulty product", cycle_time_s=None,
                components=[
                    _c("out-belt", "Outfeed conveyor belt", "conveyor", 1, {"width": "200 mm", "length": "1.5 m"},
                       wear_part=True, criticality="B", recommended_spares=1),
                    _c("out-motor", "Conveyor gearmotor", "motor", 1, {"power": "0.25 kW"}, manufacturer="SEW-Eurodrive",
                       criticality="B"),
                    _c("reject-cyl", "Reject pusher cylinder", "pneumatic_actuator", 1, {"bore": "25 mm", "stroke": "100 mm"},
                       manufacturer="Festo", criticality="B", recommended_spares=1),
                ]),
        Station(id="st-frame", name="Machine frame", kind="frame", sequence=0,
                function="Welded base frame and stainless steel cladding", components=[
                    _c("frame-base", "Welded base frame", "frame_structure", 1, {"material": "AISI 304"},
                       make_or_buy="make"),
                    _c("frame-feet", "Levelling feet", "frame_structure", 6, {"load": "1000 kg"}, manufacturer="Elesa+Ganter"),
                ]),
        Station(id="st-control", name="Control cabinet", kind="control", sequence=0,
                function="PLC, drives, power distribution and HMI", components=[
                    _c("plc-cpu", "PLC CPU", "plc", 1, {"family": "SIMATIC S7-1500"}, manufacturer="Siemens",
                       part_number="6ES7515-2AM02-0AB0", criticality="A", recommended_spares=1),
                    _c("servo-drives", "Servo drives", "drive", 4, {"family": "SINAMICS S210"}, manufacturer="Siemens",
                       criticality="A", recommended_spares=1),
                    _c("hmi", "HMI touch panel", "hmi", 1, {"size": "15 in"}, manufacturer="Siemens", criticality="B"),
                    _c("psu", "24 V DC power supply", "electrical", 1, {"current": "20 A"}, manufacturer="Phoenix Contact",
                       criticality="A", recommended_spares=1),
                ]),
        Station(id="st-safety", name="Safety", kind="safety", sequence=0,
                function="Guarding, interlocked doors and emergency stop", components=[
                    _c("safety-relay", "Safety relay", "safety", 1, {"contacts": "3 NO + 1 NC", "supply": "24 V DC"},
                       manufacturer="Pilz", part_number="750104", criticality="A", recommended_spares=1),
                    _c("door-switch", "Interlock door switch", "safety", 4, {"type": "RFID coded"}, manufacturer="Schmersal",
                       criticality="A", recommended_spares=1),
                    _c("guards", "Polycarbonate guards", "guarding", 4, {"thickness": "6 mm"}, make_or_buy="make"),
                ]),
        Station(id="st-pneumatics", name="Compressed air", kind="utility", sequence=0,
                function="Air treatment and valve terminal", components=[
                    _c("air-frl", "Filter regulator unit", "air_treatment", 1, {"port": "G1/2", "filter": "5 um"},
                       manufacturer="Festo", criticality="A"),
                    _c("valve-terminal", "Valve terminal", "pneumatic_valve", 1, {"valves": "8", "bus": "PROFINET"},
                       manufacturer="Festo", criticality="A", recommended_spares=1),
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


def _initial_design(problem: str) -> MachineDesign:
    machine_type, product, process = _process_stations(problem)
    # "300 tablets per minute", "1200 pcs/h", "60 cosmetic tubes per min", "60 pezzi al minuto"
    rate = re.search(
        r"(\d[\d.,]*)\s*((?:[a-z]+\s+){0,3}?[a-z]*)\s*(?:/|\bper\b|\bal\b|\ba\b)\s*(min|h\b|hour|ora)",
        problem.lower(),
    )
    throughput = None
    if rate:
        words = rate.group(2).split()
        unit = "min" if rate.group(3) == "min" else "h"
        throughput = f"{rate.group(1)} {words[-1] if words else product}/{unit}"
    return MachineDesign(
        name=f"{machine_type} (demo)",
        machine_type=machine_type,
        summary=f"Demo design generated offline for: {problem.strip()[:200]}",
        product=product,
        throughput=throughput,
        footprint=None,
        stations=_with_envelopes([*process, *_infrastructure(len(process))]),
        utilities=["400 V 3~ 50 Hz", "6 bar dry compressed air"],
        assumptions=["Generated by the offline demo engine, not by an AI model."],
        open_questions=["What is the required throughput?"] if throughput is None else [],
    )


def _vision_station(seq: int) -> Station:
    return Station(id="st-vision", name="Vision inspection", kind="inspection", sequence=seq,
                   function="Checks presence and integrity of every product", cycle_time_s=None,
                   components=[
                       _c("vision-cam", "Smart camera", "vision", 1, {"resolution": "5 MP"}, manufacturer="Cognex",
                          criticality="B"),
                       _c("vision-light", "Ring light", "vision", 1, {"colour": "red, 625 nm"}, criticality="B",
                          recommended_spares=1),
                   ])


def _refine(design: MachineDesign, request: str) -> DesignUpdate:
    r = request.lower()
    if any(k in r for k in ("vision", "camera", "inspect", "visione", "telecamera")):
        if any(s.id == "st-vision" for s in design.stations):
            return DesignUpdate(reply="The machine already has a vision inspection station.", design=design)
        last_process = max(
            (s.sequence for s in design.stations if s.sequence > 0 and s.id != "st-outfeed"), default=0
        )
        for s in design.stations:
            if s.id == "st-outfeed":
                s.sequence = last_process + 2
        design.stations.extend(_with_envelopes([_vision_station(last_process + 1)]))
        design.stations.sort(key=lambda s: (s.sequence == 0, s.sequence))
        return DesignUpdate(reply="Added a vision inspection station before the outfeed (demo engine).", design=design)
    if any(k in r for k in ("u-shape", "u shape", "u-shaped", "u shaped", "compact", "shorter", "forma a u")):
        design.layout_style = "u_shape"
        return DesignUpdate(reply="Arranged the process stations in a U-shape to shorten the line (demo engine).",
                            design=design)
    if any(k in r for k in ("inline", "in line", "straight", "in linea")):
        design.layout_style = "inline"
        return DesignUpdate(reply="Arranged the process stations in a straight line (demo engine).", design=design)
    return DesignUpdate(
        reply="Demo mode understands only a few requests (e.g. 'add vision inspection', 'make it U-shaped'). "
        "Configure an AI provider to refine the design freely.",
        design=design,
    )


class MockProvider:
    name = "mock"
    model = "demo-engine"

    def structured(
        self, *, system: str, turns: list[Turn], output: type[T], on_progress: ProgressFn | None = None
    ) -> T:
        if output is not DesignUpdate:
            raise LLMError("The demo engine only produces machine designs.")
        if on_progress:
            on_progress(progress_from_text("thinking", "", "Demo engine: matching the request to a template"))
        result = self._answer(turns)
        if on_progress:
            on_progress(progress_from_text("writing", result.model_dump_json()))
        return result  # type: ignore[return-value]

    def _answer(self, turns: list[Turn]) -> DesignUpdate:
        last = turns[-1]["content"]
        current = re.search(r"<current_design>\n(.*)\n</current_design>", last, re.S)
        if current:
            request = re.search(r"<request>\n(.*)\n</request>", last, re.S)
            design = MachineDesign.model_validate(json.loads(current.group(1)))
            return _refine(design, request.group(1) if request else "")
        problem = re.search(r"<problem>\n(.*)\n</problem>", last, re.S)
        design = _initial_design(problem.group(1) if problem else last)
        reply = f"Demo design: {len(design.stations)} stations. Set up an AI provider for real designs."
        return DesignUpdate(reply=reply, design=design)
