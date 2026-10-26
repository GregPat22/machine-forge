"""Patch operations: the AI's edits to a `MachineDesign`, checked by code (Phase 1, ADR 0013).

The AI never sends a whole design. It answers with a `PatchUpdate`: a reply and a list of
`PatchOp`s. `apply_patches` applies them in order to a copy of the design, all or nothing: if any
op is rejected the design is unchanged and every rejected op is reported as a `PatchError`. The
designer sends those errors back to the AI as its next turn (the repair loop, `designer.py`).

`PatchOp` is one flat model, an `op` name plus nullable operands, not a tagged union, because every
structured-output mode accepts it (ADR 0013). Which operands each op needs (`_OPERANDS`) and every
bound on a value are enforced here, in code: the schema sent to the AI has no bounds (rule:
strict-schema compatible). Ops check only what they add or change, so data that was already in the
design (for example a migrated v1 revision) is not judged again.

The AI never sets values the software computes (rule 3): `COMPUTED_FIELDS`, station placement and
the duration of a motion step are rejected with `computed_field`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Literal, get_args

from pydantic import BaseModel, Field

from app.models import (
    Component,
    MachineDesign,
    Mechanism,
    Parameter,
    Product,
    StationKind,
    Station,
    Step,
    Transport,
)

# Error codes, the only values `PatchError.code` takes.
ERROR_CODES: dict[str, str] = {
    "unknown_station": "a station id that does not exist",
    "unknown_component": "a component id that does not exist",
    "unknown_mechanism": "a mechanism id that does not exist in the station",
    "unknown_step": "a step id that does not exist in the station",
    "unknown_transport": "a transport id that does not exist",
    "duplicate_id": "an id that is already used (stations, components, transports: in the machine; "
    "mechanisms, steps: in the station)",
    "missing_operand": "an operand the op needs is null",
    "invalid_value": "a value outside its bound (the message names value and bound), a malformed id, "
    "an empty text, or an operand the op does not use",
    "computed_field": "a value the software computes (rule 3)",
    "graph_cycle": "a transport that would close a loop in the process graph",
    "orphan_transport": "removing a station that transports still connect",
    "unknown_op": "an op name with no handler",
}
ErrorCode = Literal[
    "unknown_station", "unknown_component", "unknown_mechanism", "unknown_step", "unknown_transport",
    "duplicate_id", "missing_operand", "invalid_value", "computed_field", "graph_cycle", "orphan_transport",
    "unknown_op",
]

PatchOpKind = Literal[
    "add_station", "remove_station", "set_param", "add_component", "remove_component", "replace_component",
    "add_mechanism", "set_mechanism", "add_step", "remove_step", "connect", "disconnect", "set_product",
    "set_utility", "add_assumption", "add_open_question",
]

# Written by code, never by a patch (rule 3, ADR 0012): derived values, coordinates, bookkeeping,
# and the footprint, which the layout computes from the stations.
COMPUTED_FIELDS = frozenset({"sequence", "cycle_time_s", "placement", "schema_version", "footprint"})


class PatchOp(BaseModel):
    """One edit of the design. Fill the operands the op uses and leave every other one null.

    add_station: station (complete, with its components, mechanisms and steps). remove_station:
    station_id (disconnect its transports first). set_param: name and value or text; with
    station_id it sets that station's field (name, function, kind, library_ref, length_mm,
    width_mm, height_mm, target_cycle_time_s) or, for any other name, the station parameter
    `name` (value, unit); without station_id it sets a machine field (name, machine_type, summary,
    target_rate_text, layout_style). add_component: station_id, component. remove_component:
    component_id. replace_component: component_id, component (same id). add_mechanism and set_mechanism
    (replaces the mechanism with the same id): station_id, mechanism. add_step: station_id, step.
    remove_step: station_id, step_id. connect: transport. disconnect: transport_id. set_product:
    product (replaces it). set_utility: items (replaces the utility list). add_assumption and
    add_open_question: text.
    """

    op: PatchOpKind
    station_id: str | None = Field(default=None, description="Station the op works on")
    component_id: str | None = Field(default=None, description="Component to remove or replace")
    step_id: str | None = Field(default=None, description="Step to remove")
    transport_id: str | None = Field(default=None, description="Transport to disconnect")
    name: str | None = Field(default=None, description="set_param: the field or parameter to set")
    value: float | None = Field(default=None, description="set_param: numeric value, null for unknown")
    text: str | None = Field(default=None, description="set_param text value; assumption or open question text")
    unit: str | None = Field(default=None, description="set_param: unit of a station parameter")
    items: list[str] | None = Field(default=None, description="set_utility: the complete utility list")
    station: Station | None = None
    component: Component | None = None
    mechanism: Mechanism | None = None
    step: Step | None = None
    transport: Transport | None = None
    product: Product | None = None


class PatchUpdate(BaseModel):
    """What the AI returns on every turn: a reply to the engineer and the edits to the design."""

    reply: str = Field(description="Short message to the engineer: what changed and why, or what you need to know")
    patches: list[PatchOp] = Field(description="Edits applied in order to the current design; empty for no change")


class PatchError(BaseModel):
    index: int | None = Field(description="Position of the rejected op in the list; null for the answer as a whole")
    code: ErrorCode
    message: str


@dataclass(frozen=True)
class PatchResult:
    design: MachineDesign | None  # None when any op was rejected
    errors: list[PatchError]

    @property
    def ok(self) -> bool:
        return not self.errors


def empty_design() -> MachineDesign:
    """The design the first turn edits: the AI's patches give it a name, a type and a summary."""
    return MachineDesign(name="", machine_type="", summary="")


