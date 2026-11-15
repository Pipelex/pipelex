"""Excel workbooks built in code for the tests of the spreadsheet readers: Tables of rows, no binary fixture committed.

A workbook openpyxl writes stores no cached value for a formula, which is what `formula_with_cached_value` patches in.
"""

import io
import re
import zipfile
from collections.abc import Callable
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


def with_part_rewritten(*, xlsx_bytes: bytes, part_name: str, rewrite: Callable[[bytes], bytes]) -> bytes:
    """The bytes of a workbook whose part `part_name` is rewritten, the other parts kept as they are."""
    source = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == part_name:
                content = rewrite(content)
            target.writestr(item, content)
    return buffer.getvalue()


def with_table_ref(*, xlsx_bytes: bytes, ref: str) -> bytes:
    """The bytes of a workbook whose first Table declares the range `ref`, whatever cells its sheet holds."""

    def _rewrite(content: bytes) -> bytes:
        return re.sub(rb'ref="[A-Z]+[0-9]+:[A-Z]+[0-9]+"', f'ref="{ref}"'.encode(), content)

    return with_part_rewritten(xlsx_bytes=xlsx_bytes, part_name="xl/tables/table1.xml", rewrite=_rewrite)


def formula_with_cached_text(*, xlsx_bytes: bytes, cached_text: str) -> bytes:
    """Give every formula of the first sheet a cached text value, typed `str` as Excel stores a formula's text result."""

    def _rewrite(content: bytes) -> bytes:
        text = content.decode("utf-8")
        text = re.sub(r"<c ([^>]*)><f>([^<]*)</f>(?:<v\s*/>|<v></v>)?", rf'<c \1 t="str"><f>\2</f><v>{cached_text}</v>', text)
        return text.encode("utf-8")

    return with_part_rewritten(xlsx_bytes=xlsx_bytes, part_name="xl/worksheets/sheet1.xml", rewrite=_rewrite)


def with_entries_reordered(*, xlsx_bytes: bytes, leading_names: list[str]) -> bytes:
    """The bytes of a workbook re-zipped with `leading_names` first, then its other entries, `xl/` ones last.

    A leading name the workbook lacks is written as an empty entry, so a sniffer reading only the first few entries
    finds no part that names the workbook.
    """
    source = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    existing_names = source.namelist()
    other_names = [name for name in existing_names if name not in leading_names]
    ordered_names = leading_names + sorted(other_names, key=lambda name: name.startswith("xl/"))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name in ordered_names:
            content = source.read(name) if name in existing_names else b""
            target.writestr(name, content)
    return buffer.getvalue()
