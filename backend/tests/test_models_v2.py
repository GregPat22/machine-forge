"""Model v2: `sequence` and `cycle_time_s` are read-only values derived from the model (ADR 0012)."""

from __future__ import annotations

import copy as copy_module
import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.engines.timing import design_timing
from app.llm.mock import SCENARIOS, demo_design
from app.models import MachineDesign, Product, Station, Step, Transport
from app.schema import strict_schema
from app.services.patch import PatchUpdate
from app.storage import Storage

DERIVED = ("sequence", "cycle_time_s")


def _station(sid: str, kind: str = "process", steps: list[Step] | None = None) -> Station:
    return Station(id=sid, name=sid.upper(), kind=kind, function="f", steps=steps or [])  # type: ignore[arg-type]


def _belt(a: str, b: str, **kw: Any) -> Transport:
    return Transport(id=f"tr-{a}-{b}", from_station=a, to_station=b, kind="belt", **kw)


def _design(stations: list[Station], transports: list[Transport]) -> MachineDesign:
    return MachineDesign(name="t", machine_type="t", summary="t", product=Product(description="p"),
                         stations=stations, transports=transports)


def _fixed(sid: str, order: int, duration: float | None, group: int | None = None) -> Step:
    return Step(id=sid, order=order, kind="fixed_duration", duration_s=duration, parallel_group=group)


def test_sequence_is_derived_from_the_process_graph() -> None:
    # Listed out of flow order on purpose: the graph decides, not the list.
    design = _design(
        [_station("c"), _station("frame", kind="frame"), _station("b"), _station("a")],
        [_belt("b", "c"), _belt("a", "b")],
    )
    seq = {s.id: s.sequence for s in design.stations}
    assert seq == {"a": 1, "b": 2, "c": 3, "frame": 0}

    # Rewiring the graph changes the order with no edit to any station.
    design.transports = [_belt("c", "a"), _belt("a", "b")]
    assert {s.id: s.sequence for s in design.stations} == {"c": 1, "a": 2, "b": 3, "frame": 0}

    # A flow station with no transport yet (a one-station machine) is still in the flow.
    lone = _design([_station("only"), _station("cab", kind="control")], [])
    assert [s.sequence for s in lone.stations] == [1, 0]

    # A flow station not connected yet comes after the connected line, wherever it is listed.
    loose = _design([_station("new"), _station("a"), _station("b")], [_belt("a", "b")])
    assert {s.id: s.sequence for s in loose.stations} == {"a": 1, "b": 2, "new": 3}

    # A reject branch leaves the main line: the line is numbered first, reject destinations after it.
    branched = _design([_station("a"), _station("rej", kind="transport"), _station("b"), _station("c")],
                       [_belt("a", "b", reject_to="rej", reject_rate=0.01), _belt("b", "c")])
    assert {s.id: s.sequence for s in branched.stations} == {"a": 1, "b": 2, "c": 3, "rej": 4}

    # A rework branch back upstream is not a cycle of the main line.
    rework = _design([_station("a"), _station("b")], [_belt("a", "b", reject_to="a", reject_rate=0.05)])
    assert {s.id: s.sequence for s in rework.stations} == {"a": 1, "b": 2}


def test_a_cyclic_process_graph_is_rejected() -> None:
    with pytest.raises(ValidationError, match="cycle"):
        _design([_station("a"), _station("b")], [_belt("a", "b"), _belt("b", "a")])


def test_cycle_time_s_comes_from_the_timing_engine() -> None:
    fixed = _station("a", steps=[_fixed("s2", 2, 0.7), _fixed("s1", 1, 0.5)])
    motion = _station("b", steps=[_fixed("s1", 1, 0.5),
                                  Step(id="s2", order=2, kind="motion", mechanism_id="m1")])
    parallel = _station("c", steps=[_fixed("s1", 1, 0.5, group=1), _fixed("s2", 2, 0.5, group=1)])
    unknown = _station("d", steps=[_fixed("s1", 1, None)])
    empty = _station("e")
    _design([fixed, motion, parallel, unknown, empty], [])

    assert fixed.cycle_time_s == pytest.approx(1.2)
    assert motion.cycle_time_s is None  # its mechanism m1 does not exist: not computable
    assert parallel.cycle_time_s == pytest.approx(0.5)  # one parallel block: its longest member (Phase 2)
    assert unknown.cycle_time_s is None
    assert empty.cycle_time_s is None



