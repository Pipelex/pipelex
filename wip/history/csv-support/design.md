# CSV Support — Design

Status: **design / pre-plan**. This document frames the problem and the design space so we can choose an approach before writing an implementation plan. It deliberately leaves the key decisions open (see "Decisions to make").

## 1. Goal

Let Pipelex methods take **CSV files as input** and produce **CSV files as output**, so tabular data flows in and out of pipelines as a first-class citizen rather than being shoehorned into a generic document blob or a hand-rolled `PipeFunc`.

Concrete user stories that should "just work":

- "I have a `contacts.csv`; run my enrichment pipe over each row and give me back an enriched CSV."
- "My pipeline produces a list of extracted records; save them as a `.csv` I can open in Excel."
- "Hand this spreadsheet to an LLM step as context."

## 2. Where this lands in the current architecture

Findings from the codebase (file references for the eventual plan):

- **Content/stuff type system** — every value is a `StuffContent` subclass wrapped in a `Stuff` (`pipelex/core/stuffs/`). Concrete types: `TextContent`, `ImageContent`, `DocumentContent`, `JSONContent`, `HtmlContent`, `NumberContent`, `ListContent[T]`, `StructuredContent` (base for custom concepts), `TextAndImagesContent`, `SearchResultContent`, `PageContent`, `MermaidContent`, `DynamicContent`.
- **Common interface** — `rendered_plain / rendered_html / rendered_markdown / rendered_json` (+ async variants), `smart_dump()`, `rendered_pretty()`. Defined on `StuffContent` (`pipelex/core/stuffs/stuff_content.py`).
- **Native concepts** — enumerated in `pipelex/core/concepts/native/concept_native.py` (`NativeConceptCode` → `structure_class`). Native concepts are part of the **MTHDS language surface**, not just runtime sugar.
- **Lists & batch** — `ListContent[T]` implements the Python list protocols; `PipeBatch` (`pipelex/pipe_controllers/batch/pipe_batch.py`) runs a branch pipe over each item of a `ListContent` and recombines outputs into a `ListContent`. `[]` multiplicity (`Person[]`, `Text[3]`) is declared in `.mthds` inputs/outputs.
- **Input path** — `pipelex run --inputs <json|path>` → `inputs.json` may reference local files by `url`; `_inputs_path_resolver.py` resolves relative paths; `working_memory_factory.make_from_pipeline_inputs` builds the `WorkingMemory`. File-backed types (`Document`, `Image`) store a **URL/reference**, not parsed bytes.
- **Output path** — `--save-main-stuff` writes `main_stuff.{json,md,html}`; `--save-working-memory` dumps the whole memory as JSON (`pipelex/cli/commands/run/_run_core.py`).
- **No tabular code exists** — no `csv`/`pandas`/`polars`/`openpyxl` dependency; `.xlsx` is only registered as a MIME type and treated as an opaque document.

**Key reframing:** a CSV table is structurally a `ListContent` of rows. So "CSV support" is less "add a blob type" and more **"a serialization bridge between CSV files and lists of (optionally typed) rows"** — the same role JSON already plays for structured content.

## 3. The central modeling fork

There are two coherent ways to model a CSV in the type system. They are **not** mutually exclusive — they can be layered — but v1 should pick a primary.

### Mode A — Typed rows: CSV ⇄ `ListContent[Concept]`

A CSV binds to a declared concept. `contacts.csv` under concept `Person` becomes `ListContent[Person]`; header cells map to concept fields; cell strings are coerced to field types.

- **Input:** `{ "contacts": { "concept": "myDomain.Person", "content": { "url": "contacts.csv" } } }` → parsed into typed rows.
- **Output:** any `ListContent[StructuredContent]` → CSV by flattening fields to columns.
- **Pros:** deeply native; rows immediately flow through `PipeBatch` and typed pipes; type-safe; round-trips with the rest of the system.
- **Cons:** needs a column↔field mapping rule, type coercion, and a policy for nested/complex fields (flatten with dotted keys / JSON-encode the cell / reject). Header semantics must be pinned down.

### Mode B — Table primitive: CSV ⇄ `TableContent`

