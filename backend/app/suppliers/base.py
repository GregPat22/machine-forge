"""External supplier connectors: search a distributor for offers matching a spare part."""

from __future__ import annotations

import re
from typing import Protocol

from app.models import Offer, SparePart


class ConnectorError(RuntimeError):
    pass


class SupplierConnector(Protocol):
    name: str
    label: str

    def search(self, part: SparePart, limit: int = 5) -> list[Offer]:
        """Offers for this part, best matches first. Raise ConnectorError on API failure."""
        ...


def search_query(part: SparePart) -> tuple[str, bool]:
    """(query, is_part_number): search by part number when known, otherwise by keywords."""
    if part.part_number:
        return part.part_number, True
    words = [part.manufacturer or "", part.name, *(s.value for s in part.specs[:2])]
    return " ".join(w for w in words if w).strip(), False


def exact_part_match(part: SparePart, manufacturer: str | None, part_number: str | None) -> bool:
    """Verify returned identity, including the manufacturer when the engineer specified it.

    Missing vendor identity is unverified, not exact. Whitespace/case and part-number
    punctuation are normalized as in the internal price-list match.
    """
    wanted = "".join(c for c in (part.part_number or "").upper() if c.isalnum())
    returned = "".join(c for c in (part_number or "").upper() if c.isalnum())
    return bool(wanted) and wanted == returned and (
        not part.manufacturer or part.manufacturer.strip().casefold() == (manufacturer or "").strip().casefold()
    )


def parse_int(text: object) -> int | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    match = re.search(r"\d[\d.,]*", str(text))
    if not match:
        return None
    return int(re.sub(r"[.,]", "", match.group(0)))


def parse_price(text: object) -> float | None:
    """'$1,234.56', '1.234,56 €' or 12.5 -> float."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    raw = re.sub(r"[^\d,.]", "", str(text))
    if not raw:
        return None
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None