def test_cycle_time_s_equals_the_timing_engine_for_every_demo_station() -> None:
    for scenario in SCENARIOS:
        design = demo_design(scenario)
        result = design_timing(design)
        assert [t.station_id for t in result.stations] == [s.id for s in design.stations]
        for station, timing in zip(design.stations, result.stations, strict=True):
            assert station.cycle_time_s == timing.cycle_time_s, (scenario, station.id)
        assert any(t.cycle_time_s is not None for t in result.stations), scenario


def test_derived_values_are_not_stored_dumped_or_in_the_ai_schema(storage: Storage) -> None:
    design = _design([_station("a", steps=[_fixed("s1", 1, 1.0)]), _station("b")], [_belt("a", "b")])
    assert design.stations[0].sequence == 1 and design.stations[0].cycle_time_s == 1.0

    for station in design.model_dump()["stations"]:
        assert not set(DERIVED) & set(station)

    project_id = storage.create_project("problem text", "ok", design)
    (raw,) = storage._conn.execute(
        "SELECT design FROM revisions WHERE project_id = ?", (project_id,)
    ).fetchone()
    for station in json.loads(raw)["stations"]:
        assert not set(DERIVED) & set(station)

    schema = json.dumps(strict_schema(PatchUpdate))
    for name in DERIVED:
        assert f'"{name}"' not in schema


def test_derived_values_cannot_be_set() -> None:
    for name, value in (("sequence", 1), ("cycle_time_s", 1.0)):
        with pytest.raises(ValidationError, match=f"{name} is derived"):
            Station(id="a", name="A", function="f", **{name: value})
    station = _design([_station("a")], []).stations[0]
    with pytest.raises(AttributeError):
        station.sequence = 3  # type: ignore[misc]
    with pytest.raises(AttributeError):
        station.cycle_time_s = 1.0  # type: ignore[misc]


def test_copies_and_equality_keep_the_derived_values() -> None:
    design = _design([_station("b"), _station("a", steps=[_fixed("s1", 1, 2.0)])], [_belt("a", "b")])
    copy = design.model_copy(deep=True)
    assert copy == design
    copy.transports = [_belt("b", "a")]
    assert [s.sequence for s in copy.stations] == [1, 2]
    assert [s.sequence for s in design.stations] == [2, 1]  # the original is untouched
    assert copy != design

    # Shallow copies too: a copy's stations follow the copy's own transports.
    shallow = design.model_copy(update={"transports": [_belt("b", "a")]})
    assert [s.sequence for s in shallow.stations] == [1, 2]
    assert [s.sequence for s in design.stations] == [2, 1]
    plain = copy_module.copy(design)
    plain.transports = [_belt("b", "a")]
    assert [s.sequence for s in plain.stations] == [1, 2]
    assert [s.sequence for s in design.stations] == [2, 1]

    reloaded = MachineDesign.model_validate_json(design.model_dump_json())
    assert reloaded == design
    assert [(s.sequence, s.cycle_time_s) for s in reloaded.stations] == [(2, None), (1, 2.0)]


def test_a_station_outside_a_design_has_no_derived_sequence() -> None:
    design = _design([_station("a")], [])
    detached = design.stations.pop()
    with pytest.raises(RuntimeError, match="not part of a MachineDesign"):
        _ = detached.sequence


def test_schema_version_and_placement_are_not_written_by_the_ai() -> None:
    design = _design([], [])
    assert design.schema_version == 3 and design.model_dump()["schema_version"] == 3
    schema = json.dumps(strict_schema(PatchUpdate))
    assert '"schema_version"' not in schema
    assert '"placement"' not in schema and '"x_mm"' not in schema  # coordinates come from the layout (rule 3)
    with pytest.raises(ValidationError):
        MachineDesign.model_validate({**design.model_dump(), "schema_version": 1})
