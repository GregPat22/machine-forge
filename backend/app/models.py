"""Domain model.

`MachineDesign` is the single source of truth: the AI edits it, and every output
(spare-parts catalog, sourcing, and later 3D / PLC / CAD / documents) is derived from it.
The design models are also sent to the LLM as a JSON schema, so they avoid constructs
structured outputs can't express (free-form dicts, numeric bounds, recursion).

Model v2 (schema_version 2, Phase 1). v1 designs are migrated on read, see
`app/migrations/design_v1.py`. `Station.sequence` and `Station.cycle_time_s` are read-only
values derived from the process graph and the steps (ADR 0012): never stored, never in the
schema, never set by the AI.
"""

from __future__ import annotations

import copy
import heapq
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, model_validator
from pydantic.json_schema import SkipJsonSchema

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
# Kinds that are always part of the product flow, connected by transports or not yet.
FLOW_KINDS = frozenset({"process", "transport", "inspection"})

ComponentRole = Literal["actuator", "sensor", "drive", "controller", "tooling", "structure", "consumable"]
TransportKind = Literal["belt", "indexing", "rotary", "pick_place", "gravity"]
MechanismKind = Literal["linear", "rotary"]
StepKind = Literal["motion", "fixed_duration"]
ProductOrientation = Literal["unspecified", "upright", "lying", "on_edge"]

# Read-only values derived from the model (ADR 0012). Not fields: never stored or set.
DERIVED_STATION_VALUES = ("sequence", "cycle_time_s")


class Spec(BaseModel):
    name: str = Field(description="Parameter name, e.g. 'rated torque'")
    value: str = Field(description="Value with unit, e.g. '2.4 Nm'")


class Signals(BaseModel):
    """Control signals of one unit of a component."""

    di: int = Field(default=0, description="Digital inputs")
    do: int = Field(default=0, description="Digital outputs")
    ai: int = Field(default=0, description="Analog inputs")
    ao: int = Field(default=0, description="Analog outputs")
    axes: int = Field(default=0, description="Motion axes driven by a drive")
    fieldbus: int = Field(default=0, description="Fieldbus nodes")


class Product(BaseModel):
    name: str | None = Field(default=None, description="Short product name, e.g. 'blister card of 10 tablets'")
    description: str | None = Field(default=None, description="What the machine processes, free text, display only")
    length_mm: float | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    mass_g: float | None = None
    orientation: ProductOrientation = Field(default="unspecified", description="How the product travels")
    lanes: int | None = Field(default=None, description="Parallel product lanes, null if not known")
    pitch_mm: float | None = Field(default=None, description="Distance between products or carriers, null if none")


class Transport(BaseModel):
    """An edge of the process graph: how products move from one station to the next."""

    id: str = Field(description="Stable slug, unique in the machine, e.g. 'tr-forming-feeding'")
    from_station: str = Field(description="Station id the products leave")
    to_station: str = Field(description="Station id the products reach")
    kind: TransportKind = "belt"
    length_mm: float | None = None
    speed_mm_s: float | None = Field(default=None, description="For continuous transports")
    index_time_s: float | None = Field(default=None, description="For indexing transports")
    buffer_capacity: int | None = Field(default=None, description="Products that can wait on the transport")
    products_per_move: int | None = None
    reject_to: str | None = Field(default=None, description="Station id that receives rejected products, if any")
    reject_rate: float | None = Field(default=None, description="Fraction of products rejected, 0 to 1")


class Parameter(BaseModel):
    name: str = Field(description="Parameter key, e.g. 'stroke'")
    value: float | None = None
    unit: str | None = Field(default=None, description="e.g. 'mm', 's', 'deg'")


