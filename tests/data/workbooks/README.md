# Workbooks saved by Excel and LibreOffice

The workbooks under `excel/` and `libreoffice/` were saved by the programs themselves, so the tests of the sheet-range finder and the workbook reader (`tests/unit/pipelex/tools/tabular/test_xlsx_saved_by_office.py`) read what a user's file holds: cached formula values, the defined names each program writes for a filter, and its own stored cells. Every other workbook in the tests is built in code with openpyxl, which stores no cached value and writes names its own way.

Each pair has the same content:

- `header_in_a1.xlsx`: a header in A1 and data rows, no Excel Table.
- `title_above_header.xlsx`: a title in A1, a blank row, then the header on row 3.
- `totals_line.xlsx`: a totals line under the data, `=SUM` on the sheet `Expenses` and `=SUBTOTAL(9,…)` on the sheet `Subtotal`.
- `filter_on_header.xlsx`: a filter (Data > Filter) on the header row, which both programs record as the hidden name `_xlnm._FilterDatabase`.
- `named_ranges.xlsx`: a workbook-scoped name `Expenses` and a sheet-scoped name `Trips` on the sheet `Mileage`.

The `excel/` files were saved by Microsoft Excel 16 for Mac and the `libreoffice/` files by LibreOffice Calc 26.8, each re-saving the source workbooks the script below writes.

## Regenerating them

Write the source workbooks with openpyxl, running the script with the repository's environment and the output directory as its argument:

```python
"""Build the source workbooks that Excel and LibreOffice re-save as the sheet-range fixtures."""

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.workbook.defined_name import DefinedName

OUT = Path(sys.argv[1])
HEADER = ["Merchant", "Category", "Amount"]
ROWS = [["Rail Co", "Travel", 84.5], ["Cafe Nord", "Meals", 12], ["Paper Shop", "Office", 23.75]]


def sheet(title: str = "Expenses") -> tuple[Workbook, object]:
    wb = Workbook()
    ws = wb.active
    ws.title = title
    return wb, ws


def write(ws, top: int, rows) -> None:
    for offset, row in enumerate(rows):
        for col, value in enumerate(row, start=1):
            ws.cell(row=top + offset, column=col, value=value)


# 1. A header in A1 with data rows and no Table.
wb, ws = sheet()
write(ws, 1, [HEADER, *ROWS])
wb.save(OUT / "header_in_a1.xlsx")

# 2. A title in A1, a blank row, the header on row 3.
wb, ws = sheet()
ws["A1"] = "March expenses"
write(ws, 3, [HEADER, *ROWS])
wb.save(OUT / "title_above_header.xlsx")

# 3. A totals line under the data: SUM in the Amount column, and SUBTOTAL in a second sheet.
wb, ws = sheet()
write(ws, 1, [HEADER, *ROWS, ["Total", None, "=SUM(C2:C4)"]])
ws2 = wb.create_sheet("Subtotal")
write(ws2, 1, [HEADER, *ROWS, ["Total", None, "=SUBTOTAL(9,C2:C4)"]])
wb.save(OUT / "totals_line.xlsx")

# 4. A filter on the header row of the range.
wb, ws = sheet()
write(ws, 1, [HEADER, *ROWS])
ws.auto_filter.ref = "A1:C4"
wb.save(OUT / "filter_on_header.xlsx")

# 5. A workbook-scoped named range, and a sheet-scoped one on a second sheet.
wb, ws = sheet()
write(ws, 1, [HEADER, *ROWS])
wb.defined_names["Expenses"] = DefinedName("Expenses", attr_text="Expenses!$A$1:$C$4")
ws2 = wb.create_sheet("Mileage")
write(ws2, 2, [["Trip", "Km"], ["Lyon", 465], ["Lille", 225]])
ws2.defined_names["Trips"] = DefinedName("Trips", attr_text="Mileage!$A$2:$B$4")
wb.save(OUT / "named_ranges.xlsx")
```

Re-save them through LibreOffice Calc, which calculates the formulas and stores their values:

```bash
/Applications/LibreOffice.app/Contents/MacOS/soffice --headless --calc --convert-to 'xlsx:Calc MS Excel 2007 XML' --outdir libreoffice src/*.xlsx
```

Re-save them through Microsoft Excel with AppleScript, one workbook at a time. Excel is sandboxed on macOS, so the first open asks a person to grant access to the folder holding `src/` and `excel/`:

```bash
for name in header_in_a1 title_above_header totals_line filter_on_header named_ranges; do
osascript <<SCRIPT
tell application "Microsoft Excel"
  set wb to open workbook workbook file name (POSIX file "$PWD/src/$name.xlsx" as text)
  calculate full
  save workbook as wb filename (POSIX file "$PWD/excel/$name.xlsx" as text) file format Excel XML file format
  close wb saving no
end tell
SCRIPT
done
```
