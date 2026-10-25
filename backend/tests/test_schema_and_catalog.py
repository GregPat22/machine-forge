from __future__ import annotations

from typing import Any

from app.llm.mock import _initial_design
from app.models import Component, DesignUpdate, MachineDesign, Station, Transport
from app.schema import strict_schema
from app.services.spare_parts import build_catalog
from tests.conftest import BLISTER_PROBLEM


def _objects(node: Any):
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            yield node
        for value in node.values():
            yield from _objects(value)
    elif isinstance(node, list):
        for item in node:
            yield from _objects(item)


def test_strict_schema_meets_structured_output_rules() -> None:
    schema = strict_schema(DesignUpdate)
    objects = list(_objects(schema))
    assert len(objects) >= 5  # DesignUpdate, MachineDesign, Station, Component, Spec
    for obj in objects:
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])
    text = str(schema)
    for banned in ("'default'", "'minimum'", "'maxLength'"):
        assert banned not in text


def test_catalog_merges_same_part_number_across_stations() -> None:
    relay = dict(category="safety", manufacturer="Pilz", part_number="750104", criticality="B", recommended_spares=1)
    design = MachineDesign(
        name="t", machine_type="t", summary="t",
        stations=[
            Station(id="a", name="A", function="f",
                    components=[Component(id="r1", name="Relay", quantity=1, **relay)]),
            Station(id="b", name="B", function="f",
                    components=[Component(id="r2", name="Relay", quantity=2,
                                          **{**relay, "part_number": "750-104", "criticality": "A"})]),
        ],
        transports=[Transport(id="ab", from_station="a", to_station="b")],
    )
    [part] = build_catalog(design)
    assert part.quantity_in_machine == 3
    assert part.used_in == ["A", "B"]
    assert part.criticality == "A"
    assert part.component_ids == ["r1", "r2"]


def test_demo_design_has_infrastructure_and_throughput() -> None:
    design = _initial_design(BLISTER_PROBLEM)
    ids = {s.id for s in design.stations}
    assert {"st-control", "st-safety", "st-frame"} <= ids
    assert design.target_rate_text == "300 tablets/min"
    catalog = build_catalog(design)
    assert any(p.wear_part and p.recommended_spares > 0 for p in catalog)
