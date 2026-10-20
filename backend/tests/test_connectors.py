"""Connector parsing against recorded-shape payloads (no network, no keys)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.models import SparePart
from app.suppliers import ConnectorError
from app.suppliers.base import parse_price
from app.suppliers.mouser import MouserConnector
from app.suppliers.nexar import NexarConnector


def _part(part_number: str | None = "WTB4-3P2161") -> SparePart:
    return SparePart(
        item=1, key="k", name="Photoelectric sensor", category="sensor", specs=[], manufacturer="SICK",
        part_number=part_number, make_or_buy="buy", quantity_in_machine=4, used_in=["S"], component_ids=["c"],
        wear_part=False, criticality="B", recommended_spares=1,
    )


def test_parse_price_formats() -> None:
    assert parse_price("$1,234.56") == 1234.56
    assert parse_price("1.234,56 €") == 1234.56
    assert parse_price("12,5") == 12.5
    assert parse_price(None) is None


def test_mouser_part_number_search() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "Errors": [],
            "SearchResults": {"NumberOfResult": 1, "Parts": [{
                "Manufacturer": "SICK", "ManufacturerPartNumber": "WTB4-3P2161",
                "Description": "Photoelectric Sensors", "Min": "1", "AvailabilityInStock": "57",
                "LeadTime": "56 Days", "ProductDetailUrl": "https://www.mouser.com/x",
                "PriceBreaks": [{"Quantity": 1, "Price": "123,45 €", "Currency": "EUR"},
                                {"Quantity": 10, "Price": "110,00 €", "Currency": "EUR"}],
            }]},
        })

    connector = MouserConnector("key", transport=httpx.MockTransport(handler))
    [offer] = connector.search(_part())
    assert "/search/partnumber" in seen["url"] and "apiKey=key" in seen["url"]
    assert seen["body"]["SearchByPartRequest"]["mouserPartNumber"] == "WTB4-3P2161"
    assert offer.unit_price == 123.45 and offer.currency == "EUR"
    assert offer.stock == 57 and offer.lead_time_days == 56 and offer.match == "exact"


def test_mouser_errors_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Errors": [{"Message": "Invalid API key"}], "SearchResults": None})

    with pytest.raises(ConnectorError, match="Invalid API key"):
        MouserConnector("bad", transport=httpx.MockTransport(handler)).search(_part(None))


def test_nexar_token_then_query() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "identity.nexar.com":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer tok"
        body = json.loads(request.content)
        assert "supSearchMpn" in body["query"]
        return httpx.Response(200, json={"data": {"supSearchMpn": {"results": [{"part": {
            "mpn": "WTB4-3P2161", "shortDescription": "Sensor", "manufacturer": {"name": "SICK"},
            "sellers": [
                {"company": {"name": "Digi-Key"}, "offers": [{
                    "clickUrl": "https://dk", "inventoryLevel": 0, "moq": 1, "factoryLeadDays": 70,
                    "prices": [{"quantity": 10, "price": 95.0, "currency": "USD"},
                               {"quantity": 1, "price": 99.0, "currency": "USD"}]}]},
                {"company": {"name": "RS"}, "offers": [{
                    "clickUrl": "https://rs", "inventoryLevel": 20, "moq": 1, "factoryLeadDays": None,
                    "prices": [{"quantity": 1, "price": 105.0, "currency": "EUR"}]}]},
            ]}}]}}})

    connector = NexarConnector("id", "secret", transport=httpx.MockTransport(handler))
    offers = connector.search(_part())
    assert calls == ["identity.nexar.com", "api.nexar.com"]
    assert [o.supplier for o in offers] == ["RS", "Digi-Key"]  # in-stock first
    assert offers[1].unit_price == 99.0  # price at the smallest quantity break
    connector.search(_part())
    assert calls.count("identity.nexar.com") == 1  # token reused
