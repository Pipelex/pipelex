---
description: "Read CSV (or Excel) files into typed lists and write list outputs back to CSV. Covers the inputs.json convention, the --save-csv flag, the flat-concept rule, type coercion, and v1 limitations."
---

# CSV Input & Output

Pipelex can read a CSV file directly into a typed list and write a list output back out as CSV. A CSV maps to a `ListContent` of a flat concept: each row becomes one instance of the concept, and each column maps to one of its fields. No new language construct is involved — you describe the row concept exactly as you would any structured concept.

This covers reading a `.csv` referenced from your `inputs.json`, writing a result with `--save-csv`, and the rules and limitations of the v1 codec.

## The flat-concept rule

A concept used with CSV must be **flat**: every field is a scalar. The accepted types are:

- `text` → `str`
- `integer` → `int`
- `number` → `float`
- `boolean` → `bool`
- `date` → `datetime.date` (ISO `YYYY-MM-DD`)

Optional fields are allowed, and so are choice-constrained scalars (`Literal` / `choices`). Any nested concept, list, dict, union, or `Any`-typed field is rejected with a clear error that names the offending field — a CSV cell has no room for nested structure, so you must project to a flat concept first.

```toml
[concept.Person]
description = "A person record read from a CSV row"
[concept.Person.structure]
name       = { type = "text",    required = true,  description = "Full name" }
job        = { type = "text",    required = true,  description = "Occupation" }
country    = { type = "text",    required = true,  description = "Country of origin" }
birth_year = { type = "integer", required = true,  description = "Year of birth" }
death_year = { type = "integer", required = false, description = "Year of death, if deceased" }
```

## Reading a CSV as input

Reference the file from `inputs.json` with a `url` whose path ends in a tabular suffix (`.csv`, or `.xlsx` once the Excel backend is available), under a flat structured concept. Pipelex detects the tabular suffix and reads the file into a `ListContent` of that concept — one CSV file becomes one list, and the concept names the **row** type:

```json
{
  "people": {
    "concept": "demo.Person",
    "content": { "url": "people.csv" }
  }
}
```

Given a `people.csv`:

```csv
name,job,country,birth_year,death_year
Ada Lovelace,Mathematician,United Kingdom,1815,1852
Grace Hopper,Computer Scientist,United States,1906,1992
Vint Cerf,Computer Scientist,United States,1943,
```

`people` arrives as a `ListContent[Person]` with three items. `birth_year` is coerced to `int`, and Vint Cerf's blank `death_year` cell becomes `None` (which is why `death_year` is declared optional).

### Header and column rules

- The header row is **required**, and headers must match the concept's field names exactly — there is no implicit renaming.

- An **extra** column (one with no matching field) is an error.

- A missing **required** column is an error.

- A missing **optional** column is fine — that field is `None` for every row. (Pipelex's own writer always emits every column, so this only matters for hand-authored partial CSVs.)

- An **empty cell** becomes `None` before validation, so the field must be optional to accept it.

### Type coercion

Cell strings are coerced through Pydantic's lax validation. The contract is pinned by tests, so you can rely on it:

| Field type | Accepted | Rejected |
| --- | --- | --- |
| `boolean` | `true`, `false`, `1`, `0`, `yes`, `no`, `on`, `off` | anything else |
| `integer` | `42`, `-3` | `1.5`, `1,000` |
| `number` | `1.5`, `3`, `-0.2` | `1,5` (comma decimal), `abc` |
| `date` | ISO `2020-12-31` | `31/12/2020`, `12/31/2020` |

A cell that cannot be coerced raises a clear error naming the 1-based row, the concept, and the field, so you can find the offending value.

## Writing a result as CSV

Pass `--save-csv <path>` to any run command to write the pipeline's main stuff to a CSV file:

```bash
pipelex run pipe summarize_people --inputs inputs.json --save-csv summaries.csv
pipelex run bundle demo.mthds --save-csv out.csv
pipelex run method my_method --save-csv out.csv
```

The path is **literal and cwd-relative** — it is written exactly where you point it, not under `--output-dir`. Parent directories are created as needed. The output's main stuff must be a flat list; if it is not a list, or its row concept is not flat, you get a clear error rather than a malformed file. The header is derived from the **declared** row concept (not from the first item), so an empty list still writes a correct header-only file. On write, `None` is rendered as an empty cell and booleans as lowercase `true`/`false`, so a value round-trips back through a read unchanged.

## Round-trip example

The pieces compose into a full CSV-in → process → CSV-out round trip. Here a `PipeBatch` runs once per person, a `PipeLLM` writes a one-sentence persona, and a `PipeCompose` assembles the output row from selected input fields plus that sentence. Both the input concept `Person` and the output concept `PersonSummary` are flat, so both sides satisfy the flat-concept rule:

```toml
[concept.PersonSummary]
description = "A person row reduced to name + country plus a one-sentence persona summary"
[concept.PersonSummary.structure]
name    = { type = "text", required = true, description = "Full name" }
country = { type = "text", required = true, description = "Country of origin" }
summary = { type = "text", required = true, description = "One-sentence persona summary" }

[pipe.summarize_people]
type             = "PipeBatch"
description      = "Summarize each person in the list"
inputs           = { people = "Person[]" }
output           = "PersonSummary[]"
branch_pipe_code = "summarize_person"
input_list_name  = "people"
input_item_name  = "person"
```

```bash
pipelex run pipe summarize_people --inputs inputs.json --save-csv summaries.csv
```

This reads `people.csv` into `ListContent[Person]`, summarizes each person, and writes a `summaries.csv` with header `name,country,summary` and one row per input person.

## Configuring delimiter and encoding

The codec defaults to a comma delimiter and UTF-8 encoding. Both are parameters of the codec functions (`list_content_from_csv` / `csv_from_list_content`), but there is no user-facing config surface (TOML default or CLI flag) in v1 — they are never guessed from the file. A user-facing knob for European semicolon-delimited CSVs is a planned follow-up.

## Limitations in v1

- **Local file paths only.** A remote `url` with a tabular suffix — `http(s)://`, `s3://`, `gs://`, a signed URL — is actively rejected with a clear error, never opened. Reading remote tabular files is a deferred follow-up.

- **`.xlsx` is recognized but not yet implemented.** An `.xlsx` path is detected as tabular and routed to a clear "needs `pipelex[tabular]`" message; the Excel backend itself is not built in v1.

- **Empty string is indistinguishable from `None`.** An empty cell reads as `None`, and on write `None` is rendered as an empty cell, so a genuinely empty string `""` cannot be told apart from a missing value through a CSV round trip.

- **A single-field `url` concept reads as a table.** Detection triggers when a content reference carries a `url` whose path ends in a tabular suffix. If you have a flat concept that happens to have a field literally named `url` and you pass `{ "url": "report.csv" }`, it is read as a CSV **table**, not as a single record with `url = "report.csv"`. Use a non-tabular value, or rename the field, if you need the single-record reading.

- **No formula-injection escaping.** Cells are written verbatim to preserve data fidelity, so a value beginning with `=`, `+`, `-`, or `@` is not escaped. If you hand a generated CSV to a spreadsheet application, treat untrusted content accordingly. An opt-in escape flag is a deferred follow-up.

## Related Documentation

- [Providing Inputs to Pipelines](provide-inputs.md)
- [Executing Pipelines](executing-pipelines.md)
- [Pipe Output](pipe-output.md)
- [Run Commands](../../tools/cli/run.md)
