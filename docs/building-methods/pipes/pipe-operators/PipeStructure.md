---
title: "PipeStructure Operator"
description: "PipeStructure turns free-form text into a structured concept via a single LLM call, or reads a spreadsheet (an Excel Table, a named range, a range on a sheet or a CSV file) into a list of records with no model at all."
---

# PipeStructure

`PipeStructure` is the operator that turns a single input into structured data. The concept of that input decides how:

- **A `Text` input** (or a concept that refines `Text`): an LLM extracts the requested structure from the text and produces a typed object, or a list of objects, matching your output concept.
- **A `Document` input** (or a concept that refines `Document`): the runtime reads one table of a spreadsheet, an Excel workbook (`.xlsx`) or a CSV file, into a list of records, one per data row, and calls no model. See [Reading a spreadsheet](#reading-a-spreadsheet).

Use the Text path whenever the source of the text is not the LLM call itself — for example when text comes from a PDF extraction, a web search result, a user message, or an upstream `PipeLLM` step that intentionally produced free-form prose.

## How it works

On the Text path:

1. The operator reads the single declared input from the working memory and renders the built-in `structuring_prompt` template against it.
2. It appends a JSON-schema description of the target concept (the same helper `PipeLLM` uses for object generation) so the model knows which fields to fill.
3. It picks an LLM setting using the same precedence as `PipeLLM` for object generation: explicit `model` on the pipe → `llm_choice_overrides.for_object` → `llm_choice_defaults.for_object`.
4. It calls `make_object` (or `make_object_list` when the output multiplicity is a list) and emits the result as the pipe's output.

`PipeStructure` does not accept user-controlled prompt templates. The structuring prompt lives in `pipelex.toml` under `[inference.llm.generic_templates] structuring_prompt`; the only variable rendered into it is `text`, fed automatically from the declared input.

## Configuration

`PipeStructure` is configured in your pipeline's `.mthds` file.

### MTHDS Parameters

| Parameter | Type | Description | Required |
| --- | --- | --- | --- |
| `type` | string | The type of the pipe: `PipeStructure` | Yes |
| `description` | string | A description of what this structuring step produces. | Yes |
| `inputs` | dictionary | Exactly one input, with no multiplicity. Its concept must be `Text` or refine `Text`, or be `Document` or refine `Document`, at any depth, to read a spreadsheet; a concept that merely holds a `Document` in one of its fields is neither. | Yes |
| `output` | string | The target structured concept, with optional multiplicity (`Foo`, `Foo[]`, `Foo[3]`). Cannot be `Text` or `Text`-compatible. Reading a spreadsheet, it must be a variable list (`Foo[]`). | Yes |
| `model` | string or table | The LLM choice used for the structuring call. Defaults to the `for_object` LLM choice (override → default). Refused when reading a spreadsheet, which calls no model. | No |
| `table` | string | Reading a spreadsheet: the name of the Excel Table to read or, when the workbook holds no Table of that name, of the named range, compared ignoring case. Leave it out to read the workbook's only Table. Refused together with `sheet_range`, refused on the Text path, and refused at run time for a CSV file, which has no Tables. | No |
| `sheet_range` | table | Reading a spreadsheet: a range of rows on a worksheet that holds no Excel Table, `{ sheet = "Expenses", header_row = 3 }`. `sheet` names the worksheet, compared ignoring case, and can be left out when the workbook holds one worksheet; `header_row` is the row holding the header, counted from 1, and can be left out when the header is the sheet's first row holding a value. `sheet_range = {}` reads the only worksheet. See [A range on a sheet](#a-range-on-a-sheet). Refused together with `table`, refused on the Text path, and refused at run time for a CSV file. | No |
| `row_field` | string | Reading a spreadsheet: an integer or number field of the output concept that receives each row's position among the table's data rows, counted from 1. No column may match it. Refused on the Text path. | No |

### LLM Setting Fields

When `model` is given as a table, it accepts the same fields as `PipeLLM`'s inline LLM setting (`model`, `temperature`, `max_tokens`, `reasoning_effort`, `reasoning_budget`, `description`). See [PipeLLM › LLM Setting Fields](./PipeLLM.md#llm-setting-fields).

!!! note "No images, no PDFs"
    `PipeStructure` is intentionally narrow: it takes one `Text` input, or one spreadsheet `Document`. To structure an image or a PDF page, run an upstream extraction step (e.g. `PipeExtract` or a vision `PipeLLM`) and feed its text output into `PipeStructure`.

### Output Multiplicity

Use bracket notation in the `output` field to control how many items the LLM should return:

- `output = "Review"` — exactly one item.
- `output = "Review[]"` — the model decides how many.
- `output = "Review[3]"` — exactly three.

See [Understanding Multiplicity](../understanding-multiplicity.md) for the full picture.

## Reading a spreadsheet

When the single input is a `Document`, `PipeStructure` reads one table of the file into the output list, one item per data row, with no model call and no inference cost. The file's format is judged from its bytes first, then from the media type and the file name it was given with: an Excel workbook (`.xlsx`) or a CSV file is read, and any other file is refused, naming the input. A CSV file has no signature its bytes could be told by, and uploads often declare it with a type that names no table format, such as `application/octet-stream`, `text/plain` or `application/vnd.ms-excel`, the type Windows gives a `.csv` file when Excel is installed: when the bytes say nothing and the declared type names neither format, a file named `….csv` or `….xlsx` is read by its name. A workbook whose archive lists its spreadsheet parts after other entries can look like a plain ZIP archive from its first bytes: when neither its declared type nor its name says more, its archive's directory is read, and a file declaring a spreadsheet main part, or holding `xl/workbook.xml`, is read as a workbook. Run setup already refuses a file of another format given as a method input, before any step runs. Reading a workbook needs the `tabular` extra (`pip install "pipelex[tabular]"`), which installs openpyxl.

**Which table.** In a workbook, the rows are read from one of three kinds of region. By default they are read from an Excel Table, the named table object created with Insert > Table: the workbook's only Table, a workbook holding several Tables or none being refused, the refusal listing the Tables found and, with none, suggesting `sheet_range`. With `table`, they are read from the Table of that name or, when the workbook holds none of that name, from the named range of that name (Formulas > Define Name); a workbook holding neither is refused, listing its Tables. With `sheet_range`, they are read from a range of rows on a worksheet, found by the rules below; a worksheet holding exactly one Excel Table is read as that Table, and one holding several is refused, naming them. A Table's header row names the columns, and its totals row is not read. A CSV file is one table, read as comma-separated UTF-8 with a header line, a leading byte order mark ignored.

**A named range.** The name may be defined for the whole workbook or for one sheet. Its first row is the header, and every row under it, to the end of the range, is a data row. A header cell that is empty names no column, and the cells under it are not read. A name defined more than once, on several sheets or both for the workbook and for a sheet, is refused, since it designates no one range. So is a name that is not one rectangle of cells: a formula or a constant, several ranges, whole columns or rows, cells outside the sheet's grid (from `A1` to `XFD1048576`), cells deleted since the name was defined (`#REF!`), a sheet that no longer exists, or a single cell. The names a spreadsheet program keeps for itself, such as a filter's, are never read as the step's named range.

**Which columns.** Each column header is matched to a field of the output concept ignoring case, spaces, dots and underscores, so a `Unit price` column fills `unit_price`. A header spelling a field's name exactly binds that field first, before any such comparison: an output concept with both `unit_price` and `unitprice` reads each from the column named exactly after it, and only a header spelling neither, such as `Unit Price`, matches both. A column that matches no field is ignored. A header matching several fields, several headers matching the same field, and a header matching the `row_field` are refused, and so is a required field that no column matches. An optional field with no column takes its default value, or nothing.

**Which rows.** Every row of an Excel Table is a data row, an empty one included, and the totals row is not; every row of a named range under its header is a data row; and a range on a sheet's data rows are those the rules above find, its totals line excluded. In a named range or a range on a sheet, a cell inside a merged range whose first cell lies in a data row reads as that first cell, as the spreadsheet shows it. In a CSV file, a blank line is skipped and not counted, a line of empty cells (`,,`) is a data row, a shorter line is padded with empty cells, and a line wider than the header is refused. The `row_field`, when given, receives each row's position among the data rows, counted from 1, so a row the method later changes can be found again.

**Which values.** The output concept's fields must each be `text`, `integer`, `number`, `boolean`, `date`, `datetime` or `choices`; a concept without a structure, or with a nested or list field, is refused. An empty cell gives the field its default value, or nothing. A workbook cell keeps its type: a text field reads a whole number as its digits, another number in its shortest decimal form, a date in ISO 8601 form and a boolean as `true` or `false`; an integer field reads a number without a fractional part; a number field any number, never a boolean; a boolean field a boolean; a date field a date, or a datetime at midnight; a datetime field a datetime or a date. A text cell, which every CSV cell is, gives an integer only from an integer literal, a number only from a decimal written with a dot and no grouping separator (`1,5`, `1 234.5` and `1_000` are refused), both written in ASCII digits and refused when too large to be held, such as `1e999`, a boolean from `true`/`false`, `yes`/`no`, `on`/`off`, `y`/`n`, `t`/`f` or `1`/`0` ignoring case, a date or a datetime only in ISO 8601 form, and a choice only when it matches exactly. A value that does not convert fails the step, naming the row's position and the field.

**Formulas.** A formula cell is read as the value the workbook last calculated and stored. A workbook saved by a program that stores no such value, as some generators do, has none: the cell reads as empty, and the step logs a warning naming the field. A formula whose stored value is an empty text, such as `=IF(A2>0,"","x")`, also reads as empty, but was calculated, so no warning is logged for it.

**Limits.** Whoever supplies the file chooses its size, and a workbook of a few compressed kilobytes can declare a Table of millions of cells, so two limits are checked before any cell is read, set under `[runtime.table_reading]`:

```toml
[runtime.table_reading]
max_workbook_uncompressed_bytes = 100_000_000
max_table_cells = 2_000_000
```

A workbook whose parts would hold more than `max_workbook_uncompressed_bytes` once decompressed, as its archive declares them, is refused before it is decompressed, and a Table, a named range or a range on a sheet spanning more than `max_table_cells` cells, its rows, header included, times its columns, is refused before its cells are read. Cells are only ever read within the part of the sheet that holds cells: a column of the Table's declared range past the sheet's last filled column is no column of the table, and a row past the sheet's last filled row is an empty data row, counted toward the row position without being read. Such a row is still a record the step outputs, so every row the Table declares counts toward `max_table_cells`, only its columns being clipped to the sheet, and a Table counts at least one column wide; a Table with no column within the sheet has no header cell and is refused. A CSV file is held to `max_table_cells` too, counted while it is parsed, the header's cells and each line's, a line narrower than the header counting as wide as it and a blank line not at all, and parsing stops as soon as the count passes the limit. Both refusals are `input.too_large`, naming the input. A refused file is fixed by reading a smaller table, or by raising the limits on a deployment that has the memory for it.

The table decides how many records the step outputs, so a step of a controller that asks it for a single output (`multiple_output = false`) or a fixed count (`nb_output`) fails when it runs, as `method.output_multiplicity_mismatch`; a batch over the step, or `multiple_output = true`, is fine.

A dry run reads nothing: it produces mock records, with their positions in the `row_field`.

```toml
[concept.BudgetLine]
description = "One line of a budget workbook"

[concept.BudgetLine.structure]
line     = { type = "integer", description = "The line's position in the table" }
item     = { type = "text", required = true, description = "What is bought" }
amount   = { type = "number", description = "What it costs" }
approved = { type = "boolean", description = "Whether it is approved" }

[pipe.read_budget]
type = "PipeStructure"
description = "Read the budget lines from the workbook"
inputs = { budget = "Document" }
output = "BudgetLine[]"
table = "Expenses"
row_field = "line"
```

### A range on a sheet

Many workbooks keep their rows on a plain sheet, with no Excel Table: a title, a header row, the data, and sometimes a totals line. `sheet_range` reads such a range by rules that make its extent certain, and refuses a sheet those rules cannot settle rather than guess, naming the cell by its address (`Expenses!A9`) and never quoting a cell's value. The rules are the MTHDS standard's, in "Finding a Sheet Range". A cell holds a value when it holds anything other than nothing or an empty text, a formula included whatever it calculates to; a cell carrying only formatting holds none. A cell holds data when it holds a value that is not a formula, or a formula whose stored value is one: the value the spreadsheet calculated when it last saved the file. A formula storing an empty text, as `=IF(A5="","",B5*C5)` does in a row still to fill, holds no data, and neither does a formula the file stores no value of, as in a workbook saved by a program that calculates nothing. A sheet whose rows are all formulas, such as a view onto another sheet, is read like any other when the workbook was saved by Excel or LibreOffice.

1. **The header row** is the row `header_row` names or, without it, the sheet's first row holding a value. Rows above it are not part of the range. A sheet holding no value is refused, and so is a `header_row` naming a row that holds none.
2. **The columns** run from the header row's first cell holding a value, rightwards, to the last one before an empty cell. A header cell of those columns that belongs to a merged range is refused, naming the merged range; a merge elsewhere on the header row that holds no value changes nothing. A header cell holding a formula with no stored value is refused, naming the cell, since the header it shows cannot be read: open the workbook in Excel or LibreOffice and save it. A value further along the header row, past the empty cell that ends the columns, is a second block of columns and is refused.
3. **The data rows** run from the row under the header down to the first row holding no data in any of the columns. A cell merged down from a data row, such as a category spanning two rows, holds that row's data, so the merge does not end the rows, and it is read as the merge's first cell, as the spreadsheet shows it. A range whose header is followed by a row holding no data has no data row, which is valid.
4. **The totals line.** A row is a totals line, and not a data row, when one of its cells holds a formula over the cells above it in its own column, written as a range with a colon, from the first data row through the row just above: `=SUM(C4:C5)`, `=SUBTOTAL(109,$C$4:$C$5)` or `=SUM(Expenses!C4:C5)`. It is the last row the third rule found, when a label such as `Total` stands beside the formula, or else the row right after it, or, when pre-filled rows follow the data rows, the row right after those, labelled or not. A row whose formulas are written otherwise is no totals line: it is a data row when it holds data, typed values or a formula whose stored value is one, such as a running balance `=C4+C5` storing its sum. A row of typed values is a data row. The row directly under the header is never a totals line.
5. **Pre-filled rows.** Rows below the range that hold formulas and no data, such as a template's `=IF(A5="","",B5*C5)` filled down to row 500, are not rows of the range and are not read: a template prepared for rows to come reads as the rows it holds. A template may keep its total under them, as in data rows, then pre-filled rows, then a `Total` row summing the column from the first data row through the last pre-filled row; that row is the range's totals line, and is not read either. When a pre-filled row holds a formula that stores no value at all, even beside formulas storing an empty text, the workbook was saved without its calculated values and the row may hold data nobody calculated: such rows are not read, and the step logs a warning saying so, to be fixed by opening the workbook in Excel or LibreOffice and saving it.
6. **Nothing below.** Data in the columns below the range is refused: a further row of data after a gap, or a note, which the rules cannot tell apart. When a title stands above the header, the title's row is the first row holding a value, so name the header's row with `header_row`.
7. **No column without a header.** A value in the column just left or just right of the columns, on the header row or a data row, the totals line included, is refused as a column with no header. Values further away, past that empty column, are another part of the sheet and are left alone. A merged range crossing the columns' left or right edge, on the header row, a row of the range or the row just after it, is refused, naming the merged range, since it carries a value into a column with a header from a column without one; a merge wholly inside the columns follows the second and third rules.
8. **A filter** on the sheet, when it has one, must cover the header row and exactly the columns found; a filter that disagrees, or whose reference names no range of cells, is refused.

A range on a sheet counts toward `max_table_cells` as its header row and data rows times its columns. The finder reads only the cells the sheet stores, so a sheet formatted down to its last row costs no more than the cells it holds.

```toml
[pipe.read_expenses]
type = "PipeStructure"
description = "Read the expense lines from the sheet, under its title"
inputs = { expenses = "Document" }
output = "Expense[]"
sheet_range = { sheet = "Expenses", header_row = 3 }
row_field = "line"
```

## Examples

### Structure free-form text into a typed object

```toml
[concept.RestaurantReview]
description = "A structured restaurant review extracted from prose"

[concept.RestaurantReview.structure]
restaurant_name = { type = "text", description = "Name of the restaurant" }
overall_rating  = { type = "integer", description = "Overall rating from 1 to 5" }
highlights      = { type = "list", item_type = "text", description = "Standout positives" }
complaints      = { type = "list", item_type = "text", description = "Issues mentioned" }

[pipe.structure_review]
type = "PipeStructure"
description = "Turn a free-form review into a RestaurantReview"
inputs = { review_text = "Text" }
output = "RestaurantReview"
```

### Structure a list of objects

```toml
[pipe.structure_review_batch]
type = "PipeStructure"
description = "Extract one or more reviews from a transcript"
inputs = { transcript = "Text" }
output = "RestaurantReview[]"
```

### After a document extraction step

`PipeStructure` shines as the second stage of a sequence whose first stage produces text from a non-text source.

```toml
[pipe.invoice_to_record]
type = "PipeSequence"
description = "Read an invoice PDF and turn it into an InvoiceRecord"
inputs = { invoice_pdf = "Document" }
output = "InvoiceRecord"
steps = [
  { pipe = "extract_invoice_text", result = "invoice_text" },
  { pipe = "structure_invoice",    result = "invoice_record" },
]

[pipe.extract_invoice_text]
type = "PipeLLM"
description = "Read the invoice PDF and produce a faithful textual transcript"
inputs = { invoice_pdf = "Document" }
output = "Text"
prompt = """
Read this invoice and produce a faithful textual transcript of every line item, total, and metadata:
@invoice_pdf
"""

[pipe.structure_invoice]
type = "PipeStructure"
description = "Turn the invoice transcript into an InvoiceRecord"
inputs = { invoice_text = "Text" }
output = "InvoiceRecord"
```

### Pick a different model for the structuring step

```toml
[pipe.structure_review_premium]
type = "PipeStructure"
description = "Use a stronger model for tricky structurings"
inputs = { review_text = "Text" }
output = "RestaurantReview"
model = "@default-premium"
```

## When to reach for `PipeStructure`

- You already have text and you want it as a typed object.
- You want a deterministic boundary between "writing prose" and "filling a schema" — for example to make the prose call cheaper, or to swap the structuring model independently.
- You want the same structuring step reused across several upstream sources (extraction, search, generation).
- You have a spreadsheet and want its rows as typed records, without paying for a model to read them.

For the common case where the text is freshly produced by an LLM and you want a single declaration, see [`structuring_method = "preliminary_text"` on PipeLLM](./PipeLLM.md#structuring-method-preliminary-text), which expands at build time into a `PipeSequence` of `PipeLLM` (text) + `PipeStructure`.

## Related Documentation

- [PipeLLM](./PipeLLM.md) — direct structured generation in a single call, plus the `preliminary_text` shorthand.
- [PipeExtract](./PipeExtract.md) — produces text from PDFs and images, a natural upstream step.
- [Understanding Multiplicity](../understanding-multiplicity.md) — single vs list outputs.
- [CSV Input & Output](../csv-input-and-output.md) — a CSV file or a workbook given directly as a method's list input, and CSV output.
- [Editing a User's Workbook](../../editing-a-users-workbook.md) — reading a workbook's rows, then writing an edited copy of it with `PipeDocGen`.
