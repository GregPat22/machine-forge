"""What changed between two revisions of a design.

Stations and components are matched by their ids, which the AI keeps stable across revisions.
A component that moves to another station is reported as modified ("station: A → B").
"""

from __future__ import annotations

from operator import attrgetter
from typing import Literal

from pydantic import BaseModel

from app.models import Component, MachineDesign, Signals, Station

ChangeKind = Literal["added", "removed", "modified"]

MACHINE_FIELDS = (
    "name", "machine_type", "product.description", "target_rate_text", "footprint", "layout_style", "summary",
)
LIST_FIELDS = ("utilities", "assumptions", "open_questions")
STATION_FIELDS = ("name", "kind", "sequence", "function", "cycle_time_s", "length_mm", "width_mm", "height_mm")
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


class DesignDiff(BaseModel):
    from_revision: int
    to_revision: int
    machine: list[FieldChange]
    lists: list[ListChange]
    stations: list[StationChange]
    components: list[ComponentChange]
    counts: dict[str, int]


def _fmt(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Signals):
        counts = [(k.upper() if k != "axes" else "Axes", n) for k, n in value.model_dump().items() if n]
        return ", ".join(f"{k} {n}" for k, n in counts) or "none"
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


def _components(design: MachineDesign) -> dict[str, tuple[Component, Station]]:
    return {c.id: (c, s) for s in design.stations for c in s.components}


def diff_designs(before: MachineDesign, after: MachineDesign, from_revision: int, to_revision: int) -> DesignDiff:
    machine = _field_changes(before, after, MACHINE_FIELDS)
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
        elif fields := _field_changes(old_st[sid], station, STATION_FIELDS):
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
