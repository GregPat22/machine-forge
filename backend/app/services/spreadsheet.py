"""Keep untrusted exported labels as data when a spreadsheet opens them."""

from collections.abc import Iterable
from typing import Any


def csv_cell(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def append_text_row(worksheet: Any, values: Iterable[Any]) -> None:
    worksheet.append(list(values))
    for cell in worksheet[worksheet.max_row]:
        if isinstance(cell.value, str):
            cell.data_type = "s"
