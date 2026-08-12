---
description: "Provide inputs to Pipelex pipelines from the CLI, Python API, or Client. Just provide the values — Pipelex interprets them against the pipe's declared input signature."
---

# Providing Inputs to Pipelines

Every pipe declares what it needs: an `inputs` signature mapping each variable name to a concept (and, for lists, a multiplicity). When you run a pipe, **you just provide the values** — Pipelex interprets each one *top-down against that declared signature*, so a bare string becomes the declared concept (a `legal.Question`, not a generic `native.Text`), a bare number satisfies a numeric input, and a plain object validates against a structured concept.

This is the fast path. There is also an explicit `{"concept": ..., "content": ...}` escape hatch for the rare cases where you need to override or disambiguate the concept — it still works, and it is now compatibility-checked against the declaration. Both are covered below.

## See what a pipe expects

Generate a template that mirrors the pipe's signature:

```bash
pipelex build inputs bundle path/to/my_pipe.mthds
```

This writes `inputs.json` (add `--format toml` for TOML) with an example value per input, shaped exactly the way the pipe expects them. Fill in the values and run:

```bash
pipelex run bundle path/to/my_pipe.mthds --inputs inputs.json
```

For a pipe declaring `question = "Question"`, `priority = "Priority"`, `invoice = "Invoice"`, and `tags = "Tag[]"`, the template is the **light** shape — the values themselves, not envelopes:

```json
{
  "question": "text_value",
  "priority": 1,
  "invoice": {
    "invoice_number": "invoice_number_value",
    "amount": 0.0
  },
  "tags": ["text_value"]
}
```

The TOML template carries the declared concept for each key as a comment, so you can see what you are filling in (JSON has no comments — use `--explicit` there to see concepts):

```toml
# concept: my_domain.Question
question = "text_value"
# concept: my_domain.Priority
priority = 1
# concept: my_domain.Invoice
invoice = {invoice_number = "invoice_number_value", amount = 0.0}
# concept: my_domain.Tag[]
tags = ["text_value"]
```

