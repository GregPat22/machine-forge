"""CSV/Excel scientific notation must reach sourcing with its original numeric value."""
import csv
import io

from openpyxl import Workbook
import pytest

from app.services.price_list import parse_price_list


@pytest.mark.parametrize(("raw", "expected"), [
    ("1e3", 1000), ("1.2E+03", 1200), ("1e-3", .001), (".5e2", 50),
    ("1.e3", 1000), ("+1.2e1", 12), ("EUR 1.2e3", 1200), ("1,2e3 €", 1200),
    ("1.234,5e-2", 12.345), ("1,234.5E-2 USD", 12.345),
])
@pytest.mark.parametrize("file_format", ["csv", "xlsx"])
def test_import_preserves_scientific_notation(raw, expected, file_format):
    rows = [["Supplier", "Part number", "Unit price", "Currency"], ["Vendor", "ABC", raw, "EUR"]]
    if file_format == "csv":
        out = io.StringIO()
        csv.writer(out).writerows(rows)
        data = out.getvalue().encode()
    else:
        workbook = Workbook()
        for row in rows:
            workbook.active.append(row)
        buffer = io.BytesIO()
        workbook.save(buffer)
        data = buffer.getvalue()
    [entry] = parse_price_list(f"prices.{file_format}", data)
    assert entry.unit_price == pytest.approx(expected)


def test_price_list_api_returns_the_same_numeric_value(client):
    response = client.post("/api/price-list", files={"file": (
        "prices.csv", b"Supplier,Part number,Unit price,Currency\nVendor,ABC,1.2E+03,EUR\n")})
    assert response.status_code == 200
    assert client.get("/api/price-list").json()[0]["unit_price"] == 1200
