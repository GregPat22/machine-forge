from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.suppliers.base import ConnectorError, SupplierConnector

__all__ = ["ConnectorError", "ConnectorStatus", "SupplierConnector", "connector_status", "make_connectors"]


@dataclass
class ConnectorStatus:
    name: str
    label: str
    configured: bool
    covers: str
    setup: str


def connector_status(settings: Settings) -> list[ConnectorStatus]:
    return [
        ConnectorStatus(
            name="mouser",
            label="Mouser Electronics",
            configured=bool(settings.mouser_api_key),
            covers="Electrical/electronic: sensors, PLC I/O, power supplies, connectors, some motion",
            setup="Set MOUSER_API_KEY (free, mouser.com/api-hub)",
        ),
        ConnectorStatus(
            name="nexar",
            label="Nexar / Octopart",
            configured=bool(settings.nexar_client_id and settings.nexar_client_secret),
            covers="Aggregated offers from many distributors (Digi-Key, RS, Farnell, TME, ...)",
            setup="Set NEXAR_CLIENT_ID and NEXAR_CLIENT_SECRET (nexar.com)",
        ),
    ]


def make_connectors(settings: Settings) -> list[SupplierConnector]:
    connectors: list[SupplierConnector] = []
    if settings.mouser_api_key:
        from app.suppliers.mouser import MouserConnector

        connectors.append(MouserConnector(settings.mouser_api_key))
    if settings.nexar_client_id and settings.nexar_client_secret:
        from app.suppliers.nexar import NexarConnector

        connectors.append(NexarConnector(settings.nexar_client_id, settings.nexar_client_secret))
    return connectors
