from __future__ import annotations

import json

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


def test_layout_and_document_endpoints(client: TestClient) -> None:
    pid = client.post("/api/projects", json={"problem": BLISTER_PROBLEM}).json()["id"]
    layout = client.get(f"/api/projects/{pid}/layout").json()
    assert layout["style"] == "inline" and layout["boxes"]

    u_shape = client.post(f"/api/projects/{pid}/prompt", json={"message": "Make it U-shaped, the hall is short"})
    assert u_shape.json()["design"]["layout_style"] == "u_shape"
    assert client.get(f"/api/projects/{pid}/layout").json()["style"] == "u_shape"
    assert client.get(f"/api/projects/{pid}/layout?revision=1").json()["style"] == "inline"

    doc = client.get(f"/api/projects/{pid}/documents").json()
    assert doc["revision"] == 2 and len(doc["sections"]) == 9
    md = client.get(f"/api/projects/{pid}/documents.md")
    assert md.headers["content-type"].startswith("text/markdown")
    docx = client.get(f"/api/projects/{pid}/documents.docx?revision=1")
    assert docx.content[:2] == b"PK"
    assert "r1.docx" in docx.headers["content-disposition"]


def _sse_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if "event" in lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_streaming_create_and_prompt(client: TestClient) -> None:
    with client.stream("POST", "/api/projects/stream", json={"problem": BLISTER_PROBLEM}) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(response.read().decode())
    kinds = [k for k, _ in events]
    assert kinds[0] == "progress" and kinds[-1] == "done"
    project = events[-1][1]
    assert project["latest_revision"] == 1

    with client.stream("POST", f"/api/projects/{project['id']}/prompt/stream",
                       json={"message": "add vision inspection"}) as response:
        events = _sse_events(response.read().decode())
    assert events[-1][0] == "done" and events[-1][1]["latest_revision"] == 2
    writing = [p for k, p in events if k == "progress" and p["phase"] == "writing"]
    # The answer is patches: the counts are what this answer writes, here the one added station.
    added = len(events[-1][1]["design"]["stations"]) - len(project["design"]["stations"])
    assert writing and (writing[-1]["stations"], added) == (1, 1)

    assert client.post("/api/projects/nope/prompt/stream", json={"message": "x"}).status_code == 404


def test_diff_drawing_and_plc_endpoints(client: TestClient) -> None:
    pid = client.post("/api/projects", json={"problem": BLISTER_PROBLEM}).json()["id"]
    client.post(f"/api/projects/{pid}/prompt", json={"message": "add vision inspection"})
    diff = client.get(f"/api/projects/{pid}/diff").json()
    assert (diff["from_revision"], diff["to_revision"]) == (1, 2)
    assert diff["counts"]["stations_added"] == 1 and diff["counts"]["components_added"] == 2
    assert client.get(f"/api/projects/{pid}/diff?from=2&to=1").json()["counts"]["stations_removed"] == 1

    svg = client.get(f"/api/projects/{pid}/layout.svg")
    assert svg.headers["content-type"].startswith("image/svg+xml") and "Vision inspection" in svg.text
    assert "SECTION" in client.get(f"/api/projects/{pid}/layout.dxf").text

    plc = client.get(f"/api/projects/{pid}/plc").json()
    assert any(f["name"] == "PRG_Main.st" for f in plc["files"])
    assert client.get(f"/api/projects/{pid}/plc.zip").content[:2] == b"PK"
    assert client.get(f"/api/projects/{pid}/plc.xml").text.startswith("<?xml")
    assert client.get(f"/api/projects/{pid}/rfq.xlsx").content[:2] == b"PK"


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
