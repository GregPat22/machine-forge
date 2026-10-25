"""MachineDesign v1 (v0.3 and Phase 0) and its migration to v2 (Phase 1 spec, section B).

The v1 classes are a frozen copy of `app/models.py` at commit f93f288. They are used only to
read old revisions; do not edit them. Unknown or missing data stays null: nothing is guessed.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import (
    Component,
    ComponentRole,
    MachineDesign,
    Product,
    Station,
    Step,
    Transport,
)

ComponentCategoryV1 = Literal[
    "servo_motor", "motor", "gearbox", "drive", "plc", "io_module", "hmi", "safety", "sensor", "vision",
    "pneumatic_actuator", "pneumatic_valve", "air_treatment", "vacuum", "linear_motion", "bearing",
    "transmission", "conveyor", "heating", "cooling", "pump", "dosing", "cutting", "sealing",
    "printing_marking", "electrical", "frame_structure", "guarding", "custom_part", "other",
]
StationKindV1 = Literal["process", "transport", "inspection", "control", "frame", "safety", "utility"]


class SpecV1(BaseModel):
    name: str
    value: str


class ComponentV1(BaseModel):
    id: str
    name: str
    category: ComponentCategoryV1
    quantity: int
    specs: list[SpecV1] = Field(default_factory=list)
    manufacturer: str | None = None
    part_number: str | None = None
    make_or_buy: Literal["buy", "make"] = "buy"
    wear_part: bool = False
    criticality: Literal["A", "B", "C"] = "C"
    recommended_spares: int = 0
    notes: str | None = None


class StationV1(BaseModel):
    id: str
    name: str
    kind: StationKindV1 = "process"
    sequence: int
    function: str
    cycle_time_s: float | None = None
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    components: list[ComponentV1] = Field(default_factory=list)


class MachineDesignV1(BaseModel):
    name: str
    machine_type: str
    summary: str
    product: str
    throughput: str | None = None
    footprint: str | None = None
    layout_style: Literal["inline", "u_shape"] = "inline"
    stations: list[StationV1] = Field(default_factory=list)
    utilities: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


# Role of each v1 category. None where the category does not say what the part does in the
# machine (a "vacuum" part is a suction cup or an ejector; a "custom_part" is tooling or
# structure): those components keep role null until the AI or the engineer sets it.
CATEGORY_ROLES: dict[str, ComponentRole | None] = {
    "servo_motor": "actuator",
    "motor": "actuator",
    "gearbox": None,
    "drive": "drive",
    "plc": "controller",
    "io_module": "controller",
    "hmi": None,
    "safety": None,
    "sensor": "sensor",
    "vision": "sensor",
    "pneumatic_actuator": "actuator",
    "pneumatic_valve": "actuator",
    "air_treatment": None,
    "vacuum": None,
    "linear_motion": None,
    "bearing": None,
    "transmission": None,
    "conveyor": None,
    "heating": "actuator",
    "cooling": None,
    "pump": "actuator",
    "dosing": None,
    "cutting": "tooling",
    "sealing": "tooling",
    "printing_marking": None,
    "electrical": None,
    "frame_structure": "structure",
    "guarding": "structure",
    "custom_part": None,
    "other": None,
}

# The one place the current version is defined is the MachineDesign default.
CURRENT_VERSION: int = MachineDesign.model_fields["schema_version"].default


def migrate_design(raw: dict[str, Any], from_version: int) -> MachineDesign:
    """Read a stored design written with `from_version` of the schema as the current model."""
    if from_version == CURRENT_VERSION:
        return MachineDesign.model_validate(raw)
    if from_version != 1:
        raise ValueError(f"Unknown design schema version {from_version}")
    v1 = MachineDesignV1.model_validate(raw)

    # The flow is the stations with sequence > 0, in sequence order (list order breaks ties);
    # consecutive flow stations are joined by a belt whose numbers are unknown. A repeated id
    # (invalid, but seen in AI output) keeps its first place, so the chain never loops.
    ordered = [s.id for _, _, s in sorted((s.sequence, i, s) for i, s in enumerate(v1.stations) if s.sequence > 0)]
    flow = list(dict.fromkeys(ordered))
    transports = [
        Transport(id=f"tr-{a}-{b}", from_station=a, to_station=b, kind="belt") for a, b in zip(flow, flow[1:])
    ]
    return MachineDesign(
        name=v1.name,
        machine_type=v1.machine_type,
        summary=v1.summary,
        product=Product(description=v1.product),
        target_rate_text=v1.throughput,
        footprint=v1.footprint,
        layout_style=v1.layout_style,
        stations=[_station(s) for s in v1.stations],
        transports=transports,
        utilities=v1.utilities,
        assumptions=v1.assumptions,
        open_questions=v1.open_questions,
    )


def _station(s: StationV1) -> Station:
    steps = []
    if s.cycle_time_s is not None:
        steps = [Step(id=f"{s.id}-cycle", order=1, kind="fixed_duration", duration_s=s.cycle_time_s)]
    return Station(
        id=s.id,
        name=s.name,
        kind=s.kind,
        function=s.function,
        length_mm=s.length_mm,
        width_mm=s.width_mm,
        height_mm=s.height_mm,
        components=[Component(**c.model_dump(), role=CATEGORY_ROLES[c.category]) for c in s.components],
        steps=steps,
        target_cycle_time_s=s.cycle_time_s,
    )


def to_v1(design: MachineDesign) -> MachineDesignV1:
    """The v1 view of a design: proves that migration keeps every v1 field (spec section B)."""
    v1_component_fields = set(ComponentV1.model_fields)
    return MachineDesignV1(
        name=design.name,
        machine_type=design.machine_type,
        summary=design.summary,
        product=design.product.description or "",
        throughput=design.target_rate_text,
        footprint=design.footprint,
        layout_style=design.layout_style,
        stations=[
            StationV1(
                id=s.id, name=s.name, kind=s.kind, sequence=s.sequence, function=s.function,
                cycle_time_s=s.cycle_time_s, length_mm=s.length_mm, width_mm=s.width_mm, height_mm=s.height_mm,
                components=[ComponentV1(**c.model_dump(include=v1_component_fields)) for c in s.components],
            )
            for s in design.stations
        ],
        utilities=design.utilities,
        assumptions=design.assumptions,
        open_questions=design.open_questions,
    )