A new content type holding the table verbatim: `headers: list[str]` + `rows` (list of string rows, or list of dicts). Renders to markdown/HTML/JSON table. No schema, lossless strings.

- **Pros:** simple; schema-free; ideal for "give the LLM a table" and "carry a spreadsheet through unchanged"; minimal coercion logic.
- **Cons:** untyped (everything is strings); to do typed per-row processing you still need a separate "table → typed list" step. Adds a **new native concept** to the MTHDS language surface (enum + registry + `Stuff` helpers + tests + arguably the `mthds/` spec).

### How they relate

Mode B is the **lossless, schema-free primitive**; Mode A is the **typed bridge**. A clean end state has both: read a CSV as a `Table` when you just want the grid, or bind it to a concept when you want typed rows; write any list/table back out. The decision is which is the *canonical* v1 surface and whether we add a native concept at all.

## 4. I/O surface design space

Independent of the modeling fork, each direction has surface choices (non-exclusive):

**Output**

- **(O1) Render format** — add a CSV rendering (`rendered_csv()` / a `csv` `TextFormat`). Cheapest; makes CSV "just another rendering of a list/table". But CSV doesn't fit the prompt-format router cleanly and is awkward for arbitrarily nested structures.
- **(O2) CLI export** — extend `--save-main-stuff` to also emit `main_stuff.csv` when the main stuff is a list/table, or add `--save-csv <path>`. Best for "run pipeline → get a CSV".
- **(O3) Dedicated pipe operator** — an explicit "write list/table to CSV artifact" operator. Most explicit, most plumbing; probably overkill for v1.

**Input**

- **(I1) `inputs.json` references a `.csv`** — extend the input loader/factory to parse `.csv` URLs into the chosen content (Table or typed list). Most consistent with how `Document`/`Image` inputs work today.
- **(I2) CLI sugar** — e.g. `pipelex run my_pipe --csv data.csv`. Nice-to-have, later.
- **(I3) Programmatic factory** — `TableContent.make_from_csv_path(...)` / `ListContentFactory.from_csv(path, concept=...)` for library users and tests.

## 5. Dependency question

Core has no DataFrame dependency and is intentionally lean. Options:

- **Stdlib `csv` only** — covers comma/delimiter parsing, quoting, headers. No `.xlsx`. Keeps core lean. **Default recommendation.**
- **pandas/polars** — richer (dtypes, Excel, big files) but a heavy core dependency we'd rather not impose. If Excel is wanted, prefer an **optional extra** (`pipelex[tabular]`) over a hard dep.

This choice bounds the Excel/`.xlsx` ambition, so it's coupled to the scope decision below.

## 6. Chosen approach (locked)

Decisions taken (see §7 for the record):

- **Model — typed lists only (Mode A).** A CSV is a **serialization format for `ListContent[Concept]`**, never a blob and never a new content type. No native `Table` concept; the MTHDS language surface is unchanged. Rows are instances of a declared concept; columns are that concept's fields. This reuses `ListContent`, typed concepts, and `PipeBatch` directly.
- **Scope — full round-trip.** CSV in → process (typically batch over rows) → CSV out, both directions in v1.
- **Dependency — stdlib `csv` in core, `.xlsx` behind an optional extra.** v1 reads/writes CSV with the stdlib `csv` module (no DataFrame dep). The reader/writer sits behind a small **format seam** so an `openpyxl`-backed `.xlsx` codec can be added later under `pipelex[tabular]` without touching callers.
- **Nested cells — reject non-flat.** A row concept used for CSV must have **scalar fields only** (`str`/`int`/`float`/`bool`/optional thereof). A nested structure or list field raises a clear error telling the author to project to a flat concept first. No silent flattening, no JSON-in-cell, no dropped data.

**Design principle that falls out of this:** CSV is an **I/O codec**, not a prompt-render format. It does **not** join the `rendered_plain/markdown/html/json` `TextFormat` router (that family is about LLM/template/display rendering). Reading and writing CSV files is a separate codec surface that the CLI and the input loader call into.

## 7. Worked example — the round-trip

The headline "enrich a CSV" flow, end to end:

