---
description: "Return an edited copy of an Excel workbook a user supplies: append rows to one of its Tables or to a range on a plain sheet, or fill in the empty cells of its rows, with PipeStructure reading the rows and PipeDocGen writing the copy. The user's own file is never changed."
---

# Editing a User's Workbook

A method can take an Excel workbook a user already keeps, such as an expenses register, and return a copy of it with new rows added to a Table, or to the rows typed on a plain sheet, or with the empty cells of some rows filled in. The user's file is never changed: the method returns a new file, named after theirs, and they decide what to do with it.

Two steps do the work, and this guide shows how they fit together:

- a [`PipeDocGen`](pipes/pipe-operators/PipeDocGen.md) step with a `template_input` fills a copy of the workbook the run supplies, either appending records to a Table (`table_fill = "append"`) or writing each record into the row it matches (`table_fill = "update"`);
- a [`PipeStructure`](pipes/pipe-operators/PipeStructure.md#reading-a-spreadsheet) step reads a Table of the same workbook into a list of records, calling no model, so that a method can see which rows have gaps.

The reference pages hold every field and every rule; this page shows the shape of the two methods and the rules an author runs into first.

!!! note "The document generation plugin writes the workbook"
    An `xlsx` step is printed by the `pipelex-xlsx` engine of the Pipelex document generation plugin, which the hosted Pipelex API runs. A runtime without the plugin refuses a method with such a step when it loads, naming the missing engine (see [Document engines](pipes/pipe-operators/PipeDocGen.md#document-engines)). Reading the workbook with `PipeStructure` needs only Pipelex, with the `tabular` extra when you run it yourself.

## The workbook

Both methods below work on a register whose rows live in an Excel Table named `Expenses`, the named table object Excel creates with Insert > Table. Its columns are `Expense ID`, `Date`, `Description`, `Amount` and `Category`. A column header is matched to a field ignoring case, spaces, dots and underscores, so `Expense ID` is the field `expense_id`.

The workbook comes into the method as a `Document` input. Declaring a concept that refines `Document` says what the file is:

```toml
[concept.ExpenseRegister]
description = "A user's expenses workbook, holding an Excel Table named Expenses"
refines     = "Document"
```

## Appending rows

The first method reads a batch of receipts with a model and appends one row per receipt to the register's `Expenses` Table:

```toml
domain      = "expense_append"
description = "Add the expenses shown on receipts to the user's expenses register"
main_pipe   = "add_receipts"

[concept.ExpenseRegister]
description = "A user's expenses workbook, holding an Excel Table named Expenses"
refines     = "Document"

[concept.Expense]
description = "One expense, as a receipt shows it"

[concept.Expense.structure]
expense_id  = { type = "text", description = "The receipt's number, which identifies the expense", required = true }
date        = { type = "date", description = "The day the expense was made", required = true }
description = { type = "text", description = "What the expense was for", required = true }
amount      = { type = "number", description = "The amount paid", required = true }
category    = { type = "text", description = "The expense category, such as Travel, Meals or Supplies" }

[pipe.add_receipts]
type        = "PipeSequence"
description = "Read each receipt into an expense, then append the expenses to the register"
inputs      = { register = "ExpenseRegister", receipts = "Document[]" }
output      = "ExpenseRegister"
steps = [
    { pipe = "read_receipt", batch_over = "receipts", batch_as = "receipt", result = "expenses" },
    { pipe = "append_expenses", result = "updated_register" },
]

[pipe.read_receipt]
type        = "PipeLLM"
description = "Read the expense a receipt shows"
inputs      = { receipt = "Document" }
output      = "Expense"
prompt      = """
Read this receipt and record the expense it shows: the receipt's number as its identifier, its date, a short description, the total amount paid and a category (Travel, Lodging, Meals, Supplies or Software).

@receipt
"""

[pipe.append_expenses]
type           = "PipeDocGen"
description    = "Add the expenses after the rows the register's Expenses Table already holds"
inputs         = { register = "ExpenseRegister", expenses = "Expense[]" }
output         = "ExpenseRegister"
format         = "xlsx"
template_input = "register"
table_fill     = "append"
```

The `append_expenses` step is the whole edit:

- **`template_input = "register"`** names the input whose file is filled. That input is the template, not data: only the step's other inputs fill it, here `expenses`.
- **The list `expenses` fills the Table `Expenses`** because a list of records goes into the Table named after it. Each column takes the field its header matches, so `Expense ID` takes `expense_id`; a column whose header matches no field of the records is left empty in the new rows. Giving every appended row its identifier matters here, because the update below finds its rows by that column.
- **`table_fill = "append"`** keeps every row the Table holds and writes the records after the last row holding data. Empty rows at the end of the Table are filled first, then the Table grows into the empty rows below it. A calculated column, one whose formula Excel filled down the column, keeps calculating on the new rows.

The output is a new `ExpenseRegister`, named after the file the user sent unless the step sets a `filename`.

## Filling in the empty cells

The second method fills in the categories the register leaves empty. It reads the Table's rows, keeps those with no category, asks a model for each one's category, and writes the categories back into the rows they belong to:

```toml
domain      = "expense_update"
description = "Fill in the categories an expenses register leaves empty"
main_pipe   = "complete_categories"

[concept.ExpenseRegister]
description = "A user's expenses workbook, holding an Excel Table named Expenses"
refines     = "Document"

[concept.ExpenseRow]
description = "One row of the register's Expenses Table"

[concept.ExpenseRow.structure]
expense_id  = { type = "text", description = "The expense's identifier", required = true }
date        = { type = "date", description = "The day the expense was made" }
description = { type = "text", description = "What the expense was for", required = true }
amount      = { type = "number", description = "The amount paid" }
category    = { type = "text", description = "The expense category, empty when not yet filled in" }

[concept.CategoryPick]
description = "The category chosen for one expense"

[concept.CategoryPick.structure]
category = { type = "text", description = "Exactly one of: Travel, Lodging, Meals, Supplies, Software", required = true }

[concept.ExpenseCompletion]
description = "The missing category of one expense, with the identifier of its row"

[concept.ExpenseCompletion.structure]
expense_id = { type = "text", description = "The expense's identifier, copied from the row read", required = true }
category   = { type = "text", description = "The category to write into the empty cell", required = true }

[pipe.complete_categories]
type        = "PipeSequence"
description = "Read the register's rows, categorize those with no category, and write the categories back"
inputs      = { register = "ExpenseRegister" }
output      = "ExpenseRegister"
steps = [
    { pipe = "read_rows", result = "rows" },
    { pipe = "complete_if_missing", batch_over = "rows", batch_as = "row", result = "expenses" },
    { pipe = "fill_categories", result = "completed_register" },
]

[pipe.read_rows]
type        = "PipeStructure"
description = "Read the rows of the register's Expenses Table"
inputs      = { register = "ExpenseRegister" }
output      = "ExpenseRow[]"
table       = "Expenses"

[pipe.complete_if_missing]
type                = "PipeCondition"
description         = "Categorize a row whose category is empty, and skip the others"
inputs              = { row = "ExpenseRow" }
output              = "ExpenseCompletion?"
expression_template = "{% if row.category %}skip{% else %}fill{% endif %}"
default_outcome     = "continue"

[pipe.complete_if_missing.outcomes]
fill = "categorize_row"
skip = "continue"

[pipe.categorize_row]
type        = "PipeSequence"
description = "Choose the row's category, then pair it with the row's identifier"
inputs      = { row = "ExpenseRow" }
output      = "ExpenseCompletion"
steps = [
    { pipe = "pick_category", result = "pick" },
    { pipe = "build_completion", result = "completion" },
]

[pipe.pick_category]
type        = "PipeLLM"
description = "Choose the expense's category from its description and amount"
inputs      = { row = "ExpenseRow" }
output      = "CategoryPick"
prompt      = """
Choose the category of this business expense. Answer with exactly one of: Travel, Lodging, Meals, Supplies, Software.

Description: $row.description
Amount: $row.amount
"""

[pipe.build_completion]
type        = "PipeCompose"
description = "Pair the chosen category with the row's identifier, copied unchanged"
inputs      = { row = "ExpenseRow", pick = "CategoryPick" }
output      = "ExpenseCompletion"

[pipe.build_completion.construct]
expense_id = { from = "row.expense_id" }
category   = { from = "pick.category" }

[pipe.fill_categories]
type           = "PipeDocGen"
description    = "Write each category into the empty cell of the row holding its expense identifier"
inputs         = { register = "ExpenseRegister", expenses = "ExpenseCompletion[]" }
output         = "ExpenseRegister"
format         = "xlsx"
template_input = "register"
table_fill     = "update"
match_on       = ["expense_id"]
cells          = "fill_empty"
```

The method's steps, one by one:

1. **`read_rows` reads the Table.** A `PipeStructure` step whose input is a `Document` reads one Table of the workbook into a list of records, one per data row, without calling a model. `table` names the Table, compared ignoring case. The Table's totals row is not read, an empty cell leaves its field empty, and a column the `ExpenseRow` concept has no field for is ignored, so the concept only needs the columns the method uses.
2. **`complete_if_missing` keeps the rows with a gap.** Batched over the rows, the condition sends a row with no category to `categorize_row` and `continue`s past the others. A `continue` produces no output, and a batch drops the branches that produced none, so `expenses` holds a completion only for the rows that needed one (see [PipeBatch](pipes/pipe-controllers/PipeBatch.md) and [PipeCondition](pipes/pipe-controllers/PipeCondition.md#special-outcomes-continue-and-fail)).
3. **`categorize_row` asks the model, then copies the key.** The model chooses the category, and a `PipeCompose` step pairs it with the row's `expense_id`, copied from the row read rather than written by the model, so the completion finds its row again.
4. **`fill_categories` writes the copy.** With `table_fill = "update"`, each record of `expenses` is written into the one row of the `Expenses` Table whose `Expense ID` cell holds its `expense_id`. The key field is never written. `cells = "fill_empty"`, which is also the default, writes only empty cells.

### Matching by row position instead

A sheet with no column that identifies its rows can be matched by position. The `PipeStructure` step records each row's position among the Table's data rows, counted from 1, in the field `row_field` names, the completion carries that position unchanged, and the update step names it with `match_row` in place of `match_on`:

```toml
[concept.ExpenseRow.structure]
position    = { type = "integer", description = "The row's position among the Table's data rows", required = true }
# ... the other fields as above

[concept.ExpenseCompletion.structure]
position   = { type = "integer", description = "The row's position, copied from the row read", required = true }
category   = { type = "text", description = "The category to write into the empty cell", required = true }

[pipe.read_rows]
type        = "PipeStructure"
description = "Read the rows of the register's Expenses Table"
inputs      = { register = "ExpenseRegister" }
output      = "ExpenseRow[]"
table       = "Expenses"
row_field   = "position"

[pipe.build_completion.construct]
position   = { from = "row.position" }
category   = { from = "pick.category" }

[pipe.fill_categories]
type           = "PipeDocGen"
description    = "Write each category into the empty cell of the row at its position"
inputs         = { register = "ExpenseRegister", expenses = "ExpenseCompletion[]" }
output         = "ExpenseRegister"
format         = "xlsx"
template_input = "register"
table_fill     = "update"
match_row      = "position"
cells          = "fill_empty"
```

The position must travel through the method unchanged and never be produced by a model. A batch keeps it, since each branch works on one row and copies its position into its result. No column of the Table may match the `row_field`.

## When the rows live on a plain sheet

Many registers have no Excel Table: a title, a header row, the rows, and sometimes a totals line, typed straight onto a sheet. Both steps name such a range with `sheet_range`, the sheet and the row its header is on, and both find it by the same rules, so the positions `PipeStructure` gives the rows are the rows an update by `match_row` writes:

```toml
[pipe.read_rows]
type        = "PipeStructure"
description = "Read the rows of the register's Expenses sheet, under its title"
inputs      = { register = "ExpenseRegister" }
output      = "ExpenseRow[]"
sheet_range = { sheet = "Expenses", header_row = 3 }
row_field   = "position"

[pipe.fill_categories]
type           = "PipeDocGen"
description    = "Write each category found into its row of the register"
inputs         = { register = "ExpenseRegister", expenses = "ExpenseCompletion[]" }
output         = "ExpenseRegister"
format         = "xlsx"
template_input = "register"
table_fill     = "update"
match_row      = "position"
sheet_range    = { list = "expenses", sheet = "Expenses", header_row = 3 }
```

- **`header_row` skips the title.** Without it, the header is the sheet's first row holding a value; a title above the header would be read as the header, and the refusal says to name the header's row.
- **The range ends at the first row holding no data**, and anything typed below it in the same columns, a note or a further block of rows, refuses the run rather than being read or written over. A formula holds data when the value Excel stored for it when it last saved the file is not empty, so a sheet computed from another sheet reads its rows. Formulas a template fills down ahead of the rows to come, such as `=IF(A5="","",B5*C5)` to row 500, store an empty text, so they are pre-filled rows, not rows of the range, and are not refused. A value in the column just beside the range is a column with no header, refused too, and so is a merged range crossing the edge of the columns.
- **A totals line is not a row.** The first row holding a total of its column from the first data row, one aggregate over two rows or more and nothing else, such as `=SUM(D4:D20)` or `=SUBTOTAL(109,D4:D20)`, is read as a totals line, not a record, ends the data and does not count toward the positions. A running count such as `=MAX($A$4:A9)+1`, or a cumulative `=SUM($D$4:D9)` filled down, is a column of the records, not a total. Rows right after the totals line whose formulas build on it, each with a text label, such as a `VAT` line `=D21*0.2` or a `Grand total` `=D21+D22`, are its footer and are not read either. Anything else after the totals line holding data in the range's columns, such as an "Approved by" note or the records after a subtotal, refuses the run, even below a blank row: move a note out of the columns, and a subtotal below the records. The totals line may also sit under the pre-filled rows, as a template keeps a `Total` row summing the column through its last pre-filled row; `append` then writes into the pre-filled rows above it.
- **Save the workbook with Excel or LibreOffice.** A workbook written by a program that calculates nothing stores no value for its formulas. A header cell holding such a formula refuses the run, and rows holding only such formulas are not read, with a warning in the step's log.
- **`PipeDocGen` names the list.** With `sheet_range`, the list `list` names fills the range, whatever the sheet is called, and only `append` and `update` are allowed: `replace` could clear the user's rows past a boundary the rules found rather than one the workbook declares.
- **Turning the range into a Table keeps the method working.** A sheet holding one Excel Table is read and filled as that Table.

`PipeStructure` also reads a named range, a block of cells named with Formulas > Define Name, by giving its name in `table`. See [A range on a sheet](pipes/pipe-operators/PipeStructure.md#a-range-on-a-sheet) and [Filling a range on a sheet](pipes/pipe-operators/PipeDocGen.md#filling-a-range-on-a-sheet) for every rule.

## The rules you will meet

These are the rules a method author runs into first. The [`PipeDocGen`](pipes/pipe-operators/PipeDocGen.md#a-template-the-run-supplies) and [`PipeStructure`](pipes/pipe-operators/PipeStructure.md#reading-a-spreadsheet) reference pages hold the rest.

### Naming

- **A list input is named after the Table it fills.** The records go into the Table whose name matches the list's name, compared ignoring case, spaces, dots and underscores, so the list `expenses` fills the Table `Expenses`. A list named `expense_records` never reaches a Table named `Expenses`: name the list after the Table, or the Table after the list.
- **Under `append` or `update`, a list of records that reaches no Table refuses the run.** Adding or updating rows is the step's only purpose, so a run that would return the workbook unchanged is refused instead, as `pipelex.docgen.template_input_unfit`, naming the list and the Tables the workbook holds. A list of documents or images, such as the receipts beside the register, needs no Table.
- **The workbook is checked when a run supplies it.** `pipelex validate` cannot see a file the run will send, so its verdict carries a `template_check_warning` saying the template is checked later. When a run starts, before any step does, the workbook is checked against the step's inputs, and an error refuses the run as `pipelex.docgen.template_input_unfit`.

### Matching rows under `update`

- **A record finds its row by a key or by its position, exactly one of the two.** `match_on` names the fields whose columns are the Table's key; `match_row` names the field holding the row's position.
- **Matching is exact, and refuses rather than guesses.** Every record is matched before any cell is written. A key that appears twice in the Table, a record that matches no row, and two records matching the same row each fail the step, and the workbook is not written at all.
- **A key held only through the reader's lenient conversion is refused.** `PipeStructure` reads a text cell into a number field leniently: `00042`, `+42` and ` 42 ` all read as the integer 42. A record whose key is 42 cannot say which of those cells it came from, so a row holding its key only that way is refused, naming the record and the row, rather than written.
- **A text key compares as written**, case, spaces and leading zeros included, so the texts `042` and `42` are two keys. A number compares as its value, so `42` and `42.0` are the same key.
- **Read an identifier into a text field.** When a key column holds identifiers such as `00042`, declare its field as `text`, as `expense_id` is above, so each key keeps the form the workbook writes it in and finds its row exactly.

### What is written, and what is not

- **A null leaves its cell as it was.** In an update, a null means the method produced nothing for that cell, so the cell keeps what it holds.
- **`cells = "fill_empty"`, the default, writes only empty cells.** A filled cell already holding the record's value is left alone, and one holding a different value is a conflict that fails the step. `cells = "overwrite"` writes every cell a non-null value matches, for corrections.
- **Formulas and calculated columns are never written.** Under `update`, a formula cell and every cell of a calculated column are left as they are, and a record field matching a calculated column is refused. Under `append`, a calculated column's formula is carried to each new row, so the column keeps calculating.
- **A totals row is kept under `update`**, since the Table neither grows nor shrinks. Under `append` the Table grows, so a Table with a totals row is refused: put the totals above the Table, beside it or on another sheet, as structured references such as `=SUM(Expenses[Amount])`, which cover every row however many are added.
- **The user's file is never modified.** The engine fills a copy of the input's file and the step stores it as a new document, named after the input's file unless the step sets a `filename`.

## Related documentation

- [PipeDocGen](pipes/pipe-operators/PipeDocGen.md): every field, [a template the run supplies](pipes/pipe-operators/PipeDocGen.md#a-template-the-run-supplies), [updating a Table's rows](pipes/pipe-operators/PipeDocGen.md#updating-a-tables-rows) and [filling a range on a sheet](pipes/pipe-operators/PipeDocGen.md#filling-a-range-on-a-sheet)
- [PipeStructure](pipes/pipe-operators/PipeStructure.md#reading-a-spreadsheet): how a spreadsheet's rows, columns and values are read
- [Understanding Optionality](pipes/understanding-optionality.md): absent results, and how a batch drops them
- [Office File Conversion](../features/office-file-conversion.md): the reading direction, when a model reads a Word, Excel or PowerPoint file
- [CSV Input & Output](pipes/csv-input-and-output.md): a spreadsheet given directly as a method's list input
