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
| `table` | string | Reading a spreadsheet: the name of the Excel Table to read, compared ignoring case. Leave it out to read the workbook's only Table. Refused on the Text path, and refused at run time for a CSV file, which has no Tables. | No |
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

**Which table.** In a workbook, the rows are read from an Excel Table, the named table object created with Insert > Table: the one `table` names, or the workbook's only Table when `table` is left out. A workbook with no Table of that name, or, with no name given, several Tables or none, is refused, and the refusal lists the Tables found. The Table's header row names the columns, and its totals row is not read. A CSV file is one table, read as comma-separated UTF-8 with a header line, a leading byte order mark ignored.

**Which columns.** Each column header is matched to a field of the output concept ignoring case, spaces, dots and underscores, so a `Unit price` column fills `unit_price`. A header spelling a field's name exactly binds that field first, before any such comparison: an output concept with both `unit_price` and `unitprice` reads each from the column named exactly after it, and only a header spelling neither, such as `Unit Price`, matches both. A column that matches no field is ignored. A header matching several fields, several headers matching the same field, and a header matching the `row_field` are refused, and so is a required field that no column matches. An optional field with no column takes its default value, or nothing.

**Which rows.** Every row of an Excel Table is a data row, an empty one included, and the totals row is not. In a CSV file, a blank line is skipped and not counted, a line of empty cells (`,,`) is a data row, a shorter line is padded with empty cells, and a line wider than the header is refused. The `row_field`, when given, receives each row's position among the data rows, counted from 1, so a row the method later changes can be found again.

**Which values.** The output concept's fields must each be `text`, `integer`, `number`, `boolean`, `date`, `datetime` or `choices`; a concept without a structure, or with a nested or list field, is refused. An empty cell gives the field its default value, or nothing. A workbook cell keeps its type: a text field reads a whole number as its digits, another number in its shortest decimal form, a date in ISO 8601 form and a boolean as `true` or `false`; an integer field reads a number without a fractional part; a number field any number, never a boolean; a boolean field a boolean; a date field a date, or a datetime at midnight; a datetime field a datetime or a date. A text cell, which every CSV cell is, gives an integer only from an integer literal, a number only from a decimal written with a dot and no grouping separator (`1,5`, `1 234.5` and `1_000` are refused), both written in ASCII digits and refused when too large to be held, such as `1e999`, a boolean from `true`/`false`, `yes`/`no`, `on`/`off`, `y`/`n`, `t`/`f` or `1`/`0` ignoring case, a date or a datetime only in ISO 8601 form, and a choice only when it matches exactly. A value that does not convert fails the step, naming the row's position and the field.

**Formulas.** A formula cell is read as the value the workbook last calculated and stored. A workbook saved by a program that stores no such value, as some generators do, has none: the cell reads as empty, and the step logs a warning naming the field. A formula whose stored value is an empty text, such as `=IF(A2>0,"","x")`, also reads as empty, but was calculated, so no warning is logged for it.

**Limits.** Whoever supplies the file chooses its size, and a workbook of a few compressed kilobytes can declare a Table of millions of cells, so two limits are checked before any cell is read, set under `[runtime.table_reading]`:

```toml
[runtime.table_reading]
max_workbook_uncompressed_bytes = 100_000_000
max_table_cells = 2_000_000
```

A workbook whose parts would hold more than `max_workbook_uncompressed_bytes` once decompressed, as its archive declares them, is refused before it is decompressed, and a Table spanning more than `max_table_cells` cells, its rows, header included, times its columns, is refused before its cells are read. Cells are only ever read within the part of the sheet that holds cells: a column of the Table's declared range past the sheet's last filled column is no column of the table, and a row past the sheet's last filled row is an empty data row, counted toward the row position without being read. Such a row is still a record the step outputs, so every row the Table declares counts toward `max_table_cells`, only its columns being clipped to the sheet, and a Table counts at least one column wide; a Table with no column within the sheet has no header cell and is refused. A CSV file is held to `max_table_cells` too, counted while it is parsed, the header's cells and each line's, a line narrower than the header counting as wide as it and a blank line not at all, and parsing stops as soon as the count passes the limit. Both refusals are `input.too_large`, naming the input. A refused file is fixed by reading a smaller table, or by raising the limits on a deployment that has the memory for it.

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
