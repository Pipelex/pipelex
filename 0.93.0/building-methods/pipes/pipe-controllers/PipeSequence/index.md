# PipeSequence

The `PipeSequence` controller is used to execute a series of pipes one after another. It is the fundamental building block for creating linear methods where the output of one step becomes the input for the next.

## How it works

A `PipeSequence` defines a list of `steps`. A step is either a **pipe step**, which calls another pipe and gives a name to its output, or a **binding step**, which binds the value at a path in working memory to a new name (see [Binding steps](#binding-steps)). The working memory is passed from one step to the next, accumulating results along the way.

-   The `input` of the `PipeSequence` is passed to the first pipe in the sequence.
-   The `output` of each intermediate step is named via the `result` key and becomes available in the working memory for all subsequent steps.
-   The final `output` of the `PipeSequence` is the output produced by the very last step in the sequence, a pipe step's output or the value a binding step binds.

## Configuration

`PipeSequence` is configured in your pipeline's `.mthds` file.

### MTHDS Parameters

| Parameter  | Type            | Description                                                                                                    | Required |
| ---------- | --------------- | -------------------------------------------------------------------------------------------------------------- | -------- |
| `type`      | string          | The type of the pipe: `PipeSequence`                                                                          | Yes      |
| `description` | string          | A description of the sequence operation.                                                                          | Yes      |
| `inputs`    | dictionary  | The input concept(s) for the *first* pipe in the sequence, as a dictionary mapping input names to concept codes.                                                     | No       |
| `output`   | string          | The output concept produced by the *last* pipe in the sequence.                                                | Yes      |
| `steps`    | array of tables | An ordered list of the steps to run. Each table in the array defines a single step, a pipe step or a binding step. | Yes      |

### Step Configuration

A step carrying `pipe` is a pipe step, and a step carrying `from` is a binding step. A step carries one or the other, never both, and each kind is a closed table: a key the kind does not define is refused.

#### Pipe steps

A pipe step is a table with the following keys:

| Key      | Type   | Description                                                        | Required |
| -------- | ------ | ------------------------------------------------------------------ | -------- |
| `pipe`   | string | The name of the pipe to execute for this step.                     | Yes      |
| `result` | string | The name to give to this step's output in the working memory, a plain `snake_case` input name such as `pages` (see [Stored names](#stored-names)). When omitted, the output is stored only in the unnamed `main_stuff` slot (the default output), so later steps can pick it up as their implicit input but cannot reference it by a dedicated name. | No       |
| `nb_output` | integer | Request a fixed number of outputs from this step's pipe. Cannot be combined with `multiple_output`. | No       |
| `multiple_output` | boolean | Request a variable number of outputs from this step's pipe (the model decides how many). Cannot be combined with `nb_output`. | No       |
| `batch_over` | string | The list in the working memory to batch this step over, running the pipe once per item: a name, or a dotted path to a list held in a field, such as `catalog.pages`, which is a binding followed by a batch (see [Batching over a field](#batching-over-a-field)). Must be provided together with `batch_as`. See [Understanding Multiplicity](../understanding-multiplicity.md). | No       |
| `batch_as` | string | The name each item takes in the working memory during a `batch_over` run, under which the step's pipe reads it through an input: a plain `snake_case` input name, like `result` (see [Stored names](#stored-names)). Must differ from `batch_over` (e.g. `batch_over = "items"`, `batch_as = "item"`). | No       |

#### Stored names

A step's `result` and `batch_as` are **stored names**: the step stores a value in the working memory under each, for a later pipe to read through an input. An input name is always a plain `snake_case` identifier matching `[a-z][a-z0-9_]*`, so a stored name takes the same form, and every value a step stores can be read. A `result` or a `batch_as` in any other form, such as `Pages`, a dotted `doc.pages` or an underscore-led `_pages`, is refused with `invalid_input_name`, which the schema catches too, and the message suggests a plain name. Rename it, such as to `pages`, along with every input, binding path and `batch_over` that reads it. The same rule holds a [`PipeParallel`](PipeParallel.md) branch's `result` and `batch_as`, a [`PipeBatch`](PipeBatch.md)'s `input_item_name` and a binding step's `result`, which a binding step that breaks it reports as `binding_step_invalid`.

A plain `batch_over` reads a name rather than storing one, so it is not held to this form, but it never starts with `_bound_`, a prefix reserved for the list a dotted `batch_over` binds (see [Batching over a field](#batching-over-a-field)), and one that does is refused with `invalid_input_name` too.

#### Binding steps

A binding step is a table with exactly these two keys:

| Key      | Type   | Description                                                        | Required |
| -------- | ------ | ------------------------------------------------------------------ | -------- |
| `from`   | string | The path to bind: a name in working memory followed by zero or more field names, separated by single dots, each a letter followed by letters, digits and underscores. No subscript, expression or whitespace. | Yes      |
| `result` | string | The name the bound value is stored under, a plain snake_case input name. | Yes      |

!!! important "Output Concept Matching"
    The output concept of the `PipeSequence` has to match the output of its last step: the output of the last pipe, or the concept a binding step derives when the sequence ends with one. A batched last step yields the variable list of its branches' results, `X[]`, whatever `nb_output` it asks for, so the sequence declares a variable list.

## What each step reads

Validation follows the values through the sequence, one step after the other, and checks every pipe step against what it reads. At each step, a name in working memory holds the concept and multiplicity of the value last stored under it:

-   the sequence's declared `inputs`, to begin with;
-   a pipe step's `result`, its pipe's output, made a list by `nb_output` or `multiple_output`, and always a variable list `X[]` for a batched step, whatever `nb_output` it asks for;
-   what a nested `PipeSequence` or a `PipeCondition`'s outcome stores in the caller's memory, and the branch results of a `PipeParallel` with `add_each_output`;
-   what a binding step binds (see [What a binding binds](#what-a-binding-binds)).

A pipe step is checked against the `inputs` its pipe declares. For a nested `PipeSequence`, `PipeCondition`, `PipeParallel` or `PipeBatch`, that declaration is its contract, which its own validation holds its steps, outcomes or branches to, whatever the last of them reads. A pipe step whose pipe reads a name as a concept or a multiplicity the name does not hold is refused with `input_stuff_spec_mismatch`, and the message names the step, the name and what stored it:

```text
In pipe 'process_cv', step 2 (pipe 'analyze_one_cv') reads 'cv_pages' as 'Page', but step 1 (pipe 'extract_one_cv') stores it as 'Page[]'. Declare the input as 'Page[]' in pipe 'analyze_one_cv', or make step 1 (pipe 'extract_one_cv') store a 'Page' under 'cv_pages'.
```

-   The concept must be compatible with the read, as a sequence's output must be with its last step's: the same concept or a concept refining it, for instance, and any concept when the step reads `Anything` or `Dynamic`.
-   The multiplicity must match: a list is not a single value, and a single value is not a list. A fixed count such as `Color[5]` satisfies a step reading a variable list `Color[]`, and no other count.
-   A step's `batch_over` must name a list, whose items its pipe reads as the batch item's concept.
-   A name whose values may have different concepts, as when the outcomes of a `PipeCondition` store it under different concepts, must satisfy the read with each of them, including the value it held before when an outcome stores nothing under it.
-   A name a pipe that does not resolve at validation stored, such as a pipe of a dependency not loaded yet, is assumed to hold what the step reads.
-   A value a pipe step stores as `Anything` or `Dynamic`, as the result of a `PipeCondition` whose outcomes produce different concepts, has a concept the run alone knows, so it is assumed to be the concept the step reads, and the items of a list stored as `Anything[]` the concept a batched pipe reads. Its multiplicity is still checked: a single `Anything` read as a list, or batched over, is refused. The sequence's own input declared as `Anything`, and a binding's value of `Anything`, are checked as any other value, also where a `PipeCondition` whose outcomes do not all store the name may leave them in place, and a binding cannot walk a path through a value stored as `Anything`, which has no structure (`binding_path_unresolved`).

Every step reading a declared input is checked this way, not only the last one, so a declared input must satisfy each step that reads it, and one that does is valid even when the last step reads it as something else. When a first step reads `note` as `Markdown` and a later one reads it as `Text`, the sequence declares `note = "Markdown"`, which both accept, and declaring `note = "Text"` is refused at the first step; when a first step reads `pages` as `Page[3]` and a later one as `Page[]`, it declares `pages = "Page[3]"`. That declaration is then what the sequence needs from whatever calls it: a step calling it with a `Text` under `note`, or a `Page[]` under `pages`, is refused. A declared input no step reads is still refused with `extraneous_input_variable`, and a name a step reads from the caller that the sequence does not declare with `missing_input_variable`.

## Binding steps

A binding step hands one part of a bigger value to the steps after it, under a name of its own. An input name is always a plain name, so a pipe never declares `"invoice.total" = "Number"`: the calling sequence binds the field, and the pipe reads the bound name.

```toml
[pipe.acknowledge_invoice]
type = "PipeSequence"
description = "Acknowledges an invoice by its total"
inputs = { invoice = "Invoice" }
output = "Text"
steps = [
    { from = "invoice.total", result = "total_amount" },
    { pipe = "write_receipt", result = "receipt" },
]

[pipe.write_receipt]
type = "PipeCompose"
description = "Writes the receipt for an amount"
inputs = { total_amount = "Number" }
output = "Text"
template = "Received: $total_amount euros"
```

### What a binding binds

The concept of the result is derived before the method runs, from the declared structures the path walks. The first segment names a value in working memory, the root, and each later segment names a field of the concept reached so far.

| The path ends on | The result is |
| --- | --- |
| The root itself, `from = "departure_board"` | A renamed copy of the whole value, with its concept and multiplicity |
| A field of concept `X`, or a field whose concept is `X` | `X` |
| A `text` field, or a field declared by its `choices` | `Text` |
| A `number` or `integer` field | `Number` |
| A `boolean` field | `YesNo` |
| A `date` or `datetime` field | `Date` (a `datetime` keeps its time) |
| A `time` field | `Time` |
| A `dict` field | `JSON` |
| A `list` field of `X`, or of a plain type | `X[]`, or the native the plain type derives, as a list |
| A field holding `Anything` | `Anything`, its value stored as an `Anything` input is: a string as a `Text`, a number as a `Number`, an object as a `JSON`, and so on. A list, or a value of no such type, is refused when the step runs |

The root is typed by the latest step that stored a value under its name, or by the sequence's `inputs` when no step did. A step stores its `result`, and a batched step stores the list of its branches' results, `X[]`, whatever `nb_output` it carries. A nested `PipeSequence` runs its steps on the caller's working memory and a `PipeCondition` runs its chosen outcome there, so a name either of them stores counts as stored by the step that calls it, as do the branch results of a `PipeParallel` with `add_each_output`: a later step, a pipe step or a binding, reads it with no input of that name, and the name keeps its concept and whether it may be absent. A name only some outcomes of a condition store, when another outcome stores nothing under it or is `continue`, may still hold the value it held before, so the sequence needs it as an input, and it keeps its concept only when both values have the same one. When the values a name may hold have different concepts, its concept is not known before the run, so a binding reading it is refused with `binding_path_unresolved`, the message naming each outcome and the concept it stores. That happens when the outcomes of a condition store the name under different concepts, or when one outcome stores a value of another concept than the one an outcome storing nothing, such as `continue`, leaves. Store the name under one concept in every outcome, or bind inside each outcome, where its concept is known.

A root stored by a pipe that does not resolve at validation, such as a pipe of a dependency not loaded yet, is assumed to deliver, as the rest of the sequence's checks assume. Its binding is derived when it runs, from the value the root holds, and checked then against what reads it: the sequence's declared output when the binding ends the sequence, its concept, its multiplicity and whether it may be absent, and the input of a later step reading the result. A mismatch is a run error, never a value of another concept. A root that may be absent still makes the result maybe-absent.

A concept that refines another is walked through the structure it inherits, and a native concept through its pinned definition, so `page.page_view` binds an `Image`, every field of it kept, its `caption` included. A root holding a dependency package's concept, the output of one of the package's pipes, is walked through the package's own definitions, never through a concept of the method spelled the same.

A path is refused with `binding_path_unresolved` when the walk cannot follow it, and the message names the segment and the fields the concept does have:

-   a segment naming no field of the concept reached;
-   a segment after a plain field (`invoice.total.amount`), after a `dict` field, or after a list with no declared item type;
-   a segment into a concept with no structure to walk: a concept declared with neither a `structure` nor `refines`, whether as a string (`Notice = "A notice"`) or as a table with a description alone, unless its code names a registered Python class, whose fields are walked; `Dynamic`, `Anything`, `Composite`; a native holding its value in a single field (`Text`, `Number`, `Time`, `JSON`, `Markdown`); or a concept refining one of these. Bind the value itself instead, `from = "note"`.

A path ending on a list with no declared item type is refused too, since nothing says what its items are.

### Lists map and flatten

When the path crosses a list, whether the root holds a list or a field does, the rest of the path is applied to every item, and every list crossed is flattened into one. The result is always one flat list, `X[]`: binding `pages.page_view` over `Page[]` gives `Image[]`, one image per page, and binding `shipments.parcels` over `Shipment[]` gives every parcel of every shipment. Items holding nothing are dropped, and an empty list is a valid result, so a list result is never absent.

A single result never chooses one item of a list. When the run finds a list under a root typed as a single value, as when a count asked of the whole run reaches the steps of the sequence, the binding step fails with a run error naming the path and both shapes, rather than keep the first item. A bare name typed as a list that finds a single value fails the same way.

### Absence

A binding that finds nothing records an absence, under the optionality model (see [Understanding Optionality](../understanding-optionality.md#binding-steps-under-absence)):

-   when the path reaches a field holding nothing, the result is recorded as `DECLARED_ABSENT`, and the reason names the segment that held nothing;
-   when the root itself is absent, the binding is skipped as a pipe with an absent plain input is, and the result is recorded as `SKIPPED`, chained to the root's own record.

A single result can be absent when its path walks a field that is not `required` and has no default, or, on a concept whose structure is a Python class, a field whose annotation admits `None`, required or not, so the static checks treat it as a maybe-absent value: a step reading it as a plain input may be lifted, and a sequence ending with it declares its output optional (`Text?`), or the validation refuses it with `optional_not_handled`.

### A copy, with an identity of its own

The bound value is a deep copy taken when the step runs: changing the root afterwards, or storing another value under the root's name, leaves the bound value as it was, and the reverse. The result is a new stuff with its own stuff code, and in the execution graph the binding is a node of its own, of kind `binding`, fed by the root's producer and producing the stuff it binds.

### What validation checks

-   A step that reads a bound name is checked against the derived concept and multiplicity, as every step is checked against what it reads (see [What each step reads](#what-each-step-reads)): reading `total_amount` as `Text` when the binding derives a `Number` is refused with `input_stuff_spec_mismatch`, and `batch_over` a bound name requires a list.
-   A sequence ending with a binding step is checked as one ending with a pipe: its output concept with `inadequate_output_concept`, its multiplicity with `inadequate_output_multiplicity`, and a maybe-absent result with `optional_not_handled`.
-   A step asking a sequence that ends with a binding step for a count of outputs, with `nb_output` or `multiple_output`, is refused with `inadequate_output_multiplicity` when the binding does not bind that count: a binding binds what its path derives, whatever count its caller asks for. A batched step asks its branches for nothing, so it is not checked.
-   A root that is neither an input of the sequence nor stored by an earlier step on every run is refused with `missing_input_variable`.
-   A malformed step is refused with `binding_step_invalid`: `pipe` beside `from`, a binding without `result`, a binding carrying `nb_output`, `multiple_output`, `batch_over` or `batch_as`, a `from` or a `result` outside its grammar, and a dotted `batch_over` outside the path grammar or on a `PipeParallel` branch. The schema refuses each of these too.

A binding step lives in a `PipeSequence`'s `steps` only. A [`PipeParallel`](PipeParallel.md) branch is always a pipe step, since its branches run at once and a binding orders a value before the steps that read it: bind in the sequence before the parallel.

### Batching over a field

A pipe step's `batch_over` may be a dotted path to a list held in a field. The step is then a binding followed by a batch: the path is bound under a private name, by every rule of a binding step's `from`, and the step batches over the bound list.

```toml
[pipe.index_catalog]
type = "PipeSequence"
description = "Writes one index line per page of a catalog"
inputs = { catalog = "Catalog" }
output = "Text[]"
steps = [
    { pipe = "write_index_line", batch_over = "catalog.pages", batch_as = "page", result = "index_lines" },
]
```

This step runs exactly as the two steps below, apart from the name the list is bound under:

```toml
steps = [
    { from = "catalog.pages", result = "pages" },
    { pipe = "write_index_line", batch_over = "pages", batch_as = "page", result = "index_lines" },
]
```

So a dotted `batch_over` shares everything a binding does:

-   The root is typed by the latest step that stored it, or by the sequence's `inputs`, and the sequence needs it as its own concept: `catalog` as a `Catalog`, never as the item's `CatalogPage`.
-   Lists map and flatten, so `batch_over = "catalogs.pages"` over `Catalog[]` runs one branch per page of every catalog, and an absent root binds an empty list, which runs no branch.
-   The path must reach a list, through a list root, a list field along the way, or a list field it ends on. A path deriving a single value, such as `catalog.season`, is refused before the run with `input_stuff_spec_mismatch`, as a batch over a value that is not a list is, and so is a list whose items the pipe reads as another concept.
-   A path the structures cannot walk is refused with `binding_path_unresolved`, and a root that is neither an input of the sequence nor stored by an earlier step with `missing_input_variable`, each message naming the `batch_over` as written.
-   A path outside the path grammar, such as `catalog..pages`, is refused with `binding_step_invalid`, which the schema catches too.
-   In the execution graph, the binding is a node of kind `binding`, fed by the root's producer, and it feeds the batch.

The private name starts with an underscore, `_bound_catalog_pages` for `catalog.pages`, so no template or input can read it: it shows only in the working memory the run leaves and in the graph. The `_bound_` prefix is reserved for these names. A nested `PipeSequence` binds in the working memory of the sequence calling it, so a name of the caller taking the prefix could be overwritten by the list a sequence it calls binds. No name a step stores a value under can take it, since a [stored name](#stored-names) is a plain input name, which never starts with an underscore, and a plain `batch_over` that starts with `_bound_`, on a sequence step or a `PipeParallel` branch, is refused with `invalid_input_name`, which the schema catches too, and the message asks for another name. Only a sequence's steps bind, so a [`PipeParallel`](PipeParallel.md) branch carries a plain `batch_over` only, and a dotted one there is refused with `binding_step_invalid`: bind the list in a step before the `PipeParallel`, and batch the branch over the bound name.

### Example

Let's imagine a pipeline that first extracts text from an image, then summarizes that text, and finally translates the summary into French.

```toml
[pipe.extract_text_from_image]
type = "PipeExtract"
description = "Extract text from an image"
inputs = { image = "Image" }
output = "Page[]"
model = "@default-extract-image"

[pipe.summarize_text]
type = "PipeLLM"
description = "Summarize text"
inputs = { extracted_text = "Page[]" }
output = "Text"
prompt = "Summarize this text:\n@extracted_text"

[pipe.translate_to_french]
type = "PipeLLM"
description = "Translate text to French"
inputs = { english_summary = "Text" }
output = "Text"
prompt = "Translate this summary to French:\n@english_summary"


[pipe.image_to_french_summary]
type = "PipeSequence"
description = "Extract, summarize, and translate text from an image"
inputs = { image = "Image" }
output = "Text"
steps = [
    { pipe = "extract_text_from_image", result = "extracted_text" },
    { pipe = "summarize_text", result = "english_summary" },
    { pipe = "translate_to_french", result = "french_summary" },
]
```

## Related Documentation

- [Invoice extraction](https://github.com/Pipelex/methods/tree/main/methods/invoice_extraction) - A method in the method library that classifies each page, then extracts structured invoice data
- [Tweet optimizer](https://github.com/Pipelex/methods/tree/main/methods/tweet_optimizer) - A method in the method library that scores a draft tweet and rewrites it in your style
- [Table extraction](https://github.com/Pipelex/methods/tree/main/methods/table_extraction) - A method in the method library that extracts a table from a screenshot into HTML, then reviews it against the image
- [Gantt chart extraction](https://github.com/Pipelex/pipelex-cookbook/tree/main/methods/extract_gantt) - A cookbook method that returns every task and milestone of a Gantt chart image with their dates