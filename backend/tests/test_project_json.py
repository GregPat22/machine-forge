"""Project JSON export/import (Phase 1 spec, section E)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.llm.mock import MockProvider
from app.main import create_app
from app.storage import Storage
from tests.conftest import BLISTER_PROBLEM

V1_DESIGN = Path(__file__).parent / "fixtures" / "v1" / "designs" / "blister.json"


def _created(client: TestClient) -> dict:
    project = client.post("/api/projects", json={"problem": BLISTER_PROBLEM}).json()
    client.post(f"/api/projects/{project['id']}/prompt", json={"message": "Add vision inspection of every blister"})
    return project


def _export(client: TestClient, pid: str) -> dict:
    response = client.get(f"/api/projects/{pid}/export")
    assert response.status_code == 200
    return response.json()


def test_export_then_import_reproduces_designs_and_revisions(client: TestClient) -> None:
    pid = _created(client)["id"]
    exported = _export(client, pid)
    assert exported["format"] == "machine-forge-project"
    assert exported["format_version"] == 1
    assert [r["number"] for r in exported["revisions"]] == [1, 2]

    response = client.post("/api/projects/import", content=json.dumps(exported))
    assert response.status_code == 201
    new = response.json()
    assert new["id"] != pid
    assert new["latest_revision"] == 2

    old_revs = client.get(f"/api/projects/{pid}/revisions").json()
    new_revs = client.get(f"/api/projects/{new['id']}/revisions").json()
    assert new_revs == old_revs
    assert client.get(f"/api/projects/{new['id']}").json()["messages"] == client.get(f"/api/projects/{pid}").json()["messages"]
    # The source project is untouched and a second export round-trips byte for byte.
    assert len(client.get("/api/projects").json()) == 2
    assert _export(client, new["id"])["revisions"] == exported["revisions"]


def test_import_into_an_empty_database(client: TestClient, settings) -> None:
    exported = _export(client, _created(client)["id"])
    other = TestClient(create_app(settings=replace(settings), storage=Storage(":memory:"),
                                  provider=MockProvider(scenario="blister"), connectors=[]))
    assert other.post("/api/projects/import", content=json.dumps(exported)).status_code == 201
    assert len(other.get("/api/projects").json()) == 1


def test_oversized_file_is_rejected(client: TestClient, settings) -> None:
    small = TestClient(create_app(settings=replace(settings, max_import_bytes=100), storage=Storage(":memory:"),
                                  provider=MockProvider(scenario="blister"), connectors=[]))
    exported = _export(client, _created(client)["id"])
    response = small.post("/api/projects/import", content=json.dumps(exported))
    assert response.status_code == 413
    assert "import limit is 100 bytes" in response.json()["detail"]
    assert small.get("/api/projects").json() == []


def test_wrong_format_version_is_rejected(client: TestClient) -> None:
    exported = _export(client, _created(client)["id"])
    exported["format_version"] = 2
    response = client.post("/api/projects/import", content=json.dumps(exported))
    assert response.status_code == 400
    assert "Unsupported format_version 2" in response.json()["detail"]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"not json", "Not a valid JSON file"),
        (b'{"format": "other"}', "Not a Machine Forge project file"),
        (b'{"format": "machine-forge-project", "format_version": 1}', "malformed"),
    ],
)
def test_malformed_files_are_rejected(client: TestClient, content: bytes, message: str) -> None:
    response = client.post("/api/projects/import", content=content)
    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_future_design_schema_and_bad_design_are_rejected(client: TestClient) -> None:
    exported = _export(client, _created(client)["id"])
    future = json.loads(json.dumps(exported))
    future["revisions"][0]["schema_version"] = 99
    r = client.post("/api/projects/import", content=json.dumps(future))
    assert r.status_code == 400 and "design schema 99" in r.json()["detail"]

    broken = json.loads(json.dumps(exported))
    broken["revisions"][1]["design"] = {"stations": "nope"}
    r = client.post("/api/projects/import", content=json.dumps(broken))
    assert r.status_code == 400 and "Revision 2 has an invalid design" in r.json()["detail"]
    assert len(client.get("/api/projects").json()) == 1  # nothing half-imported


def test_design_with_a_cyclic_process_graph_is_rejected(client: TestClient) -> None:
    exported = _export(client, _created(client)["id"])
    design = exported["revisions"][0]["design"]
    first = design["transports"][0]
    design["transports"].append({**first, "id": "tr-back", "from_station": first["to_station"],
                                 "to_station": first["from_station"]})
    r = client.post("/api/projects/import", content=json.dumps(exported))
    assert r.status_code == 400 and "cycle" in r.json()["detail"]
    assert len(client.get("/api/projects").json()) == 1


def test_duplicate_revision_numbers_are_rejected(client: TestClient) -> None:
    exported = _export(client, _created(client)["id"])
    exported["revisions"][1]["number"] = 1
    r = client.post("/api/projects/import", content=json.dumps(exported))
    assert r.status_code == 400 and "unique" in r.json()["detail"]


def test_importing_a_v1_era_export_migrates(client: TestClient) -> None:
    v1 = json.loads(V1_DESIGN.read_text())
    stamp = "2026-01-01T00:00:00+00:00"
    file = {
        "format": "machine-forge-project", "format_version": 1,
        "project": {"name": v1["name"], "problem": BLISTER_PROBLEM, "created_at": stamp, "updated_at": stamp},
        "revisions": [{"number": 1, "prompt": BLISTER_PROBLEM, "reply": "ok", "schema_version": 1,
                       "created_at": stamp, "design": v1}],
        "messages": [{"role": "user", "content": BLISTER_PROBLEM, "revision": None, "created_at": stamp}],
    }
    r = client.post("/api/projects/import", content=json.dumps(file))
    assert r.status_code == 201
    body = r.json()
    assert body["design"]["schema_version"] == 2
    assert body["design"]["transports"], "v1 sequence becomes a transport chain"
    assert [s["sequence"] for s in body["design"]["stations"] if s["sequence"]] == sorted(
        s["sequence"] for s in v1["stations"] if s["sequence"]
    )


def test_export_of_unknown_project_is_404(client: TestClient) -> None:
    assert client.get("/api/projects/nope/export").status_code == 404
