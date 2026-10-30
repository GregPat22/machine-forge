"""Timing results per revision: storage, service, API and diff (Phase 2, section G; ADR 0028).

Expected cycle times are worked out by hand from the trapezoidal closed form (Biagiotti &
Melchiorri 2008, section 3.2): stroke 200 mm, 500 mm/s, 2000 mm/s² reaches the speed
(500²/2000 = 125 ≤ 200), so T = 200/500 + 500/2000 = 0.65 s; stroke 300 mm gives 0.85 s.
Bounds tables here are synthetic fixtures, not catalog data.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.engines.bounds import BoundsTable
from app.llm.mock import MockProvider
from app.main import create_app
from app.models import Component, MachineDesign, Mechanism, Station, Step, Transport
from app.services import timing as timing_service
from app.services.timing import ENGINE, compute_timing, timing_for
from app.storage import Storage

FIXTURES = Path(__file__).parent / "fixtures" / "v2"
TOL = 1e-9


def _fixture_table(version: str = "fixture-1", accel_max: float = 1000.0) -> BoundsTable:
    """A synthetic bounds table (test fixture, not catalog data)."""
    source = {"as_printed": "fixture", "source_title": "Fixture table for tests, not catalog data",
              "source_url": "https://example.invalid/fixture", "source_page": None, "accessed": None}
    return BoundsTable(version=version, rows=[
        {"id": "fixture-servo-linear-acceleration", "field": "acceleration", "unit": "mm/s2",
         "min": None, "max": accel_max, **source,
         "applies_to": {"component_category": "servo_motor", "transport_kind": None, "mechanism_kind": "linear"}},
        {"id": "fixture-indexing-time", "field": "index_time_s", "unit": "s", "min": None, "max": 1.0, **source,
         "applies_to": {"component_category": None, "transport_kind": "indexing", "mechanism_kind": None}},
    ])


def _design(stroke: float = 200.0, seal_s: float = 0.2, target: float | None = None,
            acceleration: float = 2000.0, index_time_s: float | None = None) -> MachineDesign:
    sealing = Station(
        id="st-seal", name="Sealing", function="seals the web",
        mechanisms=[Mechanism(id="m-lift", kind="linear", stroke=stroke, max_speed=500.0, acceleration=acceleration)],
        components=[Component(id="c-servo", name="Lift servo", category="servo_motor", quantity=1, motion="m-lift")],
        steps=[Step(id="lift", order=1, kind="motion", mechanism_id="m-lift"),
               Step(id="seal", order=2, kind="fixed_duration", duration_s=seal_s)],
        target_cycle_time_s=target,
    )
    cutting = Station(id="st-cut", name="Cutting", function="cuts",
                      steps=[Step(id="cut", order=1, kind="fixed_duration", duration_s=0.4)])
    transports = []
    if index_time_s is not None:
        transports = [Transport(id="tr-seal-cut", from_station="st-seal", to_station="st-cut", kind="indexing",
                                index_time_s=index_time_s)]
    return MachineDesign(name="Sealer", machine_type="sealer", summary="s", stations=[sealing, cutting],
                         transports=transports)


def _station(result, station_id: str):
    return next(s for s in result.stations if s.station_id == station_id)


class CountingProvider(MockProvider):
    """The mock provider, counting every call: the timing path must make none."""

    def __init__(self) -> None:
        super().__init__(scenario="blister")
        self.calls = 0

    def structured(self, **kw):  # type: ignore[override]
        self.calls += 1
        return super().structured(**kw)


def _client(storage: Storage, provider: MockProvider | None = None) -> TestClient:
    app = create_app(settings=Settings(llm_provider="mock"), storage=storage,
                     provider=provider or MockProvider(scenario="blister"), connectors=[])
    return TestClient(app)


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts how often the service runs the timing engine."""
    calls: list[int] = []
    original = timing_service.design_timing

    def wrapped(design: MachineDesign):
        calls.append(1)
        return original(design)

    monkeypatch.setattr(timing_service, "design_timing", wrapped)
    return calls


# --- storage and service ---------------------------------------------------------------------------


