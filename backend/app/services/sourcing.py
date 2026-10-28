"""Compare your current suppliers (imported price list) with external offers, part by part."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from app.config import Settings
from app.models import (
    MachineDesign,
    Offer,
    PriceListEntry,
    SourcingLine,
    SourcingReport,
    SparePart,
    SupplierRating,
)
from app.services.spare_parts import build_catalog, normalize_pn
from app.storage import Storage
from app.suppliers import ConnectorError, SupplierConnector
from app.suppliers.base import search_query

# Days to deliver an offer that is in stock at the distributor.
IN_STOCK_LEAD_DAYS = 3
SIMILAR_MATCH_PENALTY = 0.8
_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 1}


def _similar(part: SparePart, entry: PriceListEntry) -> bool:
    if part.manufacturer and entry.manufacturer and part.manufacturer.lower() != entry.manufacturer.lower():
        return False
    wanted = _tokens(" ".join([part.name, *(f"{s.name} {s.value}" for s in part.specs)]))
    offered = _tokens(entry.description or "")
    if not wanted or not offered:
        return False
    return len(wanted & offered) / len(wanted | offered) >= 0.5


def internal_offers(part: SparePart, price_list: list[PriceListEntry]) -> list[Offer]:
    pn = normalize_pn(part.part_number)
    exact = [e for e in price_list if pn and normalize_pn(e.part_number) == pn
             and (not part.manufacturer or not e.manufacturer
                  or part.manufacturer.strip().casefold() == e.manufacturer.strip().casefold())]
    entries, match = (exact, "exact") if exact else ([e for e in price_list if _similar(part, e)], "similar")
    return [
        Offer(
            source="internal",
            supplier=e.supplier,
            manufacturer=e.manufacturer,
            part_number=e.part_number,
            description=e.description,
            unit_price=e.unit_price,
            currency=e.currency,
            moq=e.moq,
            lead_time_days=e.lead_time_days,
            match=match,  # type: ignore[arg-type]
            is_current=True,
        )
        for e in entries
    ]


class Sourcing:
    def __init__(self, storage: Storage, settings: Settings, connectors: list[SupplierConnector]):
        self.storage = storage
        self.settings = settings
        self.connectors = connectors

    def report(self, project_id: str, revision: int, design: MachineDesign, external: bool) -> SourcingReport:
        parts = build_catalog(design)
        price_list = self.storage.price_list()
        ratings = self.storage.ratings()
        to_buy = [p for p in parts if p.make_or_buy == "buy"]
        external_offers, errors = self._external(to_buy) if external else ({}, [])

        lines: list[SourcingLine] = []
        for part in parts:
            if part.make_or_buy == "make":
                lines.append(SourcingLine(part=part, offers=[], current=None, best=None,
                                          note="Custom part: quote it with your machine shops."))
                continue
            offers = internal_offers(part, price_list) + external_offers.get(part.key, [])
            lines.append(self._line(part, offers, ratings))

        def total(attr: str) -> float | None:
            values = [
                getattr(line, attr).unit_price_base * line.part.quantity_in_machine
                for line in lines
                if getattr(line, attr) is not None and getattr(line, attr).unit_price_base is not None
            ]
            return round(sum(values), 2) if values else None

        return SourcingReport(
            project_id=project_id,
            revision=revision,
            base_currency=self.settings.base_currency,
            lines=lines,
            connectors_used=[c.name for c in self.connectors] if external else [],
            connector_errors=errors,
            total_current_base=total("current"),
            total_best_base=total("best"),
        )

    # --- external offers ------------------------------------------------------------------

    def _external(self, parts: list[SparePart]) -> tuple[dict[str, list[Offer]], list[str]]:
        results: dict[str, list[Offer]] = {p.key: [] for p in parts}
        errors: dict[str, str] = {}
        pending: list[tuple[SupplierConnector, SparePart, str]] = []
        for connector in self.connectors:
            for part in parts:
                query = search_query(part)[0]
                cached = self.storage.cached_offers(connector.name, query, self.settings.offer_cache_hours)
                if cached is None:
                    pending.append((connector, part, query))
                else:
                    results[part.key].extend(cached)

        def run(job: tuple[SupplierConnector, SparePart, str]) -> list[Offer] | None:
            connector, part, _query = job
            if connector.name in errors:  # stop calling a connector once it failed
                return None
            try:
                return connector.search(part)
            except ConnectorError as exc:
                errors.setdefault(connector.name, str(exc))
                return None

        with ThreadPoolExecutor(max_workers=4) as pool:
            for (connector, part, query), offers in zip(pending, pool.map(run, pending)):
                if offers is None:
                    continue
                self.storage.cache_offers(connector.name, query, offers)
                results[part.key].extend(offers)
        return results, list(errors.values())

    # --- scoring --------------------------------------------------------------------------

    def _to_base(self, price: float | None, currency: str | None) -> float | None:
        if price is None:
            return None
        code = (currency or self.settings.base_currency).upper()
        if code == self.settings.base_currency:
            return round(price, 4)
        rate = self.settings.fx_rates.get(code)
        return round(price * rate, 4) if rate is not None else None

    def _line(self, part: SparePart, offers: list[Offer], ratings: dict[str, SupplierRating]) -> SourcingLine:
        needed = part.quantity_in_machine + part.recommended_spares
        for offer in offers:
            offer.unit_price_base = self._to_base(offer.unit_price, offer.currency)
            rating = ratings.get(offer.supplier.lower())
            if rating:
                stars = [x for x in (rating.quality, rating.delivery) if x]
                offer.rating = round(sum(stars) / len(stars), 1) if stars else None
                offer.preferred = rating.preferred

        priced = [o for o in offers if o.unit_price_base is not None and o.unit_price_base > 0]
        if priced:
            min_price = min(o.unit_price_base for o in priced)  # type: ignore[type-var]

            def lead(o: Offer) -> int | None:
                if o.stock is not None and o.stock >= needed:
                    return IN_STOCK_LEAD_DAYS
                return o.lead_time_days

            leads = [lt for o in priced if (lt := lead(o)) is not None]
            min_lead = max(min(leads), 1) if leads else None
            s = self.settings
            weight_sum = s.weight_price + s.weight_lead_time + s.weight_availability + s.weight_rating or 1.0
            for o in priced:
                price_score = min_price / o.unit_price_base  # type: ignore[operator]
                lt = lead(o)
                lead_score = 0.5 if lt is None or min_lead is None else min_lead / max(lt, 1)
                if o.stock is None:
                    avail_score = 0.5
                elif o.stock >= needed:
                    avail_score = 1.0
                else:
                    avail_score = 0.5 if o.stock > 0 else 0.0
                # Unrated suppliers count as average (3 of 5 stars).
                rating_score = (o.rating - 1) / 4 if o.rating is not None else 0.5
                score = (s.weight_price * price_score + s.weight_lead_time * lead_score
                         + s.weight_availability * avail_score + s.weight_rating * rating_score) / weight_sum
                if o.match == "similar":
                    score *= SIMILAR_MATCH_PENALTY
                o.score = round(score, 3)

        # Preferred suppliers win ties.
        offers.sort(key=lambda o: (o.score if o.score is not None else -1, o.preferred), reverse=True)
        current_offers = [o for o in offers if o.is_current]
        current = current_offers[0] if current_offers else None
        best = offers[0] if offers and offers[0].score is not None else None

        savings = None
        note = None
        if current and best and current is not best and current.unit_price_base and best.unit_price_base:
            savings = round((current.unit_price_base - best.unit_price_base) * part.quantity_in_machine, 2)
        if not offers:
            note = "No offers: import your price list or configure a supplier connector."
        elif best is None:
            note = "Offers found, but none with a usable price."
        elif best.match == "similar":
            note = "Best offer is a similar part, not an exact part-number match: check it."
        return SourcingLine(part=part, offers=offers, current=current, best=best, savings_base=savings, note=note)
