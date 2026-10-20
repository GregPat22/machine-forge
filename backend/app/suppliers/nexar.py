"""Nexar (Octopart) supply API: one integration, offers from hundreds of distributors.

Client credentials come from nexar.com (free tier with a monthly part limit).
"""

from __future__ import annotations

import time

import httpx

from app.models import Offer, SparePart
from app.suppliers.base import ConnectorError, search_query

TOKEN_URL = "https://identity.nexar.com/connect/token"
GRAPHQL_URL = "https://api.nexar.com/graphql"

_PART_FIELDS = """
  part {
    mpn
    shortDescription
    manufacturer { name }
    sellers(authorizedOnly: true) {
      company { name }
      offers {
        clickUrl
        inventoryLevel
        moq
        factoryLeadDays
        prices { quantity price currency }
      }
    }
  }
"""

MPN_QUERY = "query ($q: String!, $limit: Int) { supSearchMpn(q: $q, limit: $limit) { results {%s} } }" % _PART_FIELDS
KEYWORD_QUERY = "query ($q: String!, $limit: Int) { supSearch(q: $q, limit: $limit) { results {%s} } }" % _PART_FIELDS


class NexarConnector:
    name = "nexar"
    label = "Nexar / Octopart"

    def __init__(self, client_id: str, client_secret: str, transport: httpx.BaseTransport | None = None):
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = httpx.Client(timeout=30.0, transport=transport)
        self._token: str | None = None
        self._token_expires = 0.0

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        try:
            response = self._http.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "supply.domain",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorError(f"Nexar authentication failed: {exc}") from exc
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expires = time.time() + float(payload.get("expires_in", 3600))
        return self._token

    def search(self, part: SparePart, limit: int = 5) -> list[Offer]:
        query, by_pn = search_query(part)
        try:
            response = self._http.post(
                GRAPHQL_URL,
                headers={"Authorization": f"Bearer {self._access_token()}"},
                json={"query": MPN_QUERY if by_pn else KEYWORD_QUERY, "variables": {"q": query, "limit": 3}},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorError(f"Nexar request failed: {exc}") from exc

        data = response.json()
        if data.get("errors"):
            raise ConnectorError("Nexar: " + "; ".join(e.get("message", "error") for e in data["errors"]))
        root = (data.get("data") or {}).get("supSearchMpn" if by_pn else "supSearch") or {}

        offers: list[Offer] = []
        for result in root.get("results") or []:
            p = result.get("part") or {}
            for seller in p.get("sellers") or []:
                for offer in seller.get("offers") or []:
                    prices = sorted(offer.get("prices") or [], key=lambda pp: pp.get("quantity") or 0)
                    if not prices:
                        continue
                    offers.append(
                        Offer(
                            source=self.name,
                            supplier=(seller.get("company") or {}).get("name") or "unknown",
                            manufacturer=(p.get("manufacturer") or {}).get("name"),
                            part_number=p.get("mpn"),
                            description=p.get("shortDescription"),
                            unit_price=prices[0].get("price"),
                            currency=prices[0].get("currency"),
                            moq=offer.get("moq"),
                            stock=offer.get("inventoryLevel"),
                            lead_time_days=offer.get("factoryLeadDays"),
                            url=offer.get("clickUrl"),
                            match="exact" if by_pn else "similar",
                        )
                    )
        # Keep the cheapest offers in stock first; the sourcing service scores them properly.
        offers.sort(key=lambda o: ((o.stock or 0) <= 0, o.unit_price if o.unit_price is not None else float("inf")))
        return offers[:limit]
