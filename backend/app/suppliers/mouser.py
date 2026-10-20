"""Mouser Search API (free key from mouser.com/api-hub; 30 calls/min, 1000 calls/day)."""

from __future__ import annotations

import httpx

from app.models import Offer, SparePart
from app.suppliers.base import ConnectorError, parse_int, parse_price, search_query

BASE_URL = "https://api.mouser.com/api/v1"


class MouserConnector:
    name = "mouser"
    label = "Mouser Electronics"

    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None):
        self._api_key = api_key
        self._http = httpx.Client(base_url=BASE_URL, timeout=20.0, transport=transport)

    def search(self, part: SparePart, limit: int = 5) -> list[Offer]:
        query, by_pn = search_query(part)
        if by_pn:
            path = "/search/partnumber"
            body = {"SearchByPartRequest": {"mouserPartNumber": query, "partSearchOptions": "Exact"}}
        else:
            path = "/search/keyword"
            body = {"SearchByKeywordRequest": {"keyword": query, "records": limit, "startingRecord": 0}}
        try:
            response = self._http.post(path, params={"apiKey": self._api_key}, json=body)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorError(f"Mouser request failed: {exc}") from exc

        data = response.json()
        errors = data.get("Errors") or []
        if errors:
            raise ConnectorError("Mouser: " + "; ".join(str(e.get("Message", e)) for e in errors))

        offers: list[Offer] = []
        for item in ((data.get("SearchResults") or {}).get("Parts") or [])[:limit]:
            breaks = item.get("PriceBreaks") or []
            first = breaks[0] if breaks else {}
            offers.append(
                Offer(
                    source=self.name,
                    supplier=self.label,
                    manufacturer=item.get("Manufacturer"),
                    part_number=item.get("ManufacturerPartNumber"),
                    description=item.get("Description"),
                    unit_price=parse_price(first.get("Price")),
                    currency=first.get("Currency"),
                    moq=parse_int(item.get("Min")),
                    stock=parse_int(item.get("AvailabilityInStock")),
                    lead_time_days=parse_int(item.get("LeadTime")),
                    url=item.get("ProductDetailUrl"),
                    match="exact" if by_pn else "similar",
                )
            )
        return offers
