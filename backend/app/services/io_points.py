"""Estimated I/O points of a design, derived by rules from component categories.

Shared by the technical documents (I/O list) and the PLC skeleton (variable declarations and
station sequences). The rules are simple estimates and are labelled as such wherever shown.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from app.models import Component, MachineDesign, Station

SIGNAL_TYPES = ("DI", "DO", "AI", "AO", "Safety DI", "Axis", "Fieldbus")


@dataclass(frozen=True)
class IOPoint:
    tag: str            # e.g. "S01.forming-cyl.DI2"
    kind: str           # one of SIGNAL_TYPES
    description: str    # e.g. "end position 2"
    station: Station
    component: Component
    unit: int           # 1-based index when the component quantity is > 1

    @property
    def variable(self) -> str:
        """IEC 61131-3 identifier: letters, digits, single underscores."""
        name = re.sub(r"[^A-Za-z0-9]+", "_", self.tag).strip("_")
        return name if not name[0].isdigit() else f"_{name}"


def _text(component: Component) -> str:
    return " ".join([component.name, *(f"{s.name} {s.value}" for s in component.specs)]).lower()


def signals(component: Component) -> list[tuple[str, str]]:
    """(signal type, description) for ONE unit of the component. Heuristic, per category."""
    text = _text(component)
    c = component.category
    if c == "sensor":
        if any(k in text for k in ("thermocouple", "pt100", "load cell", "analog", "4-20", "pressure transmitter")):
            return [("AI", "measurement")]
        return [("DI", "signal")]
    if c == "pneumatic_actuator":
        return [("DO", "valve coil"), ("DI", "end position 1"), ("DI", "end position 2")]
    if c == "vacuum":
        if "ejector" in text or "generator" in text or "pump" in text:
            return [("DO", "vacuum on"), ("DI", "vacuum switch")]
        return []
    if c == "servo_motor":
        return [("Axis", "servo axis")]
    if c == "linear_motion":
        return [("Axis", "linear axis")] if "axis" in text else []
    if c == "motor":
        return [("DO", "run"), ("DI", "running / overload")]
    if c in ("heating", "sealing"):
        return [("DO", "heater (SSR)")] if any(k in text for k in ("heat", "kw", "power", "temp")) else []
    if c in ("pump", "dosing"):
        if "gun" in text:
            return [("DO", "dispense")]
        if any(k in text for k in ("tube", "tubing", "brush")):
            return []  # consumables, or driven by a motor listed separately
        return [("DO", "run"), ("DI", "ready / fault")]
    if c == "safety":
        if any(k in text for k in ("door", "interlock", "switch", "e-stop", "emergency", "light curtain", "scanner")):
            return [("Safety DI", "channel A"), ("Safety DI", "channel B")]
        if "relay" in text:
            return [("DI", "safety relay status"), ("DO", "safety relay reset")]
        return []
    if c in ("vision", "printing_marking"):
        if any(k in text for k in ("camera", "printer", "marking", "laser", "inkjet")):
            return [("Fieldbus", "device"), ("DO", "trigger"), ("DI", "result OK")]
        return []
    if c in ("pneumatic_valve", "drive", "hmi", "io_module"):
        if c == "pneumatic_valve" and "terminal" not in text and "island" not in text:
            return [("DO", "valve coil")]
        return [("Fieldbus", "node")]
    if c == "air_treatment":
        return [("DO", "soft-start / dump valve"), ("DI", "pressure switch")]
    if c == "cooling":
        return [("DO", "run"), ("DI", "fault")]
    return []


def station_codes(design: MachineDesign) -> list[tuple[str, Station]]:
    """Flow stations S01, S02… in sequence order, then infrastructure X01, X02…"""
    flow = sorted((s for s in design.stations if s.sequence > 0), key=lambda s: s.sequence)
    infra = [s for s in design.stations if s.sequence <= 0]
    return [(f"S{s.sequence:02d}", s) for s in flow] + [(f"X{i:02d}", s) for i, s in enumerate(infra, start=1)]


def io_points(design: MachineDesign) -> list[IOPoint]:
    points: list[IOPoint] = []
    for code, station in station_codes(design):
        for component in station.components:
            per_unit = signals(component)
            for unit in range(1, component.quantity + 1):
                per_type: Counter[str] = Counter()
                for kind, desc in per_unit:
                    per_type[kind] += 1
                    suffix = f".{unit}" if component.quantity > 1 else ""
                    tag = f"{code}.{component.id}{suffix}.{kind.replace(' ', '')}{per_type[kind]}"
                    points.append(IOPoint(tag, kind, desc, station, component, unit))
    return points


def io_totals(points: list[IOPoint]) -> Counter[str]:
    return Counter(p.kind for p in points)