class Mechanism(BaseModel):
    """A motion axis of a station. Units: mm for linear, degrees for rotary."""

    id: str = Field(description="Stable slug, unique in the station, e.g. 'm-lift'")
    kind: MechanismKind
    stroke: float | None = Field(default=None, description="mm (linear) or deg (rotary)")
    max_speed: float | None = Field(default=None, description="mm/s or deg/s")
    acceleration: float | None = Field(default=None, description="mm/s2 or deg/s2")
    cam_profile: str | None = Field(default=None, description="Id of a cam profile, unused for now")
    dwell_s: float | None = None


class Step(BaseModel):
    """One ordered operation of a station: a motion of a mechanism, or a fixed-duration process."""

    id: str = Field(description="Stable slug, unique in the station")
    order: int
    kind: StepKind
    mechanism_id: str | None = Field(default=None, description="For motion steps")
    duration_s: float | None = Field(default=None, description="For fixed-duration steps (e.g. a heat-sealing dwell)")
    parallel_group: int | None = Field(default=None, description="Steps with the same group run at the same time")


class Placement(BaseModel):
    x_mm: float
    y_mm: float
    rotation_deg: float


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
    role: ComponentRole | None = Field(default=None, description="What the component does in the machine")
    signals: Signals | None = Field(default=None, description="Control signals per unit, null if not known")
    motion: str | None = Field(default=None, description="Id of the station mechanism this component moves or drives")


class _DesignLink:
    """A station's reference to the design that holds it, for the derived values.

    Not data: it never makes two stations unequal. A copied station is not part of the design
    it was copied from (its sequence raises); a copied design links its own stations again.
    """

    __slots__ = ("design",)

    def __init__(self, design: MachineDesign | None = None) -> None:
        self.design = design

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _DesignLink)

    __hash__ = None  # type: ignore[assignment]

    def __deepcopy__(self, memo: dict[int, Any]) -> _DesignLink:
        return _DesignLink()


