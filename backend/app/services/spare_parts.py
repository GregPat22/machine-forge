"""Derive the spare-parts catalog (an aggregated BOM) from a machine design."""

from __future__ import annotations

import csv
import io

from app.models import MachineDesign, SparePart

_CRITICALITY_RANK = {"A": 0, "B": 1, "C": 2}


def normalize_pn(part_number: str | None) -> str:
    return "".join(ch for ch in (part_number or "").upper() if ch.isalnum())


def _key(manufacturer: str | None, part_number: str | None, component_id: str) -> str:
    if part_number:
        return f"{(manufacturer or '').strip().lower()}|{normalize_pn(part_number)}"
    return f"id|{component_id}"


def build_catalog(design: MachineDesign) -> list[SparePart]:
    """One line per distinct part. Identical part numbers used in several stations are merged."""
    parts: dict[str, SparePart] = {}
    station_ids: dict[str, list[str]] = {}  # stations a part is used in, by id (names are display only)
    stations = sorted(design.stations, key=lambda s: (s.sequence == 0, s.sequence))
    for station in stations:
        for comp in station.components:
            key = _key(comp.manufacturer, comp.part_number, comp.id)
            existing = parts.get(key)
            if existing is None:
                parts[key] = SparePart(
                    item=0,
                    key=key,
                    name=comp.name,
                    category=comp.category,
                    specs=comp.specs,
                    manufacturer=comp.manufacturer,
                    part_number=comp.part_number,
                    make_or_buy=comp.make_or_buy,
                    quantity_in_machine=comp.quantity,
                    used_in=[station.name],
                    component_ids=[comp.id],
                    wear_part=comp.wear_part,
                    criticality=comp.criticality,
                    recommended_spares=comp.recommended_spares,
                )
                station_ids[key] = [station.id]
                continue
            existing.quantity_in_machine += comp.quantity
            existing.recommended_spares = max(existing.recommended_spares, comp.recommended_spares)
            existing.wear_part = existing.wear_part or comp.wear_part
            if _CRITICALITY_RANK[comp.criticality] < _CRITICALITY_RANK[existing.criticality]:
                existing.criticality = comp.criticality
            if station.id not in station_ids[key]:
                station_ids[key].append(station.id)
                existing.used_in.append(station.name)
            existing.component_ids.append(comp.id)

    for item, part in enumerate(parts.values(), start=1):
        part.item = item
    return list(parts.values())


def catalog_csv(parts: list[SparePart]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "Item", "Name", "Category", "Manufacturer", "Part number", "Make/Buy", "Qty in machine",
        "Recommended spares", "Wear part", "Criticality", "Used in", "Specs",
    ])
    for p in parts:
        writer.writerow([
            p.item, p.name, p.category, p.manufacturer or "", p.part_number or "", p.make_or_buy,
            p.quantity_in_machine, p.recommended_spares, "yes" if p.wear_part else "no", p.criticality,
            "; ".join(p.used_in), "; ".join(f"{s.name}: {s.value}" for s in p.specs),
        ])
    return out.getvalue()
