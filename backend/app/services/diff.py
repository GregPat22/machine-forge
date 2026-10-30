"""What changed between two revisions of a design.

Stations and components are matched by their ids, which the AI keeps stable across revisions.
A component that moves to another station is reported as modified ("station: A → B").
The timing block compares the two revisions' stored timing results (ADR 0003, 0028).
"""

from __future__ import annotations

from operator import attrgetter
from typing import Literal

from pydantic import BaseModel

from app.engines.timing import StationTiming, TimingResult, TimingWarning
from app.models import Component, MachineDesign, Product, Signals, Station

ChangeKind = Literal["added", "removed", "modified"]

MACHINE_FIELDS = (
    "name", "machine_type", *(f"product.{field}" for field in Product.model_fields),
    "target_rate_text", "footprint", "layout_style", "summary",
)
LIST_FIELDS = ("utilities", "assumptions", "open_questions")
STATION_FIELDS = ("name", "kind", "sequence", "function", "cycle_time_s", "length_mm", "width_mm", "height_mm",
                  "library_ref", "target_cycle_time_s", "placement")
COMPONENT_FIELDS = (
    "name", "category", "quantity", "manufacturer", "part_number", "make_or_buy",
    "wear_part", "criticality", "recommended_spares", "notes", "role", "signals", "motion",
)


class FieldChange(BaseModel):
    field: str
    before: str | None
    after: str | None


class ListChange(BaseModel):
    field: str
    added: list[str]
    removed: list[str]


class StationChange(BaseModel):
    station_id: str
    name: str
    change: ChangeKind
    fields: list[FieldChange] = []


class ComponentChange(BaseModel):
    component_id: str
    name: str
    station: str
    change: ChangeKind
    fields: list[FieldChange] = []


class StationTimingChange(BaseModel):
    """A station whose cycle time, limiting step or warnings differ between the two revisions.

    `None` before (after) when the station did not exist or was not computable.
    """

    station_id: str
    cycle_time_s_before: float | None
    cycle_time_s_after: float | None
    limiting_step_before: str | None
    limiting_step_after: str | None
    warnings_added: list[TimingWarning] = []
    warnings_removed: list[TimingWarning] = []


class TimingDiff(BaseModel):
    stations: list[StationTimingChange]
    # Warnings no station owns (a transport's).
    warnings_added: list[TimingWarning] = []
    warnings_removed: list[TimingWarning] = []


class DesignDiff(BaseModel):
    from_revision: int
    to_revision: int
    machine: list[FieldChange]
    lists: list[ListChange]
    stations: list[StationChange]
    components: list[ComponentChange]
    counts: dict[str, int]
    timing: TimingDiff | None = None


def _fmt(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Signals):
        counts = [(k.upper() if k != "axes" else "Axes", n) for k, n in value.model_dump().items() if n]
        return ", ".join(f"{k} {n}" for k, n in counts) or "none"
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _field_changes(before: object, after: object, fields: tuple[str, ...]) -> list[FieldChange]:
    changes = []
    for field in fields:
        a, b = _fmt(attrgetter(field)(before)), _fmt(attrgetter(field)(after))
        if a != b:
            changes.append(FieldChange(field=field, before=a, after=b))
    return changes


def _specs(component: Component) -> str:
    return "; ".join(f"{s.name}: {s.value}" for s in component.specs)


def _item_changes(before: list, after: list, key: str, prefix: str) -> list[FieldChange]:
    """Match structured items by stable ids (Parameter.name is its key, not a display label)."""
    old = {getattr(item, key): item for item in before}
    new = {getattr(item, key): item for item in after}
    changes = []
    for item_id in dict.fromkeys([*old, *new]):
        path = f"{prefix}.{item_id}"
        if item_id not in old or item_id not in new:
            changes.append(FieldChange(field=path, before=_fmt(old.get(item_id)), after=_fmt(new.get(item_id))))
        else:
            fields = tuple(field for field in type(new[item_id]).model_fields if field != key)
            for change in _field_changes(old[item_id], new[item_id], fields):
                changes.append(change.model_copy(update={"field": f"{path}.{change.field}"}))
    return changes


def _station_changes(before: Station, after: Station) -> list[FieldChange]:
    changes = _field_changes(before, after, STATION_FIELDS)
    for field, key in (("parameters", "name"), ("mechanisms", "id"), ("steps", "id")):
        changes += _item_changes(getattr(before, field), getattr(after, field), key, field)
    return changes