class Station(BaseModel):
    id: str = Field(description="Stable slug, unique in the machine, e.g. 'st-feeding'")
    name: str
    kind: StationKind = "process"
    function: str = Field(description="What this station does to the product")
    length_mm: float | None = Field(default=None, description="Approximate envelope along the product flow, mm")
    width_mm: float | None = Field(default=None, description="Approximate envelope across the flow, mm")
    height_mm: float | None = Field(default=None, description="Approximate envelope height from the floor, mm")
    components: list[Component] = Field(default_factory=list)
    library_ref: str | None = Field(default=None, description="Library module id; null for a custom station")
    parameters: list[Parameter] = Field(default_factory=list)
    mechanisms: list[Mechanism] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    target_cycle_time_s: float | None = Field(default=None, description="Required seconds per cycle, if known")
    # Coordinates come from the layout, never from the AI (rule 3): kept out of the JSON schema.
    placement: SkipJsonSchema[Placement | None] = None

    _link: _DesignLink = PrivateAttr(default_factory=_DesignLink)

    @model_validator(mode="before")
    @classmethod
    def _reject_derived_values(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for name in DERIVED_STATION_VALUES:
                if name in data:
                    raise ValueError(f"{name} is derived from the model and cannot be set (ADR 0012)")
        return data

    @property
    def sequence(self) -> int:
        """Position along the process graph from the entry station (1, 2, ...); 0 outside it."""
        design = self._link.design
        if design is None or not any(s is self for s in design.stations):
            raise RuntimeError(f"Station {self.id} is not part of a MachineDesign: its sequence is undefined")
        return design.process_order().get(self.id, 0)

    @property
    def cycle_time_s(self) -> float | None:
        """Sum of the steps when every step is fixed-duration, known and not parallel; else null.

        Motion steps get a duration from the Phase 2 timing engine; until then the cycle is unknown.
        """
        steps = sorted(self.steps, key=lambda s: s.order)
        if not steps or any(
            s.kind != "fixed_duration" or s.duration_s is None or s.parallel_group is not None for s in steps
        ):
            return None
        return sum(s.duration_s for s in steps if s.duration_s is not None)


class MachineDesign(BaseModel):
    name: str
    machine_type: str = Field(description="e.g. 'Thermoforming blister packaging machine'")
    summary: str
    product: Product = Field(default_factory=Product)
    target_rate_text: str | None = Field(
        default=None, description="Required output as the engineer stated it, e.g. '300 blisters/min'; display only"
    )
    footprint: str | None = Field(default=None, description="e.g. '6.5 m x 1.8 m'")
    layout_style: Literal["inline", "u_shape"] = Field(
        default="inline",
        description="'inline': process stations in a straight line; 'u_shape': two rows, the flow turns back",
    )
    stations: list[Station] = Field(default_factory=list)
    transports: list[Transport] = Field(
        default_factory=list,
        description="Process graph: one transport per product move between two stations, in flow direction",
    )
    utilities: list[str] = Field(default_factory=list, description="e.g. '400 V 3~ 50 Hz', '6 bar dry air'")
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    # Bookkeeping written by code, not by the AI: kept out of the JSON schema.
    schema_version: SkipJsonSchema[Literal[2]] = 2

    @model_validator(mode="after")
    def _link_stations(self) -> MachineDesign:
        self._relink()
        self.process_order()  # a cyclic graph is not a valid design
        return self

    def _relink(self) -> None:
        # A new link object each time: a shallow copy of a station shares the old one.
        for station in self.stations:
            station._link = _DesignLink(self)

    # Every copy gets stations of its own, linked to it, so its derived values follow its own graph.
    def __copy__(self) -> MachineDesign:
        copied = super().__copy__()
        copied.stations = [copy.copy(s) for s in self.stations]
        copied._relink()
        return copied

    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> MachineDesign:
        copied = super().__deepcopy__(memo)
        copied._relink()
        return copied

    def model_copy(self, *, update: dict[str, Any] | None = None, deep: bool = False) -> MachineDesign:
        copied = super().model_copy(update=update, deep=deep)
        if update and "stations" in update:  # stations passed in may belong to another design
            copied.stations = [copy.copy(s) for s in copied.stations]
        copied._relink()
        return copied

    def process_order(self) -> dict[str, int]:
        """Position (1, 2, ...) of every node of the process graph, in flow order.

        Nodes are the flow stations (`FLOW_KINDS`), every station a transport connects, and every
        reject destination. Order is topological (Kahn) over the transports; reject branches leave
        the line and do not take part (so a rework branch back upstream is not a cycle). Ties:
        stations connected by a transport first, then flow stations not connected yet and reject
        destinations, each group by its place in `stations`; ids named by a transport but missing
        from `stations` follow in order of appearance. Raises ValueError if the transports form a cycle.
        """
        first_index: dict[str, int] = {}
        for i, station in enumerate(self.stations):
            first_index.setdefault(station.id, i)
        edges = [(t.from_station, t.to_station) for t in self.transports]
        rejects = [t.reject_to for t in self.transports if t.reject_to is not None]

        connected = {node for edge in edges for node in edge}
        rank: dict[str, tuple[bool, int]] = {
            s.id: (s.id not in connected, first_index[s.id]) for s in self.stations if s.kind in FLOW_KINDS
        }
        for node in [n for edge in edges for n in edge] + rejects:
            if node not in rank:
                rank[node] = (node not in connected, first_index.get(node, len(self.stations) + len(rank)))
        successors: dict[str, list[str]] = {node: [] for node in rank}
        indegree = dict.fromkeys(rank, 0)
        for a, b in edges:
            successors[a].append(b)
            indegree[b] += 1

        ready = [(rank[n], n) for n, d in indegree.items() if d == 0]
        heapq.heapify(ready)
        order: dict[str, int] = {}
        while ready:
            _, node = heapq.heappop(ready)
            order[node] = len(order) + 1
            for nxt in successors[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    heapq.heappush(ready, (rank[nxt], nxt))
        if len(order) < len(rank):
            stuck = sorted(n for n in rank if n not in order)
            raise ValueError(f"The process graph has a cycle through {', '.join(stuck)}")
        return order


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
