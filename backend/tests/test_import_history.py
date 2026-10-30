"""Own-format imports must contain a complete history that revision readers can navigate."""
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient


def _payload(client, numbers):
    response = client.post("/api/projects", json={"problem": "Synthetic history import test"})
    pid = response.json()["id"]
    payload = client.get(f"/api/projects/{pid}/export").json()
    original = payload["revisions"][0]
    payload["revisions"] = [{**deepcopy(original), "number": number} for number in numbers]
    payload["messages"] = []
    return payload


@pytest.mark.parametrize("numbers", [[2], [1, 3], [2, 3], [1, 2, 4], [1, 2**63]])
def test_incomplete_history_is_rejected_before_creating_a_project(client, numbers):
    client = TestClient(client.app, raise_server_exceptions=False)
    payload = _payload(client, numbers)
    response = client.post("/api/projects/import", content=json.dumps(payload))
    assert response.status_code == 400, response.text
    assert "consecutive" in response.json()["detail"]
    assert len(client.get("/api/projects").json()) == 1


@pytest.mark.parametrize("numbers", [[1], [1, 2], [2, 1]])
def test_complete_history_imports_and_default_diff_works(client, numbers):
    payload = _payload(client, numbers)
    response = client.post("/api/projects/import", content=json.dumps(payload))
    assert response.status_code == 201, response.text
    pid = response.json()["id"]
    assert [r["number"] for r in client.get(f"/api/projects/{pid}/revisions").json()] == sorted(numbers)
    assert client.get(f"/api/projects/{pid}/diff").status_code == 200
