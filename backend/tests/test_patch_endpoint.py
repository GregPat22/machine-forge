"""Model editor endpoint (Phase 1 step 7a): edits go through the same patch validator as the AI."""
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm.mock import MockProvider, demo_design
from app.main import create_app
from app.storage import Storage


def _client(provider: str = "mock") -> tuple[TestClient, Storage, str]:
    storage = Storage(":memory:")
    pid = storage.create_project("pack tablets into blisters", "first design", demo_design())
    app = create_app(settings=Settings(llm_provider=provider), storage=storage,
                     provider=MockProvider() if provider == "mock" else None, connectors=[])
    return TestClient(app, raise_server_exceptions=False), storage, pid


SET_FILM_WIDTH = {"op": "set_param", "station_id": "st-forming", "name": "film_width", "value": 140, "unit": "mm"}
NEGATIVE_LANES = {"op": "set_product", "product": {"lanes": -1}}


def test_editor_patch_creates_a_revision():
    c, storage, pid = _client()
    response = c.post(f"/api/projects/{pid}/patches", json={"expected_revision": 1, "patches": [SET_FILM_WIDTH]})
    assert response.status_code == 200, response.text
    project = response.json()
    assert project["latest_revision"] == 2
    forming = next(s for s in project["design"]["stations"] if s["id"] == "st-forming")
    assert {"name": "film_width", "value": 140.0, "unit": "mm"} in forming["parameters"]
    # The derived values are in the response like in every other project response.
    assert forming["sequence"] == 1
    user, assistant = project["messages"][-2:]
    assert user["role"] == "user" and user["content"] == "Model editor: set_param st-forming film_width"
    assert assistant["role"] == "assistant" and assistant["revision"] == 2
    assert assistant["content"] == "Saved 1 edit from the model editor."
    # Stored, not only returned.
    reloaded = c.get(f"/api/projects/{pid}").json()
    assert reloaded["latest_revision"] == 2
    assert reloaded["design"] == project["design"]
    assert storage.get_revision(pid, 2).prompt == "Model editor: set_param st-forming film_width"


def test_editor_patch_rejected_returns_the_errors_and_saves_nothing():
    c, storage, pid = _client()
    before = c.get(f"/api/projects/{pid}").json()
    response = c.post(f"/api/projects/{pid}/patches",
                      json={"expected_revision": 1, "patches": [SET_FILM_WIDTH, NEGATIVE_LANES]})
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["message"] == "The edit was not saved: 1 problem found. Fix it and save again."
    assert detail["errors"] == [
        {"index": 1, "code": "invalid_value", "message": "product lanes is -1; it must be at least 1"}
    ]
    # All or nothing: the valid first op was not saved either, and the chat is unchanged.
    assert c.get(f"/api/projects/{pid}").json() == before
    assert len(storage.list_revisions(pid)) == 1


def test_editor_patch_cannot_set_computed_values():
    c, _, pid = _client()
    response = c.post(f"/api/projects/{pid}/patches", json={
        "expected_revision": 1,
        "patches": [{"op": "set_param", "name": "footprint", "text": "1 m x 1 m"}],
    })
    assert response.status_code == 400, response.text
    assert [e["code"] for e in response.json()["detail"]["errors"]] == ["computed_field"]


def test_editor_patch_rejects_a_station_sent_back_with_derived_values():
    c, storage, pid = _client()
    station = c.get(f"/api/projects/{pid}").json()["design"]["stations"][0]  # has sequence and cycle_time_s
    station["id"] = "st-forming-2"
    response = c.post(f"/api/projects/{pid}/patches",
                      json={"expected_revision": 1, "patches": [{"op": "add_station", "station": station}]})
    assert response.status_code == 422, response.text
    assert "derived from the model and cannot be set" in response.text
    assert len(storage.list_revisions(pid)) == 1


def test_editor_patch_on_an_older_revision_is_a_conflict():
    c, storage, pid = _client()
    storage.add_revision(pid, "a chat turn", "reply", demo_design())
    response = c.post(f"/api/projects/{pid}/patches", json={"expected_revision": 1, "patches": [SET_FILM_WIDTH]})
    assert response.status_code == 409, response.text
    assert "Reload the project" in response.json()["detail"]
    assert len(storage.list_revisions(pid)) == 2


def test_editor_patch_does_not_need_an_ai_provider():
    c, _, pid = _client(provider="openai")  # no key: the provider cannot be built
    response = c.post(f"/api/projects/{pid}/patches", json={"expected_revision": 1, "patches": [SET_FILM_WIDTH]})
    assert response.status_code == 200, response.text
    assert response.json()["latest_revision"] == 2


def test_editor_patch_unknown_project_and_empty_list():
    c, _, pid = _client()
    missing = c.post("/api/projects/nope/patches", json={"expected_revision": 1, "patches": [SET_FILM_WIDTH]})
    assert missing.status_code == 404, missing.text
    assert missing.json()["detail"] == "Project nope not found"  # not FastAPI's "Not Found" for a missing route
    empty = c.post(f"/api/projects/{pid}/patches", json={"expected_revision": 1, "patches": []})
    assert empty.status_code == 422, empty.text
