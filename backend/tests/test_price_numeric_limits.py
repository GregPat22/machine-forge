"""Nonfinite imported numbers are client errors; a rejected upload changes nothing."""
import csv
import io

from openpyxl import Workbook
import pytest
from fastapi.testclient import TestClient

from app.services.price_list import PriceListError, _number


@pytest.mark.parametrize("field", ["Unit price", "Lead time", "MOQ"])
@pytest.mark.parametrize("raw", ["9" * 400, "1e309", "-1e309"])
def test_nonfinite_csv_numbers_are_rejected_atomically(client, field, raw):
    client = TestClient(client.app, raise_server_exceptions=False)
    initial = b"Supplier,Part number,Unit price\nExisting,OLD,7\n"
    assert client.post("/api/price-list", files={"file": ("initial.csv", initial)}).status_code == 200
    out = io.StringIO()
    csv.writer(out).writerows([["Supplier", "Part number", field], ["Vendor", "ABC", raw]])
    response = client.post("/api/price-list", files={"file": ("prices.csv", out.getvalue().encode())})
    assert response.status_code == 400, response.text
    assert "finite" in response.json()["detail"]
    assert [r["supplier"] for r in client.get("/api/price-list").json()] == ["Existing"]


@pytest.mark.parametrize("value", [float("inf"), -float("inf"), float("nan")])
def test_nonfinite_numeric_cells_are_not_accepted(value):
    with pytest.raises(PriceListError, match="finite"):
        _number(value)


@pytest.mark.parametrize("bad_first", [False, True])
def test_bad_numeric_sheet_cannot_be_silently_skipped(client, bad_first):
    client = TestClient(client.app, raise_server_exceptions=False)
    workbook = Workbook()
    workbook.remove(workbook.active)
    for bad in ([True, False] if bad_first else [False, True]):
        sheet = workbook.create_sheet("Bad" if bad else "Good")
        sheet.append(["Supplier", "Part number", "MOQ"])
        sheet.append(["Vendor", "ABC", "1e309" if bad else 1])
    buffer = io.BytesIO()
    workbook.save(buffer)
    response = client.post("/api/price-list", files={"file": ("prices.xlsx", buffer.getvalue())})
    assert response.status_code == 400, response.text
    assert client.get("/api/price-list").json() == []


@pytest.mark.parametrize("field", ["Lead time", "MOQ"])
@pytest.mark.parametrize("raw", [str(2**63), "1e100"])
def test_integer_values_outside_storage_range_are_client_errors(client, field, raw):
    client = TestClient(client.app, raise_server_exceptions=False)
    data = f"Supplier,Part number,{field}\nVendor,ABC,{raw}\n".encode()
    response = client.post("/api/price-list", files={"file": ("prices.csv", data)})
    assert response.status_code == 400, response.text
    assert "64-bit" in response.json()["detail"]
