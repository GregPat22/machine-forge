"""Plausibility bounds: mechanism and transport values against public catalog data (Phase 2, section E).

A pure function over the design and a table already loaded: no I/O (rule 5); the service reads
`backend/data/catalog_bounds.yaml` (`app.services.bounds`). The table's numbers come from
manufacturers' public catalogs, each row citing its source; this module holds none.

A row applies to a mechanism when a component of the same station whose `category` is the row's
`component_category` drives it (`Component.motion` is the mechanism id) and the mechanism's `kind`
is the row's `mechanism_kind`; to a transport when the transport's `kind` is the row's
`transport_kind`. Only these structured fields decide, never a name (rule 1). A mechanism that no
component drives is not checked, and the result lists it. A field with no value is not checked.

A row is active only with a source title, a source URL, and a `min` or a `max`. A value below
`min` or above `max` of an active row gives an `out_of_bounds` warning naming the row and its
source; a value on the bound passes. The design is never corrected. Inactive rows
(`TODO(source)`) give nothing.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engines.timing import BoundsField, TimingWarning
from app.models import ComponentCategory, MachineDesign, MechanismKind, TransportKind

# The model's unit for each field: mechanism fields by mechanism kind, transport fields alone.
MECHANISM_UNITS: dict[str, dict[str, str]] = {
    "stroke": {"linear": "mm", "rotary": "deg"},
    "max_speed": {"linear": "mm/s", "rotary": "deg/s"},
    "acceleration": {"linear": "mm/s2", "rotary": "deg/s2"},
    "jerk": {"linear": "mm/s3", "rotary": "deg/s3"},
}
TRANSPORT_UNITS: dict[str, str] = {"index_time_s": "s", "speed_mm_s": "mm/s"}


class AppliesTo(BaseModel):
    """Exactly one of `component_category` (with `mechanism_kind`) and `transport_kind`."""

    model_config = ConfigDict(extra="forbid")

    component_category: ComponentCategory | None = None
    transport_kind: TransportKind | None = None
    mechanism_kind: MechanismKind | None = None

    @model_validator(mode="after")
    def _one_target(self) -> AppliesTo:
        if (self.component_category is None) == (self.transport_kind is None):
            raise ValueError("a row applies to exactly one of component_category and transport_kind")
        if self.component_category is not None and self.mechanism_kind is None:
            raise ValueError("a component_category row needs mechanism_kind (linear or rotary)")
        if self.transport_kind is not None and self.mechanism_kind is not None:
            raise ValueError("a transport_kind row has no mechanism_kind")
        return self


class BoundsRow(BaseModel):
    """One catalog bound: `field` between `min` and `max`, in the model's `unit`, with its source."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    applies_to: AppliesTo
    field: BoundsField
    unit: str
    min: float | None = None
    max: float | None = None
    as_printed: str | None = None
    source_title: str | None = None
    source_url: str | None = None
    source_page: str | None = None
    accessed: date | None = None

    @model_validator(mode="after")
    def _consistent(self) -> BoundsRow:
        kind = self.applies_to.mechanism_kind
        if self.applies_to.transport_kind is not None:
            if self.field not in TRANSPORT_UNITS:
                raise ValueError(f"row {self.id}: {self.field} is not a transport field")
            unit = TRANSPORT_UNITS[self.field]
        else:
            if self.field not in MECHANISM_UNITS:
                raise ValueError(f"row {self.id}: {self.field} is not a mechanism field")
            assert kind is not None
            unit = MECHANISM_UNITS[self.field][kind]
        if self.unit != unit:
            raise ValueError(f"row {self.id}: the model's unit for {self.field} is {unit}, not {self.unit}")
        for name, value in (("min", self.min), ("max", self.max)):
            if value is not None and not math.isfinite(value):
                raise ValueError(f"row {self.id}: {name} must be finite, got {value!r}")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"row {self.id}: min {self.min} is above max {self.max}")
        return self

    @property
    def active(self) -> bool:
        return bool(self.source_url and self.source_title) and (self.min is not None or self.max is not None)


class BoundsTable(BaseModel):
    """The rows of the bounds file and its `version` (the SHA-256 of the file, set by the loader)."""

    version: str
    rows: list[BoundsRow]

    @model_validator(mode="after")
    def _unique_ids(self) -> BoundsTable:
        ids = [row.id for row in self.rows]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate row ids: {', '.join(duplicates)}")
        return self


class UncheckedMechanism(BaseModel):
    """A mechanism that no component drives, so no row can apply to it."""

    station_id: str
    mechanism_id: str


class BoundsCheck(BaseModel):
    warnings: list[TimingWarning] = []
    unchecked: list[UncheckedMechanism] = []


def check_bounds(design: MachineDesign, table: BoundsTable) -> BoundsCheck:
    """Every mechanism and transport value checked against the active rows that apply to it.

    Order: stations, then their mechanisms, as in the design, then transports; rows in table order.
    """
    active = [row for row in table.rows if row.active]
    result = BoundsCheck()
    for station in design.stations:
        for mechanism in station.mechanisms:
            categories = {c.category for c in station.components if c.motion == mechanism.id}
            if not categories:
                result.unchecked.append(UncheckedMechanism(station_id=station.id, mechanism_id=mechanism.id))
                continue
            for row in active:
                target = row.applies_to
                if target.component_category in categories and target.mechanism_kind == mechanism.kind:
                    warning = _outside(row, getattr(mechanism, row.field))
                    if warning is not None:
                        result.warnings.append(warning.model_copy(
                            update={"station_id": station.id, "mechanism_id": mechanism.id}))
    for transport in design.transports:
        for row in active:
            if row.applies_to.transport_kind == transport.kind:
                warning = _outside(row, getattr(transport, row.field))
                if warning is not None:
                    result.warnings.append(warning.model_copy(update={"transport_id": transport.id}))
    return result


def _outside(row: BoundsRow, value: float | None) -> TimingWarning | None:
    if value is None:
        return None
    bound: Literal["min", "max"]
    if row.min is not None and value < row.min:
        bound, limit = "min", row.min
    elif row.max is not None and value > row.max:
        bound, limit = "max", row.max
    else:
        return None
    return TimingWarning(code="out_of_bounds", value=value, limit=limit, field=row.field, bound=bound,
                         row_id=row.id, source_title=row.source_title, source_url=row.source_url)
