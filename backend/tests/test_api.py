from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage import Storage
from tests.conftest import BLISTER_PROBLEM


def test_create_refine_restore_flow(client: TestClient) -> None:
    created = client.post("/api/projects", json={"problem": BLISTER_PROBLEM})
    assert created.status_code == 201
    project = created.json()
    assert project["latest_revision"] == 1
    assert project["design"]["machine_type"].startswith("Thermoforming blister")
    assert [m["role"] for m in project["messages"]] == ["user", "assistant"]
    pid = project["id"]

    refined = client.post(f"/api/projects/{pid}/prompt", json={"message": "Add vision inspection of every blister"})
    assert refined.status_code == 200
    body = refined.json()
    assert body["latest_revision"] == 2
    station_ids = [s["id"] for s in body["design"]["stations"]]
    assert "st-vision" in station_ids
    outfeed = next(s for s in body["design"]["stations"] if s["id"] == "st-outfeed")
    vision = next(s for s in body["design"]["stations"] if s["id"] == "st-vision")
    assert vision["sequence"] < outfeed["sequence"]

    revisions = client.get(f"/api/projects/{pid}/revisions").json()
    assert [r["number"] for r in revisions] == [1, 2]

    restored = client.post(f"/api/projects/{pid}/revisions/1/restore").json()
    assert restored["latest_revision"] == 3
    assert "st-vision" not in [s["id"] for s in restored["design"]["stations"]]

    assert len(client.get("/api/projects").json()) == 1
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_spare_parts_endpoints(client: TestClient) -> None:
    pid = client.post("/api/projects", json={"problem": BLISTER_PROBLEM}).json()["id"]
    parts = client.get(f"/api/projects/{pid}/spare-parts").json()
    assert parts and parts[0]["item"] == 1
    assert any(p["part_number"] == "6ES7515-2AM02-0AB0" for p in parts)

    csv_response = client.get(f"/api/projects/{pid}/spare-parts.csv")
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert csv_response.text.splitlines()[0].startswith("Item,Name,Category")

    report = client.get(f"/api/projects/{pid}/sourcing").json()
    assert report["revision"] == 1
    assert len(report["lines"]) == len(parts)


def test_price_list_upload_and_sourcing(client: TestClient) -> None:
    pid = client.post("/api/projects", json={"problem": BLISTER_PROBLEM}).json()["id"]
    csv_data = "Fornitore;Codice;Descrizione;Prezzo;Valuta\nRivenditore Srl;6ES7515-2AM02-0AB0;CPU 1515-2 PN;2.150,00;EUR\n"
    uploaded = client.post("/api/price-list", files={"file": ("listino.csv", csv_data.encode(), "text/csv")})
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["imported"] == 1

    report = client.get(f"/api/projects/{pid}/sourcing").json()
    cpu = next(line for line in report["lines"] if line["part"]["part_number"] == "6ES7515-2AM02-0AB0")
    assert cpu["current"]["supplier"] == "Rivenditore Srl"
    assert cpu["current"]["unit_price_base"] == 2150.0


def test_bad_price_list_is_400(client: TestClient) -> None:
    response = client.post("/api/price-list", files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
    assert response.status_code == 400
    assert "supplier" in response.json()["detail"].lower()


def test_unconfigured_llm_returns_503() -> None:
    settings = Settings(llm_provider="nonsense")
    app = create_app(settings=settings, storage=Storage(":memory:"), connectors=[])
    client = TestClient(app)
    status = client.get("/api/status").json()
    assert status["llm"]["ready"] is False
    response = client.post("/api/projects", json={"problem": BLISTER_PROBLEM})
    assert response.status_code == 503
    assert "MF_LLM_PROVIDER" in response.json()["detail"]


def test_connectors_status(client: TestClient) -> None:
    names = {c["name"]: c["configured"] for c in client.get("/api/connectors").json()}
    assert names == {"mouser": False, "nexar": False}
