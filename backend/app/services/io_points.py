"""I/O points of a design, from the signals of each component.

Shared by the technical documents (I/O list) and the PLC skeleton (variable declarations and
station sequences). How many signals a component has comes from `Component.signals`; the
category only names them (a cylinder's DO is its valve coil), and the role says whether a safety
device's inputs are safety inputs. Names and free text are never read (rule 1). A component
whose signals are not known gets no points and is listed by `components_without_signals`.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace

from app.models import Component, MachineDesign, Signals, Station

SIGNAL_TYPES = ("DI", "DO", "AI", "AO", "Safety DI", "Axis", "Fieldbus")


@dataclass(frozen=True)
class IOPoint:
    tag: str            # e.g. "S01.forming-cyl.DI2"
    kind: str           # one of SIGNAL_TYPES
    description: str    # e.g. "end position 2"
    station: Station
    component: Component
    unit: int           # 1-based index when the component quantity is > 1
    mechanism: str | None = None  # the station mechanism the component moves (`Component.motion`)
    _variable: str | None = None

    @property
    def variable(self) -> str:
        """IEC 61131-3 identifier: letters, digits, single underscores."""
        if self._variable is not None:
            return self._variable
        name = re.sub(r"[^A-Za-z0-9]+", "_", self.tag).strip("_")
        return name if not name[0].isdigit() else f"_{name}"


# Names of a component's signals, in order, by category. The PLC skeleton recognises these
# descriptions (a valve coil with two end positions is a cylinder step). Signals beyond the list,
# and those of other categories, get a numbered generic name.
_LABELS: dict[str, tuple[tuple[str, str], ...]] = {
    "sensor": (("DI", "signal"), ("AI", "measurement")),
    "pneumatic_actuator": (("DO", "valve coil"), ("DI", "end position 1"), ("DI", "end position 2")),
    "vacuum": (("DO", "vacuum on"), ("DI", "vacuum switch")),
    "servo_motor": (("Axis", "servo axis"),),
    "linear_motion": (("Axis", "linear axis"),),
    "motor": (("DO", "run"), ("DI", "running / overload")),
    "heating": (("DO", "heater (SSR)"),),
    "sealing": (("DO", "heater (SSR)"),),
    "pump": (("DO", "run"), ("DI", "ready / fault")),
    "dosing": (("DO", "dispense"), ("DI", "ready / fault")),
    "vision": (("Fieldbus", "device"), ("DO", "trigger"), ("DI", "result OK")),
    "printing_marking": (("Fieldbus", "device"), ("DO", "trigger"), ("DI", "result OK")),
    "pneumatic_valve": (("DO", "valve coil"), ("Fieldbus", "node")),
    "drive": (("Fieldbus", "node"),),
    "hmi": (("Fieldbus", "node"),),
    "io_module": (("Fieldbus", "node"),),
    "air_treatment": (("DO", "soft-start / dump valve"), ("DI", "pressure switch")),
    "cooling": (("DO", "run"), ("DI", "fault")),
}
# Safety devices: a sensor (door switch, light curtain, e-stop) has two-channel safety inputs; a
# controller (safety relay) reports its status on a plain input and is reset by an output.
_SAFETY_SENSOR_LABELS = (("Safety DI", "channel A"), ("Safety DI", "channel B"))
_SAFETY_CONTROLLER_LABELS = (("DI", "safety relay status"), ("DO", "safety relay reset"))
_GENERIC = {"DI": "input", "DO": "output", "AI": "analog input", "AO": "analog output",
            "Safety DI": "safety channel", "Axis": "axis", "Fieldbus": "node"}


def _counts(component: Component, sig: Signals) -> dict[str, int]:
    di = "Safety DI" if component.category == "safety" and component.role == "sensor" else "DI"
    counts = {di: sig.di, "DO": sig.do, "AI": sig.ai, "AO": sig.ao, "Axis": sig.axes, "Fieldbus": sig.fieldbus}
    return {kind: n for kind, n in counts.items() if n > 0}


def _labels(component: Component) -> tuple[tuple[str, str], ...]:
    if component.category == "safety":
        if component.role == "sensor":
            return _SAFETY_SENSOR_LABELS
        if component.role == "controller":
            return _SAFETY_CONTROLLER_LABELS
        return ()
    return _LABELS.get(component.category, ())


def signals(component: Component) -> list[tuple[str, str]]:
    """(signal type, description) for ONE unit of the component; empty when its signals are unknown."""
    if component.signals is None:
        return []
    left = _counts(component, component.signals)
    out: list[tuple[str, str]] = []
    for kind, label in _labels(component):
        if left.get(kind, 0) > 0:
            out.append((kind, label))
            left[kind] -= 1
    named = Counter(kind for kind, _ in out)
    for kind in SIGNAL_TYPES:
        out += [(kind, f"{_GENERIC[kind]} {named[kind] + n}") for n in range(1, left.get(kind, 0) + 1)]
    return out


def components_without_signals(design: MachineDesign) -> list[tuple[Station, Component]]:
    """Components whose signals are not known: they have no I/O points until someone sets them."""
    return [(s, c) for _, s in station_codes(design) for c in s.components if c.signals is None]


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
                    points.append(IOPoint(tag, kind, desc, station, component, unit, component.motion))
    return _unique_variables(points)


def _unique_variables(points: list[IOPoint]) -> list[IOPoint]:
    """Keep existing identifiers unless punctuation erased a distinction, e.g. motor.1 / motor-1.

    IEC identifiers are case-insensitive. Stable component ids and unit numbers decide which
    point keeps its name, so reordering components cannot reassign their variables.
    """
    groups: dict[str, list[int]] = {}
    for i, point in enumerate(points):
        groups.setdefault(point.variable.casefold(), []).append(i)
    taken = set(groups)
    for indices in groups.values():
        ordered = sorted(indices, key=lambda i: (points[i].component.id, points[i].unit, points[i].tag))
        for i in ordered[1:]:
            suffix = 2
            while (candidate := f"{points[i].variable}_{suffix}").casefold() in taken:
                suffix += 1
            taken.add(candidate.casefold())
            points[i] = replace(points[i], _variable=candidate)
    return points


def io_totals(points: list[IOPoint]) -> Counter[str]:
    return Counter(p.kind for p in points)
