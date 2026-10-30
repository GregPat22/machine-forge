"""An exact external match describes the returned identity, not the kind of query."""
import httpx
import pytest

from app.config import Settings
from app.models import Component, MachineDesign, Offer, Station
from app.services.sourcing import Sourcing
from app.services.spare_parts import build_catalog
from app.suppliers.mouser import MouserConnector
from app.suppliers.nexar import NexarConnector


def _design(manufacturer="Maker A", pn="ABC-123"):
    return MachineDesign(name="Test", machine_type="test", summary="test", stations=[
        Station(id="st", name="Test", function="Test", components=[
            Component(id="part", name="Sensor", category="sensor", quantity=1,
                      manufacturer=manufacturer, part_number=pn)])])


@pytest.mark.parametrize("connector_kind", ["mouser", "nexar"])
@pytest.mark.parametrize(("manufacturer", "pn", "expected"), [
    ("Maker B", "ABC-123", "similar"), (None, "ABC-123", "similar"),
    ("Maker A", "DIFFERENT", "similar"), ("Maker A", None, "similar"),
    (" maker a ", "abc 123", "exact"),
])
def test_connector_checks_the_returned_identity(connector_kind, manufacturer, pn, expected):
    def handler(request):
        if request.url.path.endswith("/connect/token"):
            return httpx.Response(200, json={"access_token": "test", "expires_in": 3600})
        if connector_kind == "mouser":
            return httpx.Response(200, json={"SearchResults": {"Parts": [{
                "Manufacturer": manufacturer, "ManufacturerPartNumber": pn,
                "PriceBreaks": [{"Price": "1.00", "Currency": "EUR"}]}]}})
        return httpx.Response(200, json={"data": {"supSearchMpn": {"results": [{"part": {
            "mpn": pn, "manufacturer": {"name": manufacturer}, "sellers": [{"company": {"name": "Vendor"},
            "offers": [{"prices": [{"quantity": 1, "price": 1, "currency": "EUR"}]}]}]}}]}}})

    transport = httpx.MockTransport(handler)
    connector = (MouserConnector("test", transport=transport) if connector_kind == "mouser"
                 else NexarConnector("test", "test", transport=transport))
    [offer] = connector.search(build_catalog(_design())[0])
    assert offer.match == expected


@pytest.mark.parametrize(("manufacturer", "pn"), [("Maker B", "ABC-123"), ("Maker A", "OTHER")])
def test_old_cached_exact_labels_are_revalidated_for_the_requested_part(storage, manufacturer, pn):
    class CachedConnector:
        name = "recorded"
        label = "Recorded test vendor"

        def search(self, part, limit=5):
            raise AssertionError("This test must use the old cache entry")

    storage.cache_offers("recorded", "ABC-123", [Offer(
        source="recorded", supplier="Test vendor", manufacturer=manufacturer, part_number=pn,
        match="exact", unit_price=1, currency="EUR")])
    report = Sourcing(storage, Settings(), [CachedConnector()]).report("test", 1, _design(), external=True)
    [line] = report.lines
    assert line.offers[0].match == "similar"
    assert "not an exact" in line.note