def apply_patches(design: MachineDesign, patches: list[PatchOp]) -> PatchResult:
    """Apply `patches` in order to a copy of `design`; all of them, or none and every error."""
    work = design.model_copy(deep=True)
    errors: list[PatchError] = []
    for index, op in enumerate(patches):
        for code, message in _apply(work, op):
            errors.append(PatchError(index=index, code=code, message=message))  # type: ignore[arg-type]
    if errors:
        return PatchResult(design=None, errors=errors)
    # Validated again from plain data: a fresh design whose stations are linked to it.
    return PatchResult(design=MachineDesign.model_validate(work.model_dump()), errors=[])


# --- Dispatch --------------------------------------------------------------------------------

Issue = tuple[str, str]  # (error code, message)

_OPERAND_FIELDS = tuple(f for f in PatchOp.model_fields if f != "op")
# op -> (required operands, optional operands). Every other operand must be null.
_OPERANDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "add_station": (("station",), ()),
    "remove_station": (("station_id",), ()),
    "set_param": (("name",), ("station_id", "value", "text", "unit")),
    "add_component": (("station_id", "component"), ()),
    "remove_component": (("component_id",), ()),
    "replace_component": (("component_id", "component"), ()),
    "add_mechanism": (("station_id", "mechanism"), ()),
    "set_mechanism": (("station_id", "mechanism"), ()),
    "add_step": (("station_id", "step"), ()),
    "remove_step": (("station_id", "step_id"), ()),
    "connect": (("transport",), ()),
    "disconnect": (("transport_id",), ()),
    "set_product": (("product",), ()),
    "set_utility": (("items",), ()),
    "add_assumption": (("text",), ()),
    "add_open_question": (("text",), ()),
}


def _apply(design: MachineDesign, op: PatchOp) -> list[Issue]:
    """Apply one op to `design` in place, or leave it untouched and return why not."""
    handler = _HANDLERS.get(op.op)
    if handler is None:
        return [("unknown_op", f"unknown operation '{op.op}'")]
    required, optional = _OPERANDS[op.op]
    issues: list[Issue] = []
    missing = [f for f in required if getattr(op, f) is None]
    if missing:
        issues.append(("missing_operand", f"{op.op} needs " + ", ".join(f"'{f}'" for f in missing)))
    for f in _OPERAND_FIELDS:
        if f not in required and f not in optional and getattr(op, f) is not None:
            issues.append(("invalid_value", f"{op.op} does not use '{f}'; leave it null"))
    return issues or handler(design, op)


# --- Checks shared by the ops ------------------------------------------------------------------

_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

_BOUNDS: dict[str, Callable[[float], bool]] = {
    "greater than 0": lambda v: v > 0,
    "at least 1": lambda v: v >= 1,
    "at least 0": lambda v: v >= 0,
    "between 0 and 1": lambda v: 0 <= v <= 1,
}


