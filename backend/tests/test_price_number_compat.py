"""Previously supported signs/grouping and malformed values must survive exponent support."""
import csv
import io

import pytest

from app.services.price_list import parse_price_list


@pytest.mark.parametrize(("raw", "expected"), [
    ("1 234,56 €", 1234.56), ("1\u00a0234.56 USD", 1234.56), ("-$1.25", -1.25),
    ("1-", None), ("--1", None), ("1e-", None),
])
def test_existing_price_number_behavior_is_preserved(raw, expected):
    out = io.StringIO()
    csv.writer(out).writerows([["Supplier", "Part number", "Unit price"], ["Test vendor", "ABC", raw]])
    [entry] = parse_price_list("prices.csv", out.getvalue().encode())
    assert entry.unit_price == (pytest.approx(expected) if expected is not None else None)