def _components(design: MachineDesign) -> dict[str, tuple[Component, Station]]:
    return {c.id: (c, s) for s in design.stations for c in s.components}


def diff_designs(before: MachineDesign, after: MachineDesign, from_revision: int, to_revision: int) -> DesignDiff:
    machine = _field_changes(before, after, MACHINE_FIELDS)
    machine += _item_changes(before.transports, after.transports, "id", "transports")
    lists = []
    for field in LIST_FIELDS:
        old, new = getattr(before, field), getattr(after, field)
        added, removed = [x for x in new if x not in old], [x for x in old if x not in new]
        if added or removed:
            lists.append(ListChange(field=field, added=added, removed=removed))

    old_st = {s.id: s for s in before.stations}
    new_st = {s.id: s for s in after.stations}
    stations: list[StationChange] = []
    for sid, station in new_st.items():
        if sid not in old_st:
            stations.append(StationChange(station_id=sid, name=station.name, change="added"))
        elif fields := _station_changes(old_st[sid], station):
            stations.append(StationChange(station_id=sid, name=station.name, change="modified", fields=fields))
    stations += [StationChange(station_id=sid, name=s.name, change="removed") for sid, s in old_st.items() if sid not in new_st]

    old_c, new_c = _components(before), _components(after)
    components: list[ComponentChange] = []
    for cid, (comp, station) in new_c.items():
        if cid not in old_c:
            components.append(ComponentChange(component_id=cid, name=comp.name, station=station.name, change="added"))
            continue
        old_comp, old_station = old_c[cid]
        fields = _field_changes(old_comp, comp, COMPONENT_FIELDS)
        if _specs(old_comp) != _specs(comp):
            fields.append(FieldChange(field="specs", before=_specs(old_comp) or None, after=_specs(comp) or None))
        if old_station.id != station.id:
            fields.append(FieldChange(field="station", before=old_station.name, after=station.name))
        if fields:
            components.append(ComponentChange(component_id=cid, name=comp.name, station=station.name,
                                              change="modified", fields=fields))
    components += [
        ComponentChange(component_id=cid, name=c.name, station=s.name, change="removed")
        for cid, (c, s) in old_c.items() if cid not in new_c
    ]

    counts = {
        f"{kind}_{change}": sum(1 for x in items if x.change == change)
        for kind, items in (("stations", stations), ("components", components))
        for change in ("added", "removed", "modified")
    }
    counts["machine_fields"] = len(machine) + len(lists)
    return DesignDiff(from_revision=from_revision, to_revision=to_revision, machine=machine, lists=lists,
                      stations=stations, components=components, counts=counts)


def _warning_key(warning: TimingWarning) -> tuple[str | None, ...]:
    """A warning is the same in both revisions when its code and every id it names are the same."""
    return (warning.code, warning.station_id, warning.step_id, warning.mechanism_id, warning.transport_id,
            warning.row_id)


def _warning_changes(before: list[TimingWarning], after: list[TimingWarning]) -> tuple[list[TimingWarning], ...]:
    old = {_warning_key(w) for w in before}
    new = {_warning_key(w) for w in after}
    return [w for w in after if _warning_key(w) not in old], [w for w in before if _warning_key(w) not in new]


def diff_timing(before: TimingResult, after: TimingResult) -> TimingDiff:
    """Per station: cycle time, limiting step and warnings, before and after. Unchanged stations are left out."""
    old = {s.station_id: s for s in before.stations}
    new = {s.station_id: s for s in after.stations}
    empty = StationTiming(station_id="")
    stations = []
    for sid in dict.fromkeys([*new, *old]):
        a, b = old.get(sid, empty), new.get(sid, empty)
        added, removed = _warning_changes(a.warnings, b.warnings)
        if (a.cycle_time_s, a.limiting_step_id) != (b.cycle_time_s, b.limiting_step_id) or added or removed:
            stations.append(StationTimingChange(
                station_id=sid, cycle_time_s_before=a.cycle_time_s, cycle_time_s_after=b.cycle_time_s,
                limiting_step_before=a.limiting_step_id, limiting_step_after=b.limiting_step_id,
                warnings_added=added, warnings_removed=removed,
            ))
    added, removed = _warning_changes(before.warnings, after.warnings)
    return TimingDiff(stations=stations, warnings_added=added, warnings_removed=removed)