def _bound(issues: list[Issue], where: str, field: str, value: float | None, limit: str) -> None:
    if value is None:
        return
    if not math.isfinite(value):
        issues.append(("invalid_value", f"{where} {field} is {value!r}; it must be a finite number"))
    elif not _BOUNDS[limit](value):
        issues.append(("invalid_value", f"{where} {field} is {value!r}; it must be {limit}"))


def _new_id(issues: list[Issue], kind: str, new_id: str, taken: set[str], scope: str = "") -> None:
    if not _SLUG.fullmatch(new_id):
        issues.append(("invalid_value", f"{kind} id '{new_id}' must be a lowercase slug "
                                        "(letters, digits and single hyphens, e.g. 'st-feeding')"))
    elif new_id in taken:
        issues.append(("duplicate_id", f"{kind} id '{new_id}' is already used{scope}"))


def _not_empty(issues: list[Issue], where: str, field: str, value: str | None) -> None:
    if value is not None and not value.strip():
        issues.append(("invalid_value", f"{where} {field} cannot be empty"))


def _find_station(design: MachineDesign, station_id: str, issues: list[Issue]) -> Station | None:
    station = next((s for s in design.stations if s.id == station_id), None)
    if station is None:
        issues.append(("unknown_station", f"station '{station_id}' does not exist"))
    return station


def _component_ids(design: MachineDesign) -> set[str]:
    return {c.id for s in design.stations for c in s.components}


def _check_component(issues: list[Issue], component: Component, station: Station, taken: set[str]) -> None:
    where = f"component '{component.id}'"
    _new_id(issues, "component", component.id, taken)
    _not_empty(issues, where, "name", component.name)
    _bound(issues, where, "quantity", component.quantity, "at least 1")
    _bound(issues, where, "recommended_spares", component.recommended_spares, "at least 0")
    if component.signals is not None:
        for field, count in component.signals:
            _bound(issues, where, f"signals.{field}", count, "at least 0")
    if component.motion is not None and component.motion not in {m.id for m in station.mechanisms}:
        issues.append(("unknown_mechanism", f"{where}: station '{station.id}' has no mechanism '{component.motion}'"))


def _check_mechanism_values(issues: list[Issue], mechanism: Mechanism) -> None:
    where = f"mechanism '{mechanism.id}'"
    for field in ("stroke", "max_speed", "acceleration"):
        _bound(issues, where, field, getattr(mechanism, field), "greater than 0")
    _bound(issues, where, "dwell_s", mechanism.dwell_s, "at least 0")


def _check_step(issues: list[Issue], step: Step, station: Station, taken: set[str]) -> None:
    where = f"step '{step.id}'"
    _new_id(issues, "step", step.id, taken, f" in station '{station.id}'")
    _bound(issues, where, "order", step.order, "at least 1")
    if step.kind == "motion":
        if step.duration_s is not None:
            issues.append(("computed_field", f"{where} is a motion step: its duration is computed, leave duration_s null"))
        if step.mechanism_id is None:
            issues.append(("missing_operand", f"{where} is a motion step and needs mechanism_id"))
        elif step.mechanism_id not in {m.id for m in station.mechanisms}:
            issues.append(("unknown_mechanism", f"{where}: station '{station.id}' has no mechanism '{step.mechanism_id}'"))
    else:
        if step.mechanism_id is not None:
            issues.append(("invalid_value", f"{where} is a fixed-duration step; leave mechanism_id null"))
        _bound(issues, where, "duration_s", step.duration_s, "greater than 0")


def _check_parameter_name(issues: list[Issue], where: str, name: str) -> None:
    if name in COMPUTED_FIELDS:
        issues.append(("computed_field", f"{name} is computed by the software and cannot be set"))
    elif name in Station.model_fields:
        issues.append(("invalid_value", f"{where} parameter '{name}' is a station field; set the field instead"))
    elif not name.strip():
        issues.append(("invalid_value", f"{where} parameter name cannot be empty"))
    elif name != name.strip():
        issues.append(("invalid_value", f"{where} parameter name '{name}' has leading or trailing spaces"))


# --- Ops ---------------------------------------------------------------------------------------


