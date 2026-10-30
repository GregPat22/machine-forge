"""Mouser errors may reach the engineer; authenticated request URLs must not."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.llm.mock import MockProvider, demo_design
from app.main import create_app
from app.suppliers.base import ConnectorError
from app.suppliers.mouser import MouserConnector
from app.services.spare_parts import build_catalog

KEY = "synthetic-review-key"


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_errors_keep_status_without_api_credentials(status):
    connector = MouserConnector(KEY, transport=httpx.MockTransport(lambda r: httpx.Response(status)))
    part = build_catalog(demo_design())[0]
    with pytest.raises(ConnectorError) as caught:
        connector.search(part)
    message = str(caught.value)
    assert KEY not in message and "apiKey=" not in message, message
    assert str(status) in message


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
def test_transport_error_details_cannot_expose_the_request_url(error):
    def handler(request):
        raise error(f"Failed authenticated request: {request.url}", request=request)

    connector = MouserConnector(KEY, transport=httpx.MockTransport(handler))
    with pytest.raises(ConnectorError) as caught:
        connector.search(build_catalog(demo_design())[0])
    assert KEY not in str(caught.value) and "apiKey=" not in str(caught.value)


def test_sourcing_api_does_not_return_mouser_credentials(settings, storage):
    pid = storage.create_project("Synthetic machine", "Test reply", demo_design())
    connector = MouserConnector(KEY, transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    client = TestClient(create_app(settings=settings, storage=storage, provider=MockProvider(), connectors=[connector]))
    response = client.get(f"/api/projects/{pid}/sourcing?external=true")
    assert response.status_code == 200
    assert response.json()["connector_errors"]
    assert KEY not in response.text and "apiKey=" not in response.text
