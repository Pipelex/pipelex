"""Excel workbooks built in code for the tests of the spreadsheet readers: Tables of rows, no binary fixture committed.

A workbook openpyxl writes stores no cached value for a formula, which is what `formula_with_cached_value` patches in.
"""

import io
import re
import zipfile
from typing import Any

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table


def add_table(
    *,
    workbook: Workbook,
    sheet_title: str,
    table_name: str,
    header: list[str],
    rows: list[list[Any]],
    top_row: int = 1,
    left_column: int = 1,
    totals_row: list[Any] | None = None,
) -> None:
    """Write a header and rows on a sheet (created when missing) and define an Excel Table over them."""
    if sheet_title in workbook.sheetnames:
        worksheet = workbook[sheet_title]
    else:
        worksheet = workbook.create_sheet(title=sheet_title)
    all_rows: list[list[Any]] = [header, *rows]
    if totals_row is not None:
        all_rows.append(totals_row)
    for row_offset, row_values in enumerate(all_rows):
        for column_offset, cell_value in enumerate(row_values):
            worksheet.cell(row=top_row + row_offset, column=left_column + column_offset, value=cell_value)
    first_cell = f"{get_column_letter(left_column)}{top_row}"
    last_cell = f"{get_column_letter(left_column + len(header) - 1)}{top_row + len(all_rows) - 1}"
    table = Table(displayName=table_name, ref=f"{first_cell}:{last_cell}")
    if totals_row is not None:
        table.totalsRowCount = 1
    worksheet.add_table(table)


def empty_workbook() -> Workbook:
    """A workbook with its default sheet removed, for `add_table` to fill."""
    workbook = Workbook()
    default_sheet = workbook.active
    if default_sheet is not None:
        workbook.remove(default_sheet)
    return workbook


def workbook_bytes(workbook: Workbook) -> bytes:
    """The bytes of a workbook, as a `.xlsx` file holds them."""
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def single_table_workbook(*, header: list[str], rows: list[list[Any]], table_name: str = "Rows", totals_row: list[Any] | None = None) -> bytes:
    """The bytes of a workbook holding one sheet with one Table."""
    workbook = empty_workbook()
    add_table(workbook=workbook, sheet_title="Sheet1", table_name=table_name, header=header, rows=rows, totals_row=totals_row)
    return workbook_bytes(workbook)


def formula_with_cached_value(*, xlsx_bytes: bytes, cached_value: str) -> bytes:
    """Give every formula of the first sheet a cached value, as Excel stores one when it saves."""
    source = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                text = content.decode("utf-8")
                text = re.sub(r"(<f>[^<]*</f>)<v\s*/>", rf"\1<v>{cached_value}</v>", text)
                text = re.sub(r"(<f>[^<]*</f>)<v></v>", rf"\1<v>{cached_value}</v>", text)
                text = re.sub(r"(<f>[^<]*</f>)(?!<v)", rf"\1<v>{cached_value}</v>", text)
                content = text.encode("utf-8")
            target.writestr(item, content)
    return buffer.getvalue()
