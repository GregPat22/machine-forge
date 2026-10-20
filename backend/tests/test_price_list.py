from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from app.services.price_list import PriceListError, parse_price_list


def test_italian_csv_with_semicolons_and_decimal_comma() -> None:
    data = (
        "Fornitore;Produttore;Codice articolo;Descrizione;Prezzo unitario;Tempo di consegna;Lotto minimo\n"
        "Elettro Srl;Siemens;6ES7515-2AM02-0AB0;CPU S7-1500;1.980,50;10;1\n"
        ";;;;;;\n"
        "Pneumatica Spa;Festo;;Cilindro alesaggio 80 corsa 50;245,00;15 giorni;\n"
    ).encode("utf-8")
    entries = parse_price_list("listino.csv", data)
    assert len(entries) == 2
    cpu, cylinder = entries
    assert cpu.supplier == "Elettro Srl"
    assert cpu.unit_price == 1980.5
    assert cpu.lead_time_days == 10
    assert cpu.currency == "EUR"
    assert cylinder.part_number is None
    assert cylinder.lead_time_days == 15


def test_xlsx_with_english_headers() -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["Supplier", "Manufacturer", "MPN", "Price", "Currency", "Lead time"])
    ws.append(["RS", "SICK", "WTB4-3P2161", 89.9, "usd", 5])
    buf = io.BytesIO()
    wb.save(buf)
    [entry] = parse_price_list("prices.xlsx", buf.getvalue())
    assert entry.part_number == "WTB4-3P2161"
    assert entry.unit_price == 89.9
    assert entry.currency == "USD"


def test_missing_supplier_column() -> None:
    with pytest.raises(PriceListError):
        parse_price_list("x.csv", b"code,price\nA,1\n")


def test_unsupported_extension() -> None:
    with pytest.raises(PriceListError):
        parse_price_list("x.pdf", b"%PDF")
