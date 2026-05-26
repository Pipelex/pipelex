# PipeStructure

`PipeStructure` is the operator that turns text into structured data. It takes a single `Text`-compatible input, asks an LLM to extract the requested structure, and produces a typed object (or list of objects) matching your output concept.

Use `PipeStructure` whenever the source of the text is not the LLM call itself — for example when text comes from a PDF extraction, a web search result, a user message, or an upstream `PipeLLM` step that intentionally produced free-form prose.

## How it works

1. The operator reads the single declared input from the working memory and renders the built-in `structuring_prompt` template against it.
2. It appends a JSON-schema description of the target concept (the same helper `PipeLLM` uses for object generation) so the model knows which fields to fill.
3. It picks an LLM setting using the same precedence as `PipeLLM` for object generation: explicit `model` on the pipe → `llm_choice_overrides.for_object` → `llm_choice_defaults.for_object`.
4. It calls `make_object` (or `make_object_list` when the output multiplicity is a list) and emits the result as the pipe's output.

`PipeStructure` does not accept user-controlled prompt templates. The structuring prompt lives in `pipelex.toml` under `[cogt.llm_config.generic_templates] structuring_prompt`; the only variable rendered into it is `text`, fed automatically from the declared input.

## Configuration

`PipeStructure` is configured in your pipeline's `.mthds` file.

### MTHDS Parameters

| Parameter | Type | Description | Required |
| --- | --- | --- | --- |
| `type` | string | The type of the pipe: `PipeStructure` | Yes |
| `description` | string | A description of what this structuring step produces. | Yes |
| `inputs` | dictionary | Exactly one input. Its concept must be `Text` or refine `Text` (e.g. `Document` is not allowed; a domain concept that `refines = "Text"` is). | Yes |
| `output` | string | The target structured concept, with optional multiplicity (`Foo`, `Foo[]`, `Foo[3]`). Cannot be `Text` or `Text`-compatible. | Yes |
| `model` | string or table | The LLM choice used for the structuring call. Defaults to the `for_object` LLM choice (override → default). | No |

### LLM Setting Fields

When `model` is given as a table, it accepts the same fields as `PipeLLM`'s inline LLM setting (`model`, `temperature`, `max_tokens`, `reasoning_effort`, `reasoning_budget`, `description`). See [PipeLLM › LLM Setting Fields](./PipeLLM.md#llm-setting-fields).

!!! note "No images, no documents"
    `PipeStructure` is intentionally narrow: it takes one `Text` input. To structure an image or a PDF page, run an upstream extraction step (e.g. `PipeExtract` or a vision `PipeLLM`) and feed its text output into `PipeStructure`.

### Output Multiplicity

Use bracket notation in the `output` field to control how many items the LLM should return:

- `output = "Review"` — exactly one item.
- `output = "Review[]"` — the model decides how many.
- `output = "Review[3]"` — exactly three.

See [Understanding Multiplicity](../understanding-multiplicity.md) for the full picture.

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
Read this invoice and produce a faithful textual transcript of every line item, total, and metadata: @invoice_pdf
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

For the common case where the text is freshly produced by an LLM and you want a single declaration, see [`structuring_method = "preliminary_text"` on PipeLLM](./PipeLLM.md#structuring-method-preliminary-text), which expands at build time into a `PipeSequence` of `PipeLLM` (text) + `PipeStructure`.

## Related Documentation

- [PipeLLM](./PipeLLM.md) — direct structured generation in a single call, plus the `preliminary_text` shorthand.
- [PipeExtract](./PipeExtract.md) — produces text from PDFs and images, a natural upstream step.
- [Understanding Multiplicity](../understanding-multiplicity.md) — single vs list outputs.