def _add_station(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.station is not None
    station = op.station
    where = f"station '{station.id}'"
    issues: list[Issue] = []
    _new_id(issues, "station", station.id, {s.id for s in design.stations})
    if station.placement is not None:
        issues.append(("computed_field", f"{where} placement comes from the layout and cannot be set"))
    _not_empty(issues, where, "name", station.name)
    _not_empty(issues, where, "function", station.function)
    for field in ("length_mm", "width_mm", "height_mm", "target_cycle_time_s"):
        _bound(issues, where, field, getattr(station, field), "greater than 0")
    parameter_names: set[str] = set()
    for parameter in station.parameters:
        _check_parameter_name(issues, where, parameter.name)
        if parameter.name in parameter_names:
            issues.append(("duplicate_id", f"{where} parameter '{parameter.name}' is listed twice"))
        parameter_names.add(parameter.name)
        if parameter.value is not None and not math.isfinite(parameter.value):
            issues.append(("invalid_value", f"{where} parameter '{parameter.name}' is {parameter.value!r}; "
                                            "it must be a finite number"))
    mechanism_ids: set[str] = set()
    for mechanism in station.mechanisms:
        _new_id(issues, "mechanism", mechanism.id, mechanism_ids, f" in station '{station.id}'")
        _check_mechanism_values(issues, mechanism)
        mechanism_ids.add(mechanism.id)
    component_ids = _component_ids(design)
    for component in station.components:
        _check_component(issues, component, station, component_ids)
        component_ids.add(component.id)
    step_ids: set[str] = set()
    for step in station.steps:
        _check_step(issues, step, station, step_ids)
        step_ids.add(step.id)
    if not issues:
        design.stations.append(station.model_copy(deep=True))
    return issues


def _remove_station(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.station_id is not None
    issues: list[Issue] = []
    station = _find_station(design, op.station_id, issues)
    if station is None:
        return issues
    users = [t.id for t in design.transports if op.station_id in (t.from_station, t.to_station, t.reject_to)]
    if users:
        noun, pronoun = ("transport", "it") if len(users) == 1 else ("transports", "them")
        return [("orphan_transport", f"station '{station.id}' is still connected by {noun} {', '.join(users)}; "
                                     f"disconnect {pronoun} first")]
    design.stations.remove(station)
    return []


@dataclass(frozen=True)
class _Field:
    """A design or station field that set_param can set."""

    kind: Literal["text", "optional_text", "number", "choice"]
    choices: tuple[str, ...] = ()


_MACHINE_FIELDS = {
    "name": _Field("text"),
    "machine_type": _Field("text"),
    "summary": _Field("text"),
    "target_rate_text": _Field("optional_text"),
    "layout_style": _Field("choice", ("inline", "u_shape")),
}
_STATION_FIELDS = {
    "name": _Field("text"),
    "function": _Field("text"),
    "kind": _Field("choice", get_args(StationKind)),
    "library_ref": _Field("optional_text"),
    "length_mm": _Field("number"),
    "width_mm": _Field("number"),
    "height_mm": _Field("number"),
    "target_cycle_time_s": _Field("number"),
}


def _set_param(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.name is not None
    name = op.name
    if name in COMPUTED_FIELDS:
        return [("computed_field", f"{name} is computed by the software and cannot be set")]
    if op.value is not None and op.text is not None:
        return [("invalid_value", "set_param takes either value or text, not both")]
    issues: list[Issue] = []
    if op.station_id is None:
        target: MachineDesign | Station = design
        where, fields = "machine", _MACHINE_FIELDS
    else:
        station = _find_station(design, op.station_id, issues)
        if station is None:
            return issues
        target, where, fields = station, f"station '{station.id}'", _STATION_FIELDS

    spec = fields.get(name)
    if spec is None:
        if name == "id":
            return [("invalid_value", f"{where} id cannot be changed; add a new item instead")]
        if name in type(target).model_fields:
            return [("invalid_value", f"{where} {name} cannot be set with set_param; use its own operations")]
        if isinstance(target, MachineDesign):
            return [("invalid_value", f"the machine has no field '{name}' that set_param can set; "
                                      f"it can set: {', '.join(sorted(_MACHINE_FIELDS))}")]
        return _set_station_parameter(target, op)

    if op.unit is not None:
        issues.append(("invalid_value", f"{where} {name} has a fixed unit; leave unit null"))
    if spec.kind == "number":
        if op.text is not None:
            issues.append(("invalid_value", f"{where} {name} takes a number in value, not text"))
        _bound(issues, where, name, op.value, "greater than 0")
        new_value: object = op.value
    else:
        if op.value is not None:
            issues.append(("invalid_value", f"{where} {name} takes text, not a number"))
        text = op.text.strip() if op.text is not None else None
        if spec.kind == "optional_text":
            new_value = text or None
        elif not text:
            issues.append(("missing_operand", f"set_param of {where} {name} needs 'text'"))
        elif spec.kind == "choice" and text not in spec.choices:
            issues.append(("invalid_value", f"{where} {name} is '{text}'; it must be one of: {', '.join(spec.choices)}"))
        new_value = text
    if not issues:
        setattr(target, name, new_value)
    return issues


def _set_station_parameter(station: Station, op: PatchOp) -> list[Issue]:
    assert op.name is not None
    where = f"station '{station.id}'"
    issues: list[Issue] = []
    _check_parameter_name(issues, where, op.name)
    if op.text is not None:
        issues.append(("invalid_value", f"{where} parameter '{op.name}' takes a number in value, not text"))
    if op.value is not None and not math.isfinite(op.value):
        issues.append(("invalid_value", f"{where} parameter '{op.name}' is {op.value!r}; it must be a finite number"))
    if issues:
        return issues
    existing = next((p for p in station.parameters if p.name == op.name), None)
    if existing is None:
        station.parameters.append(Parameter(name=op.name, value=op.value, unit=op.unit))
    else:
        existing.value, existing.unit = op.value, op.unit
    return []


def _add_component(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.station_id is not None and op.component is not None
    issues: list[Issue] = []
    station = _find_station(design, op.station_id, issues)
    if station is None:
        return issues
    _check_component(issues, op.component, station, _component_ids(design))
    if not issues:
        station.components.append(op.component.model_copy(deep=True))
    return issues


def _find_component(design: MachineDesign, component_id: str) -> tuple[Station, int] | None:
    for station in design.stations:
        for i, component in enumerate(station.components):
            if component.id == component_id:
                return station, i
    return None


def _remove_component(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.component_id is not None
    found = _find_component(design, op.component_id)
    if found is None:
        return [("unknown_component", f"component '{op.component_id}' does not exist")]
    station, i = found
    del station.components[i]
    return []


def _replace_component(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.component_id is not None and op.component is not None
    found = _find_component(design, op.component_id)
    if found is None:
        return [("unknown_component", f"component '{op.component_id}' does not exist")]
    if op.component.id != op.component_id:
        return [("invalid_value", f"replace_component keeps the id '{op.component_id}'; "
                                  "to use a new id, remove the component and add a new one")]
    station, i = found
    issues: list[Issue] = []
    _check_component(issues, op.component, station, _component_ids(design) - {op.component_id})
    if not issues:
        station.components[i] = op.component.model_copy(deep=True)
    return issues


def _add_mechanism(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.station_id is not None and op.mechanism is not None
    issues: list[Issue] = []
    station = _find_station(design, op.station_id, issues)
    if station is None:
        return issues
    _new_id(issues, "mechanism", op.mechanism.id, {m.id for m in station.mechanisms}, f" in station '{station.id}'")
    _check_mechanism_values(issues, op.mechanism)
    if not issues:
        station.mechanisms.append(op.mechanism.model_copy(deep=True))
    return issues


def _set_mechanism(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.station_id is not None and op.mechanism is not None
    issues: list[Issue] = []
    station = _find_station(design, op.station_id, issues)
    if station is None:
        return issues
    index = next((i for i, m in enumerate(station.mechanisms) if m.id == op.mechanism.id), None)
    if index is None:
        return [("unknown_mechanism", f"station '{station.id}' has no mechanism '{op.mechanism.id}'")]
    _check_mechanism_values(issues, op.mechanism)
    if not issues:
        station.mechanisms[index] = op.mechanism.model_copy(deep=True)
    return issues


def _add_step(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.station_id is not None and op.step is not None
    issues: list[Issue] = []
    station = _find_station(design, op.station_id, issues)
    if station is None:
        return issues
    _check_step(issues, op.step, station, {s.id for s in station.steps})
    if not issues:
        station.steps.append(op.step.model_copy(deep=True))
    return issues


def _remove_step(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.station_id is not None and op.step_id is not None
    issues: list[Issue] = []
    station = _find_station(design, op.station_id, issues)
    if station is None:
        return issues
    step = next((s for s in station.steps if s.id == op.step_id), None)
    if step is None:
        return [("unknown_step", f"station '{station.id}' has no step '{op.step_id}'")]
    station.steps.remove(step)
    return []


def _connect(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.transport is not None
    transport = op.transport
    where = f"transport '{transport.id}'"
    issues: list[Issue] = []
    _new_id(issues, "transport", transport.id, {t.id for t in design.transports})
    station_ids = {s.id for s in design.stations}
    for ref in (transport.from_station, transport.to_station, transport.reject_to):
        if ref is not None and ref not in station_ids:
            issues.append(("unknown_station", f"{where}: station '{ref}' does not exist"))
    if transport.from_station == transport.to_station:
        issues.append(("invalid_value", f"{where} goes from station '{transport.from_station}' to itself"))
    for field in ("length_mm", "speed_mm_s", "index_time_s"):
        _bound(issues, where, field, getattr(transport, field), "greater than 0")
    _bound(issues, where, "buffer_capacity", transport.buffer_capacity, "at least 0")
    _bound(issues, where, "products_per_move", transport.products_per_move, "at least 1")
    _bound(issues, where, "reject_rate", transport.reject_rate, "between 0 and 1")
    if issues:
        return issues
    design.transports.append(transport.model_copy(deep=True))
    try:
        design.process_order()
    except ValueError as exc:
        design.transports.pop()
        reason = str(exc)
        return [("graph_cycle", f"{where} would close a loop: {reason[:1].lower()}{reason[1:]}")]
    return []


def _disconnect(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.transport_id is not None
    transport = next((t for t in design.transports if t.id == op.transport_id), None)
    if transport is None:
        return [("unknown_transport", f"transport '{op.transport_id}' does not exist")]
    design.transports.remove(transport)
    return []


def _set_product(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.product is not None
    product = op.product
    issues: list[Issue] = []
    for field in ("length_mm", "width_mm", "height_mm", "mass_g"):
        _bound(issues, "product", field, getattr(product, field), "greater than 0")
    _bound(issues, "product", "lanes", product.lanes, "at least 1")
    _bound(issues, "product", "pitch_mm", product.pitch_mm, "greater than 0")
    if not issues:
        design.product = product.model_copy(deep=True)
    return issues


def _set_utility(design: MachineDesign, op: PatchOp) -> list[Issue]:
    assert op.items is not None
    issues: list[Issue] = []
    for i, item in enumerate(op.items):
        _not_empty(issues, "utility", str(i), item)
    if not issues:
        design.utilities = list(op.items)
    return issues


def _add_text(field: Literal["assumptions", "open_questions"]) -> Callable[[MachineDesign, PatchOp], list[Issue]]:
    def handler(design: MachineDesign, op: PatchOp) -> list[Issue]:
        assert op.text is not None
        if not op.text.strip():
            return [("invalid_value", f"{op.op} text cannot be empty")]
        getattr(design, field).append(op.text)
        return []

    return handler


_HANDLERS: dict[str, Callable[[MachineDesign, PatchOp], list[Issue]]] = {
    "add_station": _add_station,
    "remove_station": _remove_station,
    "set_param": _set_param,
    "add_component": _add_component,
    "remove_component": _remove_component,
    "replace_component": _replace_component,
    "add_mechanism": _add_mechanism,
    "set_mechanism": _set_mechanism,
    "add_step": _add_step,
    "remove_step": _remove_step,
    "connect": _connect,
    "disconnect": _disconnect,
    "set_product": _set_product,
    "set_utility": _set_utility,
    "add_assumption": _add_text("assumptions"),
    "add_open_question": _add_text("open_questions"),
}
assert set(_HANDLERS) == set(get_args(PatchOpKind)) == set(_OPERANDS)
