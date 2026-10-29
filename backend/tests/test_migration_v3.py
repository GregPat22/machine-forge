"""Model v2 -> v3: motion profile fields (Phase 2 spec, section A; ADR 0026).

Fixtures in tests/fixtures/v2 were written by the v2 code (see make_fixtures.py there).
"""

from __future__ import annotations

import copy
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.migrations.design_v1 import MachineDesignV1, migrate_design, to_v1
from app.models import MachineDesign
from app.storage import DESIGN_SCHEMA_VERSION, Storage

V1_DESIGNS = sorted((Path(__file__).parent / "fixtures" / "v1" / "designs").glob("*.json"))
FIXTURES = Path(__file__).parent / "fixtures" / "v2"
PROJECTS: dict[str, str] = json.loads((FIXTURES / "phase1.json").read_text())["projects"]
PROFILE_DEFAULTS = {"profile": "trapezoidal", "jerk": None}


def _v2_rows() -> list[tuple[str, int, int, dict]]:
    conn = sqlite3.connect(f"file:{FIXTURES / 'phase1.db'}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT project_id, number, schema_version, design FROM revisions ORDER BY rowid"
        ).fetchall()
    finally:
        conn.close()
    return [(pid, number, version, json.loads(design)) for pid, number, version, design in rows]


def _as_v3(raw: dict) -> dict:
    """What a v2 design must read as in v3, built by hand: the version and the mechanism defaults."""
    expected = copy.deepcopy(raw)
    expected["schema_version"] = 3
    for station in expected["stations"]:
        for mechanism in station["mechanisms"]:
            mechanism.update(PROFILE_DEFAULTS)
    return expected


def test_v2_revisions_migrate_to_v3_with_profile_defaults() -> None:
    rows = _v2_rows()
    assert len(rows) == 6
    mechanisms = 0
    for _, _, version, raw in rows:
        assert version == 2 and raw["schema_version"] == 2
        for station in raw["stations"]:
            for mechanism in station["mechanisms"]:
                assert not set(PROFILE_DEFAULTS) & set(mechanism)  # written before the fields existed
                mechanisms += 1
        design = migrate_design(raw, from_version=2)
        assert isinstance(design, MachineDesign) and design.schema_version == 3
        assert design.model_dump() == _as_v3(raw)  # the defaults, and nothing else changes
        assert MachineDesign.model_validate_json(design.model_dump_json()) == design  # valid as stored v3
        assert migrate_design(design.model_dump(), from_version=3) == design
    assert mechanisms > 0  # the fixture has mechanisms to migrate


@pytest.mark.parametrize("path", V1_DESIGNS, ids=lambda p: p.stem)
def test_v1_revisions_still_migrate(path: Path) -> None:
    raw = json.loads(path.read_text())
    design = migrate_design(raw, from_version=1)
    assert isinstance(design, MachineDesign) and design.schema_version == 3
    assert all(
        (m.profile, m.jerk) == ("trapezoidal", None) for s in design.stations for m in s.mechanisms
    )
    reread = MachineDesign.model_validate_json(design.model_dump_json())
    assert reread == design
    assert to_v1(reread).model_dump() == MachineDesignV1.model_validate(raw).model_dump()


def test_old_database_opens_after_phase_2(tmp_path: Path) -> None:
    db = tmp_path / "phase1.db"
    shutil.copy(FIXTURES / "phase1.db", db)
    before = sqlite3.connect(db).execute("SELECT rowid, design, schema_version FROM revisions ORDER BY rowid").fetchall()

    storage = Storage(db)
    assert {p.id for p in storage.list_projects()} == set(PROJECTS.values())
    raw = {(pid, number): design for pid, number, _, design in _v2_rows()}
    for pid in PROJECTS.values():
        for revision in storage.list_revisions(pid):
            assert revision.schema_version == 2  # kept until a new revision is saved
            assert revision.design.model_dump() == _as_v3(raw[(pid, revision.number)])
    blister = PROJECTS["blister"]
    revisions = storage.list_revisions(blister)
    assert [r.number for r in revisions] == [1, 2, 3]
    assert [r.design.layout_style for r in revisions] == ["inline", "u_shape", "inline"]
    project = storage.get_project(blister)
    assert project is not None and project.design == revisions[-1].design

    number = storage.add_revision(blister, "restore 1", "ok", revisions[0].design)
    new = storage.get_revision(blister, number)
    assert new is not None and new.schema_version == DESIGN_SCHEMA_VERSION == 3
    assert new.design == revisions[0].design
    after = sqlite3.connect(db).execute("SELECT rowid, design, schema_version FROM revisions ORDER BY rowid").fetchall()
    assert after[: len(before)] == before  # old rows are migrated on read, never rewritten


def test_version_2_project_json_imports(client: TestClient, storage: Storage) -> None:
    file = json.loads((FIXTURES / "blister-export.json").read_text())
    assert [(r["schema_version"], r["design"]["schema_version"]) for r in file["revisions"]] == [(2, 2)] * 3

    response = client.post("/api/projects/import", content=json.dumps(file))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["design"]["schema_version"] == 3
    revisions = storage.list_revisions(body["id"])
    assert [r.number for r in revisions] == [r["number"] for r in file["revisions"]] == [1, 2, 3]
    for revision, exported in zip(revisions, file["revisions"]):
        assert revision.schema_version == 3  # stored at the current version on import
        assert revision.design.model_dump() == _as_v3(exported["design"])
