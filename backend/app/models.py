"""Domain model.

`MachineDesign` is the single source of truth: the AI edits it, and every output
(spare-parts catalog, sourcing, and later 3D / PLC / CAD / documents) is derived from it.
The design models are also sent to the LLM as a JSON schema, so they avoid constructs
structured outputs can't express (free-form dicts, numeric bounds, recursion).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ComponentCategory = Literal[
    "servo_motor",
    "motor",
    "gearbox",
    "drive",
    "plc",
    "io_module",
    "hmi",
    "safety",
    "sensor",
    "vision",
    "pneumatic_actuator",
    "pneumatic_valve",
    "air_treatment",
    "vacuum",
    "linear_motion",
    "bearing",
    "transmission",
    "conveyor",
    "heating",
    "cooling",
    "pump",
    "dosing",
    "cutting",
    "sealing",
    "printing_marking",
    "electrical",
    "frame_structure",
    "guarding",
    "custom_part",
    "other",
]

StationKind = Literal["process", "transport", "inspection", "control", "frame", "safety", "utility"]


class Spec(BaseModel):
    name: str = Field(description="Parameter name, e.g. 'rated torque'")
    value: str = Field(description="Value with unit, e.g. '2.4 Nm'")


class Component(BaseModel):
    id: str = Field(description="Stable slug, unique in the machine, kept across revisions, e.g. 'feed-servo-1'")
    name: str
    category: ComponentCategory
    quantity: int = Field(description="Units used in this station (>= 1)")
    specs: list[Spec] = Field(default_factory=list)
    manufacturer: str | None = Field(default=None, description="Suggested manufacturer, null if no clear choice")
    part_number: str | None = Field(
        default=None, description="Manufacturer part number; null unless it is a real, existing part"
    )
    make_or_buy: Literal["buy", "make"] = Field(
        default="buy", description="'make' for custom machined/fabricated parts, 'buy' for catalog parts"
    )
    wear_part: bool = Field(default=False, description="True if it wears in normal operation")
    criticality: Literal["A", "B", "C"] = Field(
        default="C", description="A = failure stops the machine, B = degrades it, C = minor"
    )
    recommended_spares: int = Field(default=0, description="Units to keep in stock as spares")
    notes: str | None = None


class Station(BaseModel):
    id: str = Field(description="Stable slug, unique in the machine, e.g. 'st-feeding'")
    name: str
    kind: StationKind = "process"
    sequence: int = Field(description="Order along the product flow; infrastructure stations use 0")
    function: str = Field(description="What this station does to the product")
    cycle_time_s: float | None = Field(default=None, description="Seconds per cycle, if known")
    length_mm: float | None = Field(default=None, description="Approximate envelope along the product flow, mm")
    width_mm: float | None = Field(default=None, description="Approximate envelope across the flow, mm")
    height_mm: float | None = Field(default=None, description="Approximate envelope height from the floor, mm")
    components: list[Component] = Field(default_factory=list)


class MachineDesign(BaseModel):
    name: str
    machine_type: str = Field(description="e.g. 'Thermoforming blister packaging machine'")
    summary: str
    product: str = Field(description="What the machine processes")
    throughput: str | None = Field(default=None, description="e.g. '300 blisters/min'")
    footprint: str | None = Field(default=None, description="e.g. '6.5 m x 1.8 m'")
    layout_style: Literal["inline", "u_shape"] = Field(
        default="inline",
        description="'inline': process stations in a straight line; 'u_shape': two rows, the flow turns back",
    )
    stations: list[Station] = Field(default_factory=list)
    utilities: list[str] = Field(default_factory=list, description="e.g. '400 V 3~ 50 Hz', '6 bar dry air'")
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class DesignUpdate(BaseModel):
    """What the AI returns on every turn: a reply to the user and the full updated design."""

    reply: str = Field(description="Short message to the engineer: what changed and why, or what you need to know")
    design: MachineDesign


# --- Persistence / API shapes -------------------------------------------------------------


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    revision: int | None = None
    created_at: datetime


class Revision(BaseModel):
    number: int
    prompt: str
    reply: str
    design: MachineDesign
    schema_version: int = Field(default=1, description="Version of the MachineDesign schema this revision was written with")
    created_at: datetime


class ProjectSummary(BaseModel):
    id: str
    name: str
    problem: str
    latest_revision: int
    created_at: datetime
    updated_at: datetime


class Project(ProjectSummary):
    messages: list[ChatMessage]
    design: MachineDesign


# --- Spare parts catalog & sourcing ---------------------------------------------------------


class SparePart(BaseModel):
    item: int
    key: str = Field(description="Grouping key: manufacturer+part number, or component id")
    name: str
    category: ComponentCategory
    specs: list[Spec]
    manufacturer: str | None
    part_number: str | None
    make_or_buy: Literal["buy", "make"]
    quantity_in_machine: int
    used_in: list[str] = Field(description="Station names")
    component_ids: list[str]
    wear_part: bool
    criticality: Literal["A", "B", "C"]
    recommended_spares: int


class PriceListEntry(BaseModel):
    id: int | None = None
    supplier: str
    manufacturer: str | None = None
    part_number: str | None = None
    description: str | None = None
    unit_price: float | None = None
    currency: str = "EUR"
    lead_time_days: int | None = None
    moq: int | None = None
    source_file: str | None = None


class Offer(BaseModel):
    source: str = Field(description="'internal' for your price list, otherwise the connector name")
    supplier: str
    manufacturer: str | None = None
    part_number: str | None = None
    description: str | None = None
    unit_price: float | None = None
    currency: str | None = None
    unit_price_base: float | None = Field(default=None, description="Unit price converted to the base currency")
    moq: int | None = None
    stock: int | None = None
    lead_time_days: int | None = None
    url: str | None = None
    match: Literal["exact", "similar"] = "exact"
    is_current: bool = Field(default=False, description="True if it comes from your own supplier list")
    rating: float | None = Field(default=None, description="Your rating of the supplier, 1-5")
    preferred: bool = False
    score: float | None = None


class SupplierRating(BaseModel):
    name: str
    quality: int | None = Field(default=None, description="1 (poor) to 5 (excellent)")
    delivery: int | None = Field(default=None, description="Delivery reliability, 1 to 5")
    preferred: bool = False
    notes: str | None = None


class SupplierInfo(SupplierRating):
    price_list_items: int = 0


class SourcingLine(BaseModel):
    part: SparePart
    offers: list[Offer]
    current: Offer | None
    best: Offer | None
    savings_base: float | None = Field(
        default=None, description="(current - best) unit price x quantity in machine, base currency"
    )
    note: str | None = None


class SourcingReport(BaseModel):
    project_id: str
    revision: int
    base_currency: str
    lines: list[SourcingLine]
    connectors_used: list[str]
    connector_errors: list[str]
    total_current_base: float | None
    total_best_base: float | None
