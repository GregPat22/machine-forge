"""Import your own supplier price list from CSV or Excel.

Column names are matched loosely (English or Italian), so most ERP exports work as-is.
"""

from __future__ import annotations

import csv
import io
import re

from app.models import PriceListEntry

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "supplier": ("supplier", "vendor", "fornitore", "ragione sociale"),
    "manufacturer": ("manufacturer", "brand", "make", "produttore", "costruttore", "marca"),
    "part_number": ("part number", "partnumber", "mpn", "part no", "pn", "codice", "codice articolo",
                    "codice produttore", "article", "articolo", "item code"),
    "description": ("description", "descrizione", "desc", "name", "nome"),
    "unit_price": ("unit price", "price", "prezzo", "prezzo unitario", "cost", "costo"),
    "currency": ("currency", "valuta", "divisa"),
    "lead_time_days": ("lead time", "lead time days", "leadtime", "lead time (days)", "consegna",
                       "tempo di consegna", "giorni consegna"),
    "moq": ("moq", "min qty", "minimum order", "lotto minimo", "quantita minima"),
}


class PriceListError(ValueError):
    pass


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9() ]", "", header.strip().lower().replace("_", " ").replace("à", "a"))


def _map_columns(headers: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    normalized = [_norm(h or "") for h in headers]
    for field, aliases in COLUMN_ALIASES.items():
        for idx, name in enumerate(normalized):
            if name in aliases:
                mapping[field] = idx
                break
    if "supplier" not in mapping:
        raise PriceListError("Missing a supplier column (e.g. 'Supplier' or 'Fornitore').")
    if "part_number" not in mapping and "description" not in mapping:
        raise PriceListError("Need a part number or a description column to match parts.")
    return mapping


def _number(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[^\d,.\-]", "", str(value))
    if not text:
        return None
    # "1.234,56" (Italian) and "1,234.56" (English) both become 1234.56.
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _rows_from_csv(data: bytes) -> list[list[object]]:
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    return [list(row) for row in csv.reader(io.StringIO(text), dialect)]


def _rows_from_xlsx(data: bytes) -> list[list[object]]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def parse_price_list(filename: str, data: bytes, default_currency: str = "EUR") -> list[PriceListEntry]:
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xlsm")):
        rows = _rows_from_xlsx(data)
    elif lower.endswith((".csv", ".txt")):
        rows = _rows_from_csv(data)
    else:
        raise PriceListError("Upload a .csv or .xlsx file.")

    rows = [r for r in rows if any(_text(c) for c in r)]
    if len(rows) < 2:
        raise PriceListError("The file has no data rows.")
    mapping = _map_columns([str(h) if h is not None else "" for h in rows[0]])

    def cell(row: list[object], field: str) -> object:
        idx = mapping.get(field)
        return row[idx] if idx is not None and idx < len(row) else None

    entries: list[PriceListEntry] = []
    for row in rows[1:]:
        supplier = _text(cell(row, "supplier"))
        part_number = _text(cell(row, "part_number"))
        description = _text(cell(row, "description"))
        if not supplier or not (part_number or description):
            continue
        lead = _number(cell(row, "lead_time_days"))
        moq = _number(cell(row, "moq"))
        entries.append(
            PriceListEntry(
                supplier=supplier,
                manufacturer=_text(cell(row, "manufacturer")),
                part_number=part_number,
                description=description,
                unit_price=_number(cell(row, "unit_price")),
                currency=(_text(cell(row, "currency")) or default_currency).upper(),
                lead_time_days=int(lead) if lead is not None else None,
                moq=int(moq) if moq is not None else None,
                source_file=filename,
            )
        )
    if not entries:
        raise PriceListError("No usable rows: each row needs a supplier and a part number or description.")
    return entries