def test_results_table_is_created_on_an_old_database(tmp_path: Path) -> None:
    db = tmp_path / "phase1.db"
    shutil.copy(FIXTURES / "phase1.db", db)
    tables = {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "revision_results" not in tables  # the fixture predates the table

    storage = Storage(db)
    project = storage.list_projects()[0]
    result = timing_for(storage, project.id, project.latest_revision, table=_fixture_table())
    stored = storage.get_result(project.id, project.latest_revision, ENGINE)
    assert stored is not None and stored.result == result.model_dump_json()


def test_timing_is_computed_once_then_read_from_storage(counted: list[int]) -> None:
    storage = Storage(":memory:")
    pid = storage.create_project("seal trays", "first", _design())
    table = _fixture_table()

    first = timing_for(storage, pid, 1, table=table)
    assert len(counted) == 1
    assert abs(_station(first, "st-seal").cycle_time_s - (0.65 + 0.2)) < TOL
    assert first.engine_version == timing_service.ENGINE_VERSION and first.bounds_version == "fixture-1"

    second = timing_for(storage, pid, 1, table=table)
    assert len(counted) == 1  # read back, not recomputed
    assert second == first


def test_stale_engine_or_bounds_version_is_recomputed(counted: list[int]) -> None:
    storage = Storage(":memory:")
    pid = storage.create_project("seal trays", "first", _design())
    table = _fixture_table()
    first = timing_for(storage, pid, 1, table=table)

    # A row written by an older engine is recomputed and replaced.
    storage.put_result(pid, 1, ENGINE, first.engine_version - 1, table.version, first.model_dump_json())
    timing_for(storage, pid, 1, table=table)
    assert len(counted) == 2
    assert storage.get_result(pid, 1, ENGINE).engine_version == timing_service.ENGINE_VERSION

    # A changed bounds table is a new inputs version: recomputed with the new table.
    changed = _fixture_table(version="fixture-2", accel_max=1500.0)
    result = timing_for(storage, pid, 1, table=changed)
    assert len(counted) == 3
    assert result.bounds_version == "fixture-2"
    assert storage.get_result(pid, 1, ENGINE).inputs_version == "fixture-2"


def test_recompute_reproduces_the_stored_result() -> None:
    # ADR 0003: a stored result is a cache; the revision's design gives the same JSON again.
    storage = Storage(":memory:")
    pid = storage.create_project("seal trays", "first", _design(target=0.5, index_time_s=2.0))
    table = _fixture_table()
    timing_for(storage, pid, 1, table=table)
    stored = storage.get_result(pid, 1, ENGINE)
    assert stored.result == compute_timing(storage.get_revision(pid, 1).design, table).model_dump_json()


def test_results_are_deleted_with_the_project() -> None:
    storage = Storage(":memory:")
    pid = storage.create_project("seal trays", "first", _design())
    timing_for(storage, pid, 1, table=_fixture_table())
    assert storage.get_result(pid, 1, ENGINE) is not None
    assert storage.delete_project(pid)
    assert storage.get_result(pid, 1, ENGINE) is None
    assert storage._conn.execute("SELECT COUNT(*) FROM revision_results").fetchone()[0] == 0


def test_bounds_warnings_are_in_the_timing_result() -> None:
    # A mechanism's warning goes to its station, next to target_not_met; a transport's to the machine.
    design = _design(acceleration=2000.0, target=0.5, index_time_s=2.0)
    design.stations[1].mechanisms = [Mechanism(id="m-free", kind="linear", stroke=10.0)]
    result = compute_timing(design, _fixture_table(accel_max=1000.0))

    sealing = _station(result, "st-seal")
    assert [(w.code, w.step_id, w.mechanism_id, w.row_id) for w in sealing.warnings] == [
        ("target_not_met", "lift", None, None),
        ("out_of_bounds", None, "m-lift", "fixture-servo-linear-acceleration"),
    ]
    assert sealing.warnings[1].value == 2000.0 and sealing.warnings[1].limit == 1000.0
    assert _station(result, "st-cut").warnings == []
    assert [(w.code, w.transport_id, w.row_id) for w in result.warnings] == [
        ("out_of_bounds", "tr-seal-cut", "fixture-indexing-time")]
    assert [(u.station_id, u.mechanism_id) for u in result.unchecked] == [("st-cut", "m-free")]
    # Never a correction: the design is unchanged.
    assert design.stations[0].mechanisms[0].acceleration == 2000.0


# --- API -------------------------------------------------------------------------------------------


def test_timing_endpoint_returns_the_revision_result() -> None:
    storage = Storage(":memory:")
    pid = storage.create_project("seal trays", "first", _design())
    storage.add_revision(pid, "longer stroke", "ok", _design(stroke=300.0))
    client = _client(storage)

    latest = client.get(f"/api/projects/{pid}/timing")
    assert latest.status_code == 200, latest.text
    assert latest.json() == timing_for(storage, pid, 2).model_dump(mode="json")
    first = client.get(f"/api/projects/{pid}/timing", params={"revision": 1})
    assert first.status_code == 200, first.text
    assert first.json() == timing_for(storage, pid, 1).model_dump(mode="json")
    sealing = next(s for s in first.json()["stations"] if s["station_id"] == "st-seal")
    assert abs(sealing["cycle_time_s"] - (0.65 + 0.2)) < TOL


def test_timing_endpoint_404() -> None:
    storage = Storage(":memory:")
    pid = storage.create_project("seal trays", "first", _design())
    client = _client(storage)
    assert client.get("/api/projects/nope/timing").status_code == 404
    assert client.get(f"/api/projects/{pid}/timing", params={"revision": 7}).status_code == 404
    assert storage._conn.execute("SELECT COUNT(*) FROM revision_results").fetchone()[0] == 0


def test_diff_reports_cycle_time_and_limiting_step_changes() -> None:
    storage = Storage(":memory:")
    # Revision 1: lift 0.65 s limits a 0.85 s cycle, target 1.0 s met.
    pid = storage.create_project("seal trays", "first", _design(seal_s=0.2, target=1.0))
    # Revision 2: a 0.9 s seal limits a 1.55 s cycle, target missed.
    storage.add_revision(pid, "longer seal", "ok", _design(seal_s=0.9, target=1.0))
    client = _client(storage)

    response = client.get(f"/api/projects/{pid}/diff", params={"from": 1, "to": 2})
    assert response.status_code == 200, response.text
    timing = response.json()["timing"]
    assert [s["station_id"] for s in timing["stations"]] == ["st-seal"]  # cutting did not change
    sealing = timing["stations"][0]
    assert abs(sealing["cycle_time_s_before"] - 0.85) < TOL
    assert abs(sealing["cycle_time_s_after"] - 1.55) < TOL
    assert (sealing["limiting_step_before"], sealing["limiting_step_after"]) == ("lift", "seal")
    assert [(w["code"], w["step_id"]) for w in sealing["warnings_added"]] == [("target_not_met", "seal")]
    assert sealing["warnings_removed"] == []
    assert timing["warnings_added"] == [] and timing["warnings_removed"] == []

    # Back again: the warning is removed.
    back = client.get(f"/api/projects/{pid}/diff", params={"from": 2, "to": 1}).json()["timing"]
    assert [(w["code"], w["step_id"]) for w in back["stations"][0]["warnings_removed"]] == [("target_not_met", "seal")]
    # The existing diff fields are still there.
    assert {"machine", "lists", "stations", "components", "counts"} <= response.json().keys()


def test_editing_a_stroke_changes_the_timing_without_an_ai_call() -> None:
    storage = Storage(":memory:")
    pid = storage.create_project("seal trays", "first", _design(stroke=200.0))
    provider = CountingProvider()
    client = _client(storage, provider)

    before = client.get(f"/api/projects/{pid}/timing").json()
    longer = {"id": "m-lift", "kind": "linear", "stroke": 300.0, "max_speed": 500.0, "acceleration": 2000.0}
    edit = client.post(f"/api/projects/{pid}/patches", json={
        "expected_revision": 1,
        "patches": [{"op": "set_mechanism", "station_id": "st-seal", "mechanism": longer}],
    })
    assert edit.status_code == 200, edit.text
    after = client.get(f"/api/projects/{pid}/timing").json()

    def seal(result: dict) -> dict:
        return next(s for s in result["stations"] if s["station_id"] == "st-seal")

    assert abs(seal(before)["cycle_time_s"] - (0.65 + 0.2)) < TOL
    assert abs(seal(after)["cycle_time_s"] - (0.85 + 0.2)) < TOL
    assert provider.calls == 0