!!! tip "Prefer the light template"
    The light values are exactly what the runner accepts, so a template you generate and fill in runs as-is. Add `--explicit` to `build inputs` if you want the ceremonial `{concept, content}` envelope form instead (see [the escape hatch](#the-explicit-format-escape-hatch)).

## Providing values by concept type

Match the value to the input's declared concept. The declared concept is applied automatically — you never repeat it in the value.

| Declared concept refines… | Provide | Example |
| --- | --- | --- |
| `Text` | a string | `"What are the fees?"` |
| `Number` | a number (not a boolean) | `42` or `3.14` |
| `YesNo` | a boolean | `true` / `false` |
| `Date` | an extended ISO 8601 date/datetime string (or a TOML date literal) | `"2026-09-01"` |
| `Image` / `Document` | a URL or file path | `"photo.jpg"`, `"https://…/a.pdf"` |
| a structured concept | an object | `{"name": "Alice", "age": 30}` |

```json
{
  "question": "What are the late-payment fees?",
  "priority": 3,
  "is_urgent": true,
  "hearing": "2026-09-01",
  "contract": "contracts/nda.pdf",
  "client": {
    "name": "Acme Corp",
    "country": "France"
  }
}
```

Each value is typed as the **declared** concept — `question` becomes a `legal.Question`, not a bare `native.Text` — so downstream steps see the concept the pipe was designed around.

!!! note "Numbers vs. booleans"
    A boolean is never read as a number, even though `true`/`false` look numeric to some languages. Provide `true`/`false` only for a `YesNo`-refining input; provide `42` for a `Number`-refining one.

!!! note "Concepts the signature can't shape"
    A handful of concepts carry no single expected value shape — `Dynamic`, `Anything`, and the container/structural natives (`Html`, `JSON`, `Page`, `TextAndImages`, `SearchResult`, `Composite`). For an input declared as one of these, the signature can't guide interpretation, so the value is read by its own shape (a bare string becomes `native.Text`, and so on). Use the explicit format if you need a specific concept there.

## Lists and multiplicity

When an input is declared multiple (`Tag[]`, or a fixed count `Tag[3]`), provide a JSON/TOML list — each element is shaped element-wise into the declared item concept:

```json
{
  "tags": ["billing", "urgent", "enterprise"]
}
```

- A **single** value auto-wraps into a one-item list, so `"tags": "urgent"` is accepted for a `Tag[]` input.
- An **empty** list is legal and produces an empty collection.
- A fixed count `Tag[3]` validates the number of items — too few or too many is a clear error.
- Providing a list where the signature declares a **single** value is a clear error (Pipelex won't silently pick one).

See [Understanding Multiplicity](understanding-multiplicity.md) for the full model of single items versus collections.

### Tabular data for a structured list

A declared structured list (e.g. `people = "Person[]"`) also accepts a path to a `.csv`/tabular file — each row becomes one item:

```json
{
  "people": "team.csv"
}
```

The columns map to the concept's fields. See [CSV Input & Output](csv-input-and-output.md).

## Files and relative paths

For `Image`/`Document` inputs, a **relative** path is resolved against the **inputs file's** directory (a leading `~` expands to your home directory; absolute paths, `http(s)://`, and storage URIs are used as-is). So an `inputs.json` sitting next to a `contracts/` folder can say `"contract": "contracts/nda.pdf"` and it resolves correctly regardless of where you launch the command.

Tabular references use the same relative-path resolution, but v1 reads local tabular files only. A `.csv` path must resolve to a local file; download remote or storage-hosted tables before referencing them.

Callers that don't load from a file — the Python API and the hosted client — should pass absolute URLs or storage URIs, since there is no inputs-file directory to resolve against.

## The explicit format (escape hatch)

The explicit envelope `{"concept": "...", "content": ...}` gives you direct control over which concept a value is interpreted as. It is now **compatibility-checked**: the concept you name must be compatible with the input's declared concept, otherwise the run fails with a clear error.

```json
{
  "question": {
    "concept": "legal.Question",
    "content": "What are the fees?"
  }
}
```

Reach for it when:

- **You want a more-specific concept than the signature declares.** If an input is declared `native.Text` but you have a `legal.Question`, name it explicitly — a compatible, more-specific concept wins.
- **A concept name is ambiguous.** When you reference a concept by bare name and it exists in multiple domains, prefix the domain: `"accounting.Invoice"` instead of `"Invoice"`.
- **You are passing a Python object** (see below).

Generate the envelope template with `pipelex build inputs … --explicit`:

```json
{
  "question": {"concept": "my_domain.Question", "content": {"text": "text_value"}},
  "priority": {"concept": "my_domain.Priority", "content": {"number": 1}},
  "invoice": {"concept": "my_domain.Invoice", "content": {"invoice_number": "invoice_number_value", "amount": 0.0}},
  "tags": {"concept": "my_domain.Tag", "content": [{"text": "text_value"}]}
}
```

### Concept name resolution

Inside an explicit envelope, the `concept` you write is resolved against your loaded domains:

- A bare name (`"Invoice"`) found in exactly one domain is used directly.
- A bare name found in **multiple** domains is an error — prefix the domain (`"accounting.Invoice"`).
- A name found in **no** domain is an error.

Domain-prefixed names (`"domain_code.ConceptName"`) bypass the search and are always unambiguous.

## Python API and client

From Python, the same light values work — and you can additionally pass already-built content objects:

```python
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent

inputs = {
    # Light values, shaped against the signature
    "topic": "A robot learning to love",
    "priority": 3,

    # Native content objects (typed directly)
    "photo": ImageContent(url="photo.jpg"),
    "contract": DocumentContent(url="nda.pdf"),

    # Explicit envelope with a custom concept
    "draft_tweet": {
        "concept": "social.DraftTweet",
        "content": "Check out this framework!",
    },
}
```

A list of content objects (`[MyConcept(...), MyConcept(...)]`) or an already-wrapped `ListContent(items=[...])` is accepted for a declared-multiple input; a `DictStuff(concept=..., content=...)` is the object form of the explicit envelope. All are compatibility-checked against the declaration.

!!! note "Nothing to provide for a list input? Send the empty list."
    A plural slot is never *absent* — when nothing is found, it **is** the empty list (see [Understanding Multiplicity](understanding-multiplicity.md)). So a caller with no pictures provides `"photos": []`, in either spelling — bare, or as the envelope `{"concept": "native.Image", "content": []}`. Both build an empty `ListContent` typed with the declared item concept, and a template that guards its use (`{% if photos %}`) renders nothing.

    **Omitting the key is not the same thing**, and fails the run with *"missing required inputs"*: the presence markers are for singular values, and `Image[]?` is rejected outright (`optional_marker_invalid`) precisely because a plural slot has no absence to declare. See [Understanding Optionality](understanding-optionality.md).

!!! note "Bare numbers and booleans from strictly-typed Python"
    A bare number or boolean (`"priority": 3`) is accepted at runtime, but the `PipelineInputs` protocol type does not yet admit bare scalars, so a strict static type-checker may flag it until that type is widened. If your codebase runs a type-checker, type the inputs dict as `dict[str, Any]`, or pass the value through the explicit envelope (`{"concept": "...", "content": 3}`).

## Unknown input names are rejected

If you provide a name the pipe does not declare, the run fails with an error that lists the declared names. This catches typos and stale inputs files early, rather than silently ignoring the extra value.

```text
Input 'invoce' is not declared by this pipe. Declared inputs: 'question', 'priority', 'invoice', 'tags'.
```

## What can go wrong

When a value cannot be shaped against its declared concept, Pipelex raises a typed error that names the input, the declared concept, what you provided, and the **expected shape**. Common cases:

- **Wrong kind** — a string where a number is declared, a list where a single value is declared, an object where a scalar is declared.
- **Count mismatch** — the wrong number of items for a fixed-count `X[N]` input.
- **Structure validation** — an object missing a required field of a structured concept.
- **Incompatible explicit concept** — an envelope naming a concept that is not compatible with the declaration.
- **Null value** — a top-level `null`; absence is expressed by *omitting* the key, not by providing `null`. (An input declared optional with `?` may simply be left out — see [Understanding Optionality](understanding-optionality.md).)

## Input files: JSON or TOML

An inputs file is a dictionary of input names to values, accepted as **both JSON and TOML**, discriminated by file extension (`.toml` → TOML, everything else → JSON). Both produce the same dictionary, so every shape above applies to either. TOML's multi-line strings (`"""…"""`) make text-heavy inputs far easier to author, and a top-level TOML date/datetime literal (`hearing = 2026-09-01`) maps directly to the native [`Date`](../concepts/native-concepts.md) concept.

See the [run CLI reference](../../tools/cli/run.md#input-file-formats) for the extension rule, auto-detection, and TOML details.

## Related Documentation

- [Executing Pipelines](./executing-pipelines.md) — run pipelines with these inputs
- [Understanding Multiplicity](understanding-multiplicity.md) — single items vs. lists
- [Understanding Optionality](understanding-optionality.md) — optional (`?`) inputs
- [CSV Input & Output](csv-input-and-output.md) — tabular inputs and outputs
- [Native Concepts](../concepts/native-concepts.md) — the built-in concept families
- [Define Your Concepts](../concepts/define_your_concepts.md) — concepts and their role
- [Build Inputs (CLI)](../../tools/cli/build/inputs.md) — generate an inputs template