1. **Input** — `inputs.json` points a row concept at a `.csv`:

    ```json
    { "contacts": { "concept": "acme.Contact", "content": { "url": "contacts.csv" } } }
    ```

    The input loader sees a `.csv` URL, parses each data row into an `acme.Contact`, and yields `ListContent[Contact]`. (A CSV is inherently a list, so one `.csv` → one list; the named concept is the **row** concept.)

2. **Process** — the pipe declares `contacts = "Contact[]"` and uses `PipeBatch` to run a branch pipe `enrich_contact` over each `Contact`, recombining into `ListContent[EnrichedContact]` as the main stuff.

3. **Output** — the CLI writes the flat `ListContent[EnrichedContact]` back to `enriched.csv` (columns = `EnrichedContact`'s scalar fields).

No new operators, no new concept type — just the CSV codec bolted onto the existing list/batch machinery at the two edges.

## 8. Surfaces & semantics

**Input (I1 + I3).** `inputs.json` `.csv` references are parsed in the input loader; underneath sits a programmatic codec (`from_csv(path, row_concept) -> ListContent`) that tests and library users can call directly. Semantics:

- The `.csv` must have a **header row**; column headers must **match the row concept's field names** (strict — no implicit remapping).
- Cell strings are coerced to field types via pydantic's lax validation (e.g. `"42"` → `int`). An **empty cell → `None`** (and must therefore map to an optional field).
- **Extra columns** (no matching field) and **missing columns** for required fields are errors — predictable, no silent reshaping. (Consistent with the reject-non-flat stance.)

**Output (O2 + codec).** A flat `ListContent[StructuredContent]` is written to CSV; underneath the same codec (`to_csv(list_content, path)`). Trigger surface (finer point, see below): either auto-emit `main_stuff.csv` from `--save-main-stuff` when the main stuff is a flat list, or an explicit `--save-csv <path>`. Semantics:

- Columns are the row concept's scalar fields, in declared order; one CSV row per item.
- A non-flat row concept (any nested/list field) is **rejected with a clear error** at write time.

**Codec & format seam.** A single small tabular-codec module owns read/write, dispatched by file extension/format. CSV is the only built-in in v1; the seam's shape (a reader fn + writer fn keyed by format) is what lets `.xlsx` arrive later as an optional extra with zero changes to the loader or CLI.

## 9. Finer points (proposed defaults — speak up to change)

These don't change the shape of the feature; listed so the plan can lock them.

- **`inputs.json` convention:** the `concept` names the **row** concept; a `.csv` content URL implies list multiplicity (one CSV → `ListContent[row-concept]`). Pipe inputs are therefore declared with `[]`.
- **Output trigger:** prefer an explicit `--save-csv <path>` over auto-emitting from `--save-main-stuff` (explicit, no surprise files). Open to auto-emit if you'd rather.
- **Empty cell → `None`**; requires the field to be optional.
- **Strict columns:** exact header↔field correspondence; extra/missing columns error.
- **Dialect:** UTF-8, standard comma dialect; **delimiter and encoding configurable**, never auto-guessed.

## 10. Non-goals (v1)

- Streaming / out-of-core CSVs too large for memory.
- `.xlsx` in core — it's explicitly designed-for but ships later behind `pipelex[tabular]`; Google Sheets / Parquet are out.
- Delimiter/dialect **auto-detection** (configurable, not guessed).
- Schema/type **inference** beyond what the bound concept declares.
- A native `Table` concept / schema-free table primitive (deliberately not in this design; would be a separate, additive language-surface decision).

## 11. Risks / watch-outs

- **Lossy coercion** — string→typed coercion can change data (e.g. leading zeros, locale numbers). Document the rules; lean on pydantic's well-defined coercion rather than ad-hoc parsing.
- **Header collisions / unnamed columns** — define behavior for duplicate or blank headers up front (recommend: error).
- **Flat-only friction** — real concepts are often nested; the reject-non-flat rule means authors must add a "project to flat row" step. That's intended (predictable), but the error message must name the offending field and suggest the fix.
- **Format-seam over-engineering** — keep the seam minimal (two functions keyed by format); don't build a plugin framework before the second format exists.
