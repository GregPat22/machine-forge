from __future__ import annotations

from app.config import Settings
from app.models import Component, MachineDesign, Offer, PriceListEntry, SparePart, Spec, Station
from app.services.sourcing import Sourcing
from app.storage import Storage
from app.suppliers import ConnectorError


class FakeConnector:
    name = "fake"
    label = "Fake Distributor"

    def __init__(self, offers: list[Offer] | None = None, fail: bool = False):
        self.offers = offers or []
        self.fail = fail
        self.calls = 0

    def search(self, part: SparePart, limit: int = 5) -> list[Offer]:
        self.calls += 1
        if self.fail:
            raise ConnectorError("fake is down")
        return [o.model_copy() for o in self.offers if o.part_number == part.part_number]


def _design() -> MachineDesign:
    return MachineDesign(
        name="t", machine_type="t", summary="t", product="t",
        stations=[
            Station(id="s", name="Station", sequence=1, function="f", components=[
                Component(id="sensor", name="Photoelectric sensor", category="sensor", quantity=4,
                          manufacturer="SICK", part_number="WTB4-3P2161", recommended_spares=2),
                Component(id="cyl", name="Pneumatic cylinder", category="pneumatic_actuator", quantity=1,
                          manufacturer="Festo", specs=[Spec(name="bore", value="80 mm")]),
                Component(id="die", name="Forming die", category="custom_part", quantity=1, make_or_buy="make"),
            ]),
        ],
    )


def _sourcing(storage: Storage, connectors: list) -> Sourcing:
    return Sourcing(storage, Settings(fx_rates={"USD": 0.9}), connectors)


def test_compares_current_supplier_with_external_offer() -> None:
    storage = Storage(":memory:")
    storage.replace_price_list([
        PriceListEntry(supplier="Current Srl", manufacturer="SICK", part_number="WTB4 3P2161",
                       unit_price=100.0, currency="EUR", lead_time_days=10),
    ])
    external = FakeConnector([Offer(source="fake", supplier="Distributor X", part_number="WTB4-3P2161",
                                    unit_price=80.0, currency="USD", stock=500, lead_time_days=60)])
    report = _sourcing(storage, [external]).report("p", 1, _design(), external=True)

    sensor = next(line for line in report.lines if line.part.part_number == "WTB4-3P2161")
    assert sensor.current is not None and sensor.current.supplier == "Current Srl"
    assert sensor.best is not None and sensor.best.supplier == "Distributor X"
    assert sensor.best.unit_price_base == 72.0  # 80 USD * 0.9
    assert sensor.savings_base == round((100.0 - 72.0) * 4, 2)
    assert report.connectors_used == ["fake"]
    assert report.total_current_base == 400.0
    assert report.total_best_base == 288.0


def test_make_parts_and_missing_offers_get_notes() -> None:
    report = _sourcing(Storage(":memory:"), []).report("p", 1, _design(), external=False)
    notes = {line.part.name: line.note for line in report.lines}
    assert "machine shops" in notes["Forming die"]
    assert "No offers" in notes["Pneumatic cylinder"]


def test_similar_internal_match_by_description() -> None:
    storage = Storage(":memory:")
    storage.replace_price_list([
        PriceListEntry(supplier="Pneumatica Spa", manufacturer="Festo",
                       description="Pneumatic cylinder bore 80 mm", unit_price=245.0),
    ])
    report = _sourcing(storage, []).report("p", 1, _design(), external=False)
    cylinder = next(line for line in report.lines if line.part.name == "Pneumatic cylinder")
    assert cylinder.current is not None
    assert cylinder.current.match == "similar"
    assert "similar part" in (cylinder.note or "")


def test_connector_errors_are_reported_and_results_cached() -> None:
    storage = Storage(":memory:")
    failing = FakeConnector(fail=True)
    report = _sourcing(storage, [failing]).report("p", 1, _design(), external=True)
    assert report.connector_errors == ["fake is down"]

    working = FakeConnector([Offer(source="fake", supplier="X", part_number="WTB4-3P2161", unit_price=5.0)])
    _sourcing(storage, [working]).report("p", 1, _design(), external=True)
    first_calls = working.calls
    _sourcing(storage, [working]).report("p", 1, _design(), external=True)
    assert working.calls == first_calls  # second report served from cache
